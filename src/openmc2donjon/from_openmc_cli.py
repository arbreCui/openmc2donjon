"""One-step OpenMC recipe/statepoint to DONJON ASCII CLI."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__
from .adf_augment import augment_hdf5_with_adf, parse_faces
from .adf_sidecar import DEFAULT_CARTESIAN_FACES, create_flux_ratio_adf_sidecar
from .bundle import ArtifactSpec, bundle_artifacts, parse_extra_artifact
from .from_openmc_summary import FROM_OPENMC_SUMMARY_SCHEMA
from .homogeneous_face_flux import create_homogeneous_face_flux
from .low_order_driver import check_low_order_driver, create_low_order_driver
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5, read_mgxs_hdf5_histories
from .openmc_surface_flux import (
    DEFAULT_TALLY_NAME as DEFAULT_SURFACE_FLUX_TALLY_NAME,
    export_openmc_surface_flux,
)
from .openmc_statepoint import (
    StatepointLoadError,
    dry_run_openmc_statepoint_recipe,
    export_openmc_statepoint_recipe,
)
from .recipe_dry_run_report import (
    print_recipe_dry_run_summary,
    print_strict_dry_run_decision,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon-from-openmc",
        description=(
            "Export an OpenMC MGXS recipe/statepoint to the HDF5 handoff and "
            "immediately convert it to DONJON ASCII."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        required=True,
        help="Python recipe defining build_library() for an OpenMC statepoint export",
    )
    parser.add_argument(
        "--statepoint",
        type=Path,
        help="OpenMC statepoint consumed by the recipe",
    )
    parser.add_argument(
        "--no-load-statepoint",
        action="store_true",
        help="export the recipe library without loading a statepoint first",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect the recipe and one-step conversion plan without writing files",
    )
    parser.add_argument(
        "--strict-dry-run",
        action="store_true",
        help=(
            "with --dry-run, return non-zero if any production checklist item "
            "warns/fails or if recipe warnings are emitted"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib"),
        default="multicompo",
        help="output object format (default: multicompo)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "output ASCII path (default: out.mcompo.txt for multicompo, "
            "out.macrolib.txt for macrolib)"
        ),
    )
    parser.add_argument(
        "--keep-hdf5",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the intermediate MGXS HDF5 to PATH instead of a temporary file",
    )
    parser.add_argument(
        "--scatter-mgxs-type",
        default=None,
        help=(
            "explicit OpenMC MGXS type to export as DONJON scattering. "
            "Default accepts only ordinary 'scatter matrix'."
        ),
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=(
            "write a standard production run directory with mgxs_library.h5, "
            "DONJON ASCII output, summary JSON, and manifest.json"
        ),
    )
    parser.add_argument(
        "--root-name",
        default=DEFAULT_ROOT_NAME,
        help=f"top-level LCM directory name for MULTICOMPO output (default: {DEFAULT_ROOT_NAME})",
    )
    parser.add_argument(
        "--comment",
        default=None,
        help="COMMENT block text for MULTICOMPO output",
    )
    parser.add_argument(
        "--burnup",
        type=float,
        default=None,
        help="write a single-point BURN parameter axis with this value",
    )
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help="write this constant H-FACTOR when the exported HDF5 does not provide one",
    )
    parser.add_argument(
        "--adf-source",
        type=Path,
        default=None,
        help="HDF5 sidecar containing computed ADF/DF values to inject before conversion",
    )
    parser.add_argument(
        "--adf-faces",
        default=None,
        help="comma-separated expected ADF face names in --adf-source",
    )
    parser.add_argument(
        "--adf-kind",
        default=None,
        help="override root adf_kind provenance attribute when injecting --adf-source",
    )
    parser.add_argument(
        "--adf-real",
        choices=("true", "false"),
        default=None,
        help="override root adf_real provenance attribute when injecting --adf-source",
    )
    parser.add_argument(
        "--adf-source-label",
        default=None,
        help="override root adf_source provenance attribute when injecting --adf-source",
    )
    parser.add_argument(
        "--build-flux-ratio-adf",
        action="store_true",
        help=(
            "inside --run-dir, build a flux-ratio ADF sidecar from heterogeneous "
            "surface flux and a low-order driver, inject it, and bundle all side artifacts"
        ),
    )
    parser.add_argument(
        "--adf-surface-flux",
        type=Path,
        default=None,
        help=(
            "with --build-flux-ratio-adf, existing heterogeneous face-flux HDF5 "
            "or FILE::DATASET; omit when using --export-surface-flux"
        ),
    )
    parser.add_argument(
        "--export-surface-flux",
        action="store_true",
        help=(
            "with --build-flux-ratio-adf, export heterogeneous face flux from "
            "the OpenMC statepoint before building the ADF sidecar"
        ),
    )
    parser.add_argument(
        "--surface-flux-tally-name",
        default=DEFAULT_SURFACE_FLUX_TALLY_NAME,
        help=(
            "with --export-surface-flux, OpenMC tally name "
            f"(default: {DEFAULT_SURFACE_FLUX_TALLY_NAME})"
        ),
    )
    parser.add_argument(
        "--surface-flux-mesh-shape",
        default=None,
        help="with --export-surface-flux, mesh shape as Y,X; defaults to 1,N",
    )
    parser.add_argument(
        "--surface-flux-mu-edges",
        default=None,
        help="with --export-surface-flux, comma-separated MuSurfaceFilter bin edges",
    )
    parser.add_argument(
        "--surface-flux-face-area",
        type=float,
        default=1.0,
        help="with --export-surface-flux, face area used in current-to-flux reconstruction",
    )
    parser.add_argument(
        "--low-order-raw-driver",
        default=None,
        help=(
            "with --build-flux-ratio-adf, raw low-order driver HDF5 bundle; "
            "omitted low-order flux/current datasets are auto-detected in this file"
        ),
    )
    parser.add_argument(
        "--homogeneous-face-flux",
        default=None,
        help=(
            "with --build-flux-ratio-adf, existing homogeneous face-flux HDF5 "
            "or FILE::DATASET denominator; skips low-order driver reconstruction"
        ),
    )
    parser.add_argument(
        "--low-order-volume-flux",
        default=None,
        help=(
            "with --build-flux-ratio-adf, HDF5 file or FILE::DATASET containing "
            "low-order volume-average flux"
        ),
    )
    parser.add_argument(
        "--low-order-net-current",
        default=None,
        help=(
            "with --build-flux-ratio-adf, HDF5 file or FILE::DATASET containing "
            "net current density"
        ),
    )
    parser.add_argument(
        "--low-order-net-current-sign-convention",
        default=None,
        choices=("auto", "positive-outward", "positive-inward"),
        help=(
            "with --build-flux-ratio-adf, raw low-order current sign; default "
            "auto reads HDF5 sign_convention metadata or assumes positive-outward"
        ),
    )
    parser.add_argument(
        "--low-order-source-label",
        default="external low-order driver",
        help="with --build-flux-ratio-adf, provenance label for the low-order driver handoff",
    )
    parser.add_argument(
        "--adf-face-widths",
        default="1.0",
        help=(
            "with --build-flux-ratio-adf, one width for all faces or comma-separated "
            "widths matching --adf-faces"
        ),
    )
    parser.add_argument(
        "--adf-invalid-fill",
        type=float,
        default=None,
        help="with --build-flux-ratio-adf, fill value for invalid flux-ratio ADF bins",
    )
    parser.add_argument(
        "--adf-clip-min",
        type=float,
        default=None,
        help="with --build-flux-ratio-adf, optional lower clip bound for ADF values",
    )
    parser.add_argument(
        "--adf-clip-max",
        type=float,
        default=None,
        help="with --build-flux-ratio-adf, optional upper clip bound for ADF values",
    )
    parser.add_argument(
        "--mixture",
        action="append",
        default=None,
        help="write only the named mixture; repeat to keep several mixtures",
    )
    parser.add_argument(
        "--no-overwrite-hdf5",
        action="store_true",
        help="fail if --keep-hdf5 already exists",
    )
    parser.add_argument(
        "--force-run-dir",
        action="store_true",
        help="with --run-dir, overwrite existing managed run-directory artifacts",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable conversion summary JSON",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run HDF5 input-contract preflight after export and before conversion",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="with --check, require ADF data for every mixture",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="with --check, comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="with --check, require explicit transport_total datasets",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="with --check, require positive volume attributes",
    )
    parser.add_argument(
        "--scatter-row-balance-warn",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, warn if max |total - absorption - sum(P0 scatter out)| "
            "/ |total| exceeds REL"
        ),
    )
    parser.add_argument(
        "--scatter-row-balance-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, fail if max |total - absorption - sum(P0 scatter out)| "
            "/ |total| exceeds REL"
        ),
    )
    parser.add_argument(
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
    )
    parser.add_argument(
        "--adf-summary-json",
        type=Path,
        default=None,
        help="with --adf-source, write a machine-readable ADF injection summary JSON",
    )
    parser.add_argument(
        "--extra-artifact",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="with --run-dir, copy an additional artifact into manifest.json; repeatable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.build_flux_ratio_adf:
        args.check = True
        args.require_adf = True
    _apply_run_dir_defaults(args)
    if args.extra_artifact and args.run_dir is None:
        parser.error("--extra-artifact requires --run-dir")
    _extra_artifacts_from_args(args, parser)
    if args.expected_adf_faces is None and args.adf_faces is not None:
        args.expected_adf_faces = args.adf_faces
    _validate_flux_ratio_adf_args(args, parser)
    if args.strict_dry_run and not args.dry_run:
        parser.error("--strict-dry-run requires --dry-run")
    try:
        if args.dry_run:
            return 0 if _run_dry_run(args) else 1
        if args.statepoint is None and not args.no_load_statepoint:
            parser.error("--statepoint is required unless --no-load-statepoint is set")

        output_path = _output_path(args.output, args.format)
        _prepare_run_dir(args, output_path, parser)
        if args.keep_hdf5 is not None:
            return 0 if _run_pipeline(args, args.keep_hdf5, output_path, hdf5_kept=True) else 1
        else:
            with tempfile.TemporaryDirectory(prefix="openmc2donjon_") as tmpdir:
                ok = _run_pipeline(
                    args,
                    Path(tmpdir) / "mgxs_library.h5",
                    output_path,
                    hdf5_kept=False,
                )
                return 0 if ok else 1
    except StatepointLoadError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 1


def _run_dry_run(args: argparse.Namespace) -> bool:
    output_path = _output_path(args.output, args.format)
    hdf5_path = args.keep_hdf5
    summary = dry_run_openmc_statepoint_recipe(
        args.recipe,
        statepoint_path=args.statepoint,
        load_statepoint=args.statepoint is not None and not args.no_load_statepoint,
        output_path=hdf5_path,
        scatter_mgxs_type=args.scatter_mgxs_type,
    )
    print_recipe_dry_run_summary(summary)
    print("one-step conversion dry-run OK")
    print(f"  format: {args.format}")
    print(f"  ascii_output: {output_path} (not written)")
    if hdf5_path is None:
        print("  hdf5: temporary handoff (not written)")
    else:
        print(f"  hdf5: {hdf5_path} (not written)")
    if args.format == "multicompo":
        print(f"  root_name: {args.root_name}")
    else:
        print("  root_name: n/a")
    print(f"  selected_mixtures: {_render_optional_list(args.mixture)}")
    print(f"  single_point_burnup: {_render_optional_value(args.burnup)}")
    print(f"  h_factor_default: {_render_optional_value(args.h_factor_default)}")
    print(f"  scatter_mgxs_type: {args.scatter_mgxs_type or 'scatter matrix'}")
    if args.adf_source is None:
        print("  adf_source: none")
    else:
        print(f"  adf_source: {args.adf_source} (not read)")
        print(f"  adf_faces: {_render_optional_value(args.adf_faces)}")
        if args.adf_summary_json is None:
            print("  adf_summary_json: none")
        else:
            print(f"  adf_summary_json: {args.adf_summary_json} (not written)")
    if args.build_flux_ratio_adf:
        paths = _flux_ratio_adf_paths(args)
        print("  flux_ratio_adf: enabled")
        if args.export_surface_flux:
            print(f"    surface_flux: {paths['surface_flux']} (not written)")
            print(f"    surface_flux_summary: {paths['surface_flux_summary']} (not written)")
            print(f"    surface_flux_tally: {args.surface_flux_tally_name}")
            print(f"    surface_flux_mesh_shape: {_render_optional_value(args.surface_flux_mesh_shape)}")
            print(f"    surface_flux_mu_edges: {_render_optional_value(args.surface_flux_mu_edges)}")
            print(f"    surface_flux_face_area: {args.surface_flux_face_area}")
        else:
            print(f"    surface_flux: {args.adf_surface_flux} (not read)")
        print(
            "    low_order_raw_driver: "
            f"{_render_optional_value(args.low_order_raw_driver)}"
        )
        if args.homogeneous_face_flux is not None:
            print(f"    homogeneous_face_flux: {args.homogeneous_face_flux} (not read)")
        else:
            print(
                "    low_order_volume_flux: "
                f"{_render_optional_value(args.low_order_volume_flux)}"
            )
            print(
                "    low_order_net_current: "
                f"{_render_optional_value(args.low_order_net_current)}"
            )
            print(f"    low_order_driver: {paths['low_order_driver']} (not written)")
            print(
                f"    low_order_driver_check_summary: "
                f"{paths['low_order_driver_check_summary']} (not written)"
            )
            print(f"    homogeneous_face_flux: {paths['homogeneous_face_flux']} (not written)")
        print(f"    adf_sidecar: {paths['adf_sidecar']} (not written)")
        print(f"    adf_sidecar_summary: {paths['adf_sidecar_summary']} (not written)")
    else:
        print("  flux_ratio_adf: disabled")
    if args.extra_artifact:
        print("  extra_artifacts:")
        for artifact in _extra_artifacts_from_args(args):
            print(f"    {artifact.label}: {artifact.source} (not copied)")
    else:
        print("  extra_artifacts: none")
    if args.summary_json is None:
        print("  summary_json: none")
    else:
        print(f"  summary_json: {args.summary_json} (not written)")
    if args.check:
        print("  check: enabled after HDF5 export")
        print(f"    require_volume: {_yes_no(args.require_volume)}")
        print(f"    require_transport_dataset: {_yes_no(args.require_transport_dataset)}")
        print(f"    require_adf: {_yes_no(args.require_adf)}")
        print(f"    expected_adf_faces: {_render_optional_value(args.expected_adf_faces)}")
        print(
            "    scatter_row_balance_warn: "
            f"{_render_optional_value(args.scatter_row_balance_warn)}"
        )
        print(
            "    scatter_row_balance_fail: "
            f"{_render_optional_value(args.scatter_row_balance_fail)}"
        )
        if args.check_summary_json is None:
            print("    check_summary_json: none")
        else:
            print(f"    check_summary_json: {args.check_summary_json} (not written)")
    else:
        print("  check: disabled")
    if args.strict_dry_run:
        return print_strict_dry_run_decision(summary)
    return True


def _run_pipeline(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    *,
    hdf5_kept: bool,
) -> bool:
    recipe_summary = export_openmc_statepoint_recipe(
        args.recipe,
        hdf5_path,
        statepoint_path=args.statepoint,
        load_statepoint=not args.no_load_statepoint,
        scatter_mgxs_type=args.scatter_mgxs_type,
        overwrite=not args.no_overwrite_hdf5,
    )
    export_summary = recipe_summary.output
    print(
        f"exported {len(export_summary.domains)} domains, "
        f"{export_summary.energy_groups} groups, P{export_summary.legendre_order} "
        f"from recipe {recipe_summary.recipe_path}"
    )

    if args.build_flux_ratio_adf:
        args._generated_adf_source, args._generated_adf_artifacts = _build_flux_ratio_adf(
            args,
            hdf5_path,
            statepoint_path=recipe_summary.statepoint_path,
        )

    adf_source = _effective_adf_source(args)
    if adf_source is not None:
        _inject_adf(args, hdf5_path, adf_source=adf_source)

    if args.check:
        ok = run_preflight(
            [hdf5_path],
            output_format=args.format,
            output_path=output_path,
            require_adf=args.require_adf,
            expected_adf_faces=args.expected_adf_faces,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            scatter_row_balance_warn=args.scatter_row_balance_warn,
            scatter_row_balance_fail=args.scatter_row_balance_fail,
            summary_json=args.check_summary_json,
        )
        if not ok:
            if hdf5_kept:
                print(f"kept HDF5: {hdf5_path}")
            return False

    histories, _energy_bounds, burnup_values = read_mgxs_hdf5_histories(
        hdf5_path,
        h_factor_default=args.h_factor_default,
    )
    nstates = histories[0].nstates if histories else 0
    burnup_detail = "none" if burnup_values is None else str(len(burnup_values))
    print(
        f"preflight OK: mixtures={len(histories)} "
        f"state_points={nstates} burnup_axis={burnup_detail}"
    )

    if args.format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            hdf5_path,
            output_path,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    else:
        convert_mgxs_hdf5(
            hdf5_path,
            output_path,
            root_name=args.root_name,
            comment=args.comment,
            burnup=args.burnup,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    if args.keep_hdf5 is not None:
        print(f"kept HDF5: {hdf5_path}")
    print(f"wrote {args.format}: {output_path}")
    if args.summary_json is not None:
        summary = _summary_payload(
            args,
            recipe_path=recipe_summary.recipe_path,
            statepoint_path=recipe_summary.statepoint_path,
            hdf5_path=hdf5_path,
            hdf5_kept=hdf5_kept,
            output_path=output_path,
            mixture_names=[history.name for history in histories],
            nstates=nstates,
            burnup_values=burnup_values,
            energy_groups=export_summary.energy_groups,
            legendre_order=export_summary.legendre_order,
        )
        _write_json(args.summary_json, summary)
        print(f"wrote summary: {args.summary_json}")
    if args.run_dir is not None:
        _write_run_dir_manifest(args, hdf5_path, output_path, recipe_summary.recipe_path)
    return True


def _apply_run_dir_defaults(args: argparse.Namespace) -> None:
    if args.run_dir is None:
        return
    run_dir = args.run_dir
    if args.keep_hdf5 is None:
        args.keep_hdf5 = run_dir / "mgxs_library.h5"
    if args.output is None:
        args.output = str(run_dir / _default_output_name(args.format))
    if args.summary_json is None:
        args.summary_json = run_dir / "run_summary.json"
    if args.check and args.check_summary_json is None:
        args.check_summary_json = run_dir / "check_summary.json"
    if (args.adf_source is not None or args.build_flux_ratio_adf) and args.adf_summary_json is None:
        args.adf_summary_json = run_dir / "adf_summary.json"


def _prepare_run_dir(
    args: argparse.Namespace,
    output_path: Path,
    parser: argparse.ArgumentParser,
) -> None:
    if args.run_dir is None:
        return
    run_dir = args.run_dir
    managed_paths = [
        args.keep_hdf5,
        output_path,
        args.summary_json,
        run_dir / "manifest.json",
    ]
    recipe_destination = run_dir / args.recipe.name
    if not _same_path(args.recipe, recipe_destination):
        managed_paths.append(recipe_destination)
    if args.check:
        managed_paths.append(args.check_summary_json)
    if args.adf_source is not None:
        managed_paths.append(args.adf_summary_json)
        adf_source_destination = run_dir / args.adf_source.name
        if not _same_path(args.adf_source, adf_source_destination):
            managed_paths.append(adf_source_destination)
    if args.build_flux_ratio_adf:
        paths = _flux_ratio_adf_paths(args)
        if args.export_surface_flux:
            managed_paths.extend([paths["surface_flux"], paths["surface_flux_summary"]])
        if args.homogeneous_face_flux is None:
            managed_paths.extend(
                [
                    paths["low_order_driver"],
                    paths["low_order_driver_summary"],
                    paths["low_order_driver_check_summary"],
                    paths["homogeneous_face_flux"],
                    paths["homogeneous_face_flux_summary"],
                ]
            )
        else:
            homogeneous_source = _hdf5_reference_file(args.homogeneous_face_flux)
            homogeneous_destination = run_dir / homogeneous_source.name
            if not _same_path(homogeneous_source, homogeneous_destination):
                managed_paths.append(homogeneous_destination)
        managed_paths.extend([paths["adf_sidecar"], paths["adf_sidecar_summary"]])
        if args.adf_summary_json is not None:
            managed_paths.append(args.adf_summary_json)
        if args.adf_surface_flux is not None:
            surface_source = _hdf5_reference_file(args.adf_surface_flux)
            surface_destination = run_dir / surface_source.name
            if not _same_path(surface_source, surface_destination):
                managed_paths.append(surface_destination)
    for artifact in _extra_artifacts_from_args(args, parser):
        destination = run_dir / artifact.source.name
        if not _same_path(artifact.source, destination):
            managed_paths.append(destination)
    existing = [path for path in managed_paths if path is not None and path.exists()]
    if existing and not args.force_run_dir:
        rendered = ", ".join(str(path) for path in existing)
        parser.error(f"--run-dir managed artifacts already exist; use --force-run-dir: {rendered}")
    run_dir.mkdir(parents=True, exist_ok=True)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def _default_output_name(output_format: str) -> str:
    if output_format == "macrolib":
        return "out.macrolib.txt"
    return "out.mcompo.txt"


def _output_path(raw_output: str | None, output_format: str) -> Path:
    if raw_output:
        return Path(raw_output)
    return Path(_default_output_name(output_format))


def _inject_adf(args: argparse.Namespace, hdf5_path: Path, *, adf_source: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix=f"{hdf5_path.name}.adf.",
        dir=str(hdf5_path.parent),
    ) as tmpdir:
        augmented_path = Path(tmpdir) / hdf5_path.name
        augment_hdf5_with_adf(
            hdf5_path,
            adf_source=adf_source,
            output_h5=augmented_path,
            expected_faces=parse_faces(args.adf_faces),
            force=True,
            adf_kind=args.adf_kind,
            adf_real=args.adf_real,
            adf_source_label=args.adf_source_label,
            summary_json=args.adf_summary_json,
        )
        augmented_path.replace(hdf5_path)
    print(f"injected ADF into HDF5: {hdf5_path}")


def _build_flux_ratio_adf(
    args: argparse.Namespace,
    hdf5_path: Path,
    *,
    statepoint_path: Path | None,
) -> tuple[Path, list[ArtifactSpec]]:
    paths = _flux_ratio_adf_paths(args)
    faces = _flux_ratio_faces(args)
    face_widths = _parse_float_tuple(args.adf_face_widths, "--adf-face-widths")
    generated_artifacts: list[ArtifactSpec] = []

    if args.export_surface_flux:
        if statepoint_path is None:
            raise ValueError("--export-surface-flux requires a statepoint")
        export_openmc_surface_flux(
            statepoint_path,
            paths["surface_flux"],
            mgxs_h5=hdf5_path,
            tally_name=args.surface_flux_tally_name,
            mesh_shape=_parse_optional_int_pair(
                args.surface_flux_mesh_shape,
                "--surface-flux-mesh-shape",
            ),
            mu_edges=_parse_float_tuple(args.surface_flux_mu_edges, "--surface-flux-mu-edges"),
            face_area=args.surface_flux_face_area,
            face_names=faces,
            force=True,
            summary_json=paths["surface_flux_summary"],
        )
        surface_flux = paths["surface_flux"]
        generated_artifacts.extend(
            [
                ArtifactSpec(label="surface-flux", source=paths["surface_flux"]),
                ArtifactSpec(label="surface-flux-summary", source=paths["surface_flux_summary"]),
            ]
        )
    else:
        surface_flux = args.adf_surface_flux
        generated_artifacts.append(
            ArtifactSpec(label="surface-flux", source=_hdf5_reference_file(surface_flux))
        )

    if args.homogeneous_face_flux is None:
        create_low_order_driver(
            hdf5_path,
            paths["low_order_driver"],
            raw_driver=args.low_order_raw_driver,
            volume_flux=args.low_order_volume_flux,
            net_current=args.low_order_net_current,
            faces=faces,
            net_current_sign_convention=args.low_order_net_current_sign_convention,
            source_label=args.low_order_source_label,
            force=True,
            summary_json=paths["low_order_driver_summary"],
        )
        low_order_check = check_low_order_driver(
            hdf5_path,
            paths["low_order_driver"],
            faces=faces,
            face_widths=face_widths,
            summary_json=paths["low_order_driver_check_summary"],
        )
        if not low_order_check.ok:
            raise ValueError("low-order driver contract check failed")

        create_homogeneous_face_flux(
            hdf5_path,
            paths["homogeneous_face_flux"],
            volume_flux=paths["low_order_driver"],
            net_current=paths["low_order_driver"],
            faces=faces,
            face_widths=face_widths,
            force=True,
            summary_json=paths["homogeneous_face_flux_summary"],
        )
        homogeneous_face_flux = paths["homogeneous_face_flux"]
    else:
        homogeneous_face_flux = args.homogeneous_face_flux

    create_flux_ratio_adf_sidecar(
        hdf5_path,
        paths["adf_sidecar"],
        surface_flux=surface_flux,
        homogeneous_face_flux=homogeneous_face_flux,
        faces=faces,
        force=True,
        summary_json=paths["adf_sidecar_summary"],
        invalid_fill=args.adf_invalid_fill,
        clip_min=args.adf_clip_min,
        clip_max=args.adf_clip_max,
        adf_kind=args.adf_kind or "flux-ratio",
        adf_real=_optional_bool(args.adf_real, default=True),
        adf_source_label=(
            args.adf_source_label
            or "openmc2donjon-from-openmc flux-ratio ADF workflow"
        ),
    )

    if args.homogeneous_face_flux is None:
        generated_artifacts.extend(
            [
                ArtifactSpec(label="low-order-driver", source=paths["low_order_driver"]),
                ArtifactSpec(
                    label="low-order-driver-summary",
                    source=paths["low_order_driver_summary"],
                ),
                ArtifactSpec(
                    label="low-order-driver-check-summary",
                    source=paths["low_order_driver_check_summary"],
                ),
                ArtifactSpec(label="homogeneous-face-flux", source=paths["homogeneous_face_flux"]),
                ArtifactSpec(
                    label="homogeneous-face-flux-summary",
                    source=paths["homogeneous_face_flux_summary"],
                ),
            ]
        )
    else:
        generated_artifacts.append(
            ArtifactSpec(
                label="homogeneous-face-flux",
                source=_hdf5_reference_file(args.homogeneous_face_flux),
            )
        )
    generated_artifacts.append(
        ArtifactSpec(label="adf-sidecar-summary", source=paths["adf_sidecar_summary"])
    )
    return paths["adf_sidecar"], generated_artifacts


def _flux_ratio_adf_paths(args: argparse.Namespace) -> dict[str, Path]:
    run_dir = args.run_dir
    return {
        "surface_flux": run_dir / "openmc_surface_flux.h5",
        "surface_flux_summary": run_dir / "surface_flux_summary.json",
        "low_order_driver": run_dir / "low_order_driver.h5",
        "low_order_driver_summary": run_dir / "low_order_driver_summary.json",
        "low_order_driver_check_summary": run_dir / "low_order_driver_check_summary.json",
        "homogeneous_face_flux": run_dir / "homogeneous_face_flux.h5",
        "homogeneous_face_flux_summary": run_dir / "homogeneous_face_flux_summary.json",
        "adf_sidecar": run_dir / "adf_sidecar.h5",
        "adf_sidecar_summary": run_dir / "adf_sidecar_summary.json",
    }


def _effective_adf_source(args: argparse.Namespace) -> Path | None:
    generated = getattr(args, "_generated_adf_source", None)
    return generated or args.adf_source


def _write_run_dir_manifest(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    recipe_path: Path,
) -> None:
    artifacts = [ArtifactSpec(label="mgxs", source=hdf5_path)]
    if args.format == "macrolib":
        artifacts.append(ArtifactSpec(label="macrolib", source=output_path))
    else:
        artifacts.append(ArtifactSpec(label="mcompo", source=output_path))
    if args.summary_json is not None:
        artifacts.append(ArtifactSpec(label="run-summary", source=args.summary_json))
    if args.check and args.check_summary_json is not None:
        artifacts.append(ArtifactSpec(label="check-summary", source=args.check_summary_json))
    adf_source = _effective_adf_source(args)
    if adf_source is not None:
        artifacts.append(ArtifactSpec(label="adf-source", source=adf_source))
        if args.adf_summary_json is not None:
            artifacts.append(ArtifactSpec(label="adf-summary", source=args.adf_summary_json))
    artifacts.extend(getattr(args, "_generated_adf_artifacts", []))
    artifacts.extend(_extra_artifacts_from_args(args))
    artifacts.append(ArtifactSpec(label="recipe", source=recipe_path))
    bundle_artifacts(
        output_dir=args.run_dir,
        artifacts=artifacts,
        force=True,
    )


def _extra_artifacts_from_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
) -> list[ArtifactSpec]:
    artifacts: list[ArtifactSpec] = []
    for raw in args.extra_artifact:
        try:
            artifacts.append(parse_extra_artifact(raw))
        except ValueError as exc:
            if parser is not None:
                parser.error(f"--extra-artifact {raw!r}: {exc}")
            raise
    return artifacts


def _validate_flux_ratio_adf_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    dependent_options = (
        args.adf_surface_flux is not None
        or args.export_surface_flux
        or args.surface_flux_tally_name != DEFAULT_SURFACE_FLUX_TALLY_NAME
        or args.surface_flux_mesh_shape is not None
        or args.surface_flux_mu_edges is not None
        or args.surface_flux_face_area != 1.0
        or args.homogeneous_face_flux is not None
        or args.low_order_raw_driver is not None
        or args.low_order_volume_flux is not None
        or args.low_order_net_current is not None
        or args.low_order_net_current_sign_convention is not None
        or args.low_order_source_label != "external low-order driver"
        or args.adf_face_widths != "1.0"
        or args.adf_invalid_fill is not None
        or args.adf_clip_min is not None
        or args.adf_clip_max is not None
    )
    if not args.build_flux_ratio_adf:
        if dependent_options:
            parser.error(
                "flux-ratio ADF workflow options require --build-flux-ratio-adf"
            )
        return

    if args.run_dir is None:
        parser.error("--build-flux-ratio-adf requires --run-dir")
    if args.adf_source is not None:
        parser.error("--build-flux-ratio-adf creates --adf-source internally")
    if bool(args.export_surface_flux) == bool(args.adf_surface_flux):
        parser.error(
            "--build-flux-ratio-adf requires exactly one of "
            "--export-surface-flux or --adf-surface-flux"
        )
    if args.adf_surface_flux is not None:
        try:
            _hdf5_reference_file(args.adf_surface_flux)
        except ValueError as exc:
            parser.error(str(exc))
    if args.homogeneous_face_flux is not None:
        try:
            _hdf5_reference_file(args.homogeneous_face_flux)
        except ValueError as exc:
            parser.error(str(exc))
    if args.export_surface_flux:
        if args.statepoint is None and not args.dry_run:
            parser.error("--export-surface-flux requires --statepoint")
        if args.surface_flux_mu_edges is None:
            parser.error("--export-surface-flux requires --surface-flux-mu-edges")
        try:
            _parse_float_tuple(args.surface_flux_mu_edges, "--surface-flux-mu-edges")
            _parse_optional_int_pair(args.surface_flux_mesh_shape, "--surface-flux-mesh-shape")
        except ValueError as exc:
            parser.error(str(exc))
        if not (args.surface_flux_face_area > 0.0):
            parser.error("--surface-flux-face-area must be positive")
    has_raw_low_order = args.low_order_raw_driver is not None
    has_explicit_low_order = (
        args.low_order_volume_flux is not None and args.low_order_net_current is not None
    )
    has_homogeneous_face_flux = args.homogeneous_face_flux is not None
    if has_homogeneous_face_flux and (has_raw_low_order or has_explicit_low_order):
        parser.error(
            "--homogeneous-face-flux cannot be combined with low-order driver inputs"
        )
    if has_homogeneous_face_flux and args.low_order_net_current_sign_convention is not None:
        parser.error(
            "--low-order-net-current-sign-convention requires low-order driver inputs"
        )
    if has_homogeneous_face_flux and args.low_order_source_label != "external low-order driver":
        parser.error("--low-order-source-label requires low-order driver inputs")
    if has_homogeneous_face_flux and args.adf_face_widths != "1.0":
        parser.error("--adf-face-widths requires low-order driver inputs")
    if not (has_homogeneous_face_flux or has_raw_low_order or has_explicit_low_order):
        parser.error(
            "--build-flux-ratio-adf requires --homogeneous-face-flux, "
            "--low-order-raw-driver, or both --low-order-volume-flux and "
            "--low-order-net-current"
        )
    if args.low_order_volume_flux is None and args.low_order_net_current is not None:
        parser.error("--low-order-net-current also requires --low-order-volume-flux")
    if args.low_order_volume_flux is not None and args.low_order_net_current is None:
        parser.error("--low-order-volume-flux also requires --low-order-net-current")
    try:
        _flux_ratio_faces(args)
        _parse_float_tuple(args.adf_face_widths, "--adf-face-widths")
    except ValueError as exc:
        parser.error(str(exc))
    if (args.adf_clip_min is None) ^ (args.adf_clip_max is None):
        parser.error("--adf-clip-min and --adf-clip-max must be supplied together")
    if args.adf_clip_min is not None and args.adf_clip_max is not None:
        if args.adf_clip_min <= 0.0:
            parser.error("--adf-clip-min must be positive")
        if args.adf_clip_min > args.adf_clip_max:
            parser.error("--adf-clip-min must be <= --adf-clip-max")
    if args.adf_invalid_fill is not None and args.adf_invalid_fill <= 0.0:
        parser.error("--adf-invalid-fill must be positive")


def _hdf5_reference_file(reference: str | Path) -> Path:
    raw = str(reference)
    path = raw.split("::", 1)[0]
    if not path:
        raise ValueError(f"empty HDF5 reference path: {reference}")
    return Path(path)


def _flux_ratio_faces(args: argparse.Namespace) -> tuple[str, ...]:
    return parse_faces(args.adf_faces) or DEFAULT_CARTESIAN_FACES


def _parse_float_tuple(raw: str | None, label: str) -> tuple[float, ...]:
    if raw is None:
        raise ValueError(f"{label} is required")
    values: list[float] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError as exc:
            raise ValueError(f"{label} must contain numeric values") from exc
    if not values:
        raise ValueError(f"{label} must contain at least one value")
    return tuple(values)


def _parse_optional_int_pair(raw: str | None, label: str) -> tuple[int, int] | None:
    if raw is None:
        return None
    values: list[int] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        try:
            values.append(int(token))
        except ValueError as exc:
            raise ValueError(f"{label} must contain integer values") from exc
    if len(values) != 2:
        raise ValueError(f"{label} must have exactly two entries: Y,X")
    if values[0] <= 0 or values[1] <= 0:
        raise ValueError(f"{label} entries must be positive")
    return (values[0], values[1])


def _optional_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    return raw == "true"


def _render_optional_list(values: list[str] | None) -> str:
    if not values:
        return "all"
    return ", ".join(values)


def _render_optional_value(value: object) -> str:
    if value is None:
        return "none"
    return str(value)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _summary_payload(
    args: argparse.Namespace,
    *,
    recipe_path: Path,
    statepoint_path: Path | None,
    hdf5_path: Path,
    hdf5_kept: bool,
    output_path: Path,
    mixture_names: list[str],
    nstates: int,
    burnup_values,
    energy_groups: int,
    legendre_order: int,
) -> dict[str, object]:
    burnup_summary: dict[str, object] = {"present": burnup_values is not None}
    if burnup_values is not None:
        values = [float(value) for value in burnup_values]
        burnup_summary.update(
            {
                "count": len(values),
                "values": values,
            }
        )

    return {
        "schema": FROM_OPENMC_SUMMARY_SCHEMA,
        "package_version": __version__,
        "recipe": str(recipe_path),
        "statepoint": None if statepoint_path is None else str(statepoint_path),
        "loaded_statepoint": not args.no_load_statepoint,
        "hdf5": str(hdf5_path),
        "hdf5_kept": hdf5_kept,
        "output": str(output_path),
        "format": args.format,
        "energy_groups": energy_groups,
        "legendre_order": legendre_order,
        "mixture_count": len(mixture_names),
        "mixture_names": mixture_names,
        "state_points": nstates,
        "burnup_axis": burnup_summary,
        "checked": bool(args.check),
        "check_passed": True if args.check else None,
        "check_summary_json": (
            str(args.check_summary_json)
            if args.check and args.check_summary_json is not None
            else None
        ),
        "selected_mixtures": args.mixture or None,
        "root_name": args.root_name if args.format == "multicompo" else None,
        "single_point_burnup": args.burnup,
        "h_factor_default": args.h_factor_default,
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
