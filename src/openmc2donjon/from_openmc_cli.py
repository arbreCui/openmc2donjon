"""One-step OpenMC recipe/statepoint to DONJON ASCII CLI."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from . import __version__
from .from_openmc_summary import FROM_OPENMC_SUMMARY_SCHEMA
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5, read_mgxs_hdf5_histories
from .openmc_statepoint import dry_run_openmc_statepoint_recipe, export_openmc_statepoint_recipe
from .recipe_dry_run_report import print_recipe_dry_run_summary


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
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run:
        _run_dry_run(args)
        return 0
    if args.statepoint is None and not args.no_load_statepoint:
        parser.error("--statepoint is required unless --no-load-statepoint is set")

    output_path = _output_path(args.output, args.format)
    if args.keep_hdf5 is not None:
        return 0 if _run_pipeline(args, args.keep_hdf5, output_path, hdf5_kept=True) else 1
    else:
        with tempfile.TemporaryDirectory(prefix="openmc2donjon_") as tmpdir:
            ok = _run_pipeline(args, Path(tmpdir) / "mgxs_library.h5", output_path, hdf5_kept=False)
            return 0 if ok else 1


def _run_dry_run(args: argparse.Namespace) -> None:
    output_path = _output_path(args.output, args.format)
    hdf5_path = args.keep_hdf5
    summary = dry_run_openmc_statepoint_recipe(
        args.recipe,
        statepoint_path=args.statepoint,
        load_statepoint=args.statepoint is not None and not args.no_load_statepoint,
        output_path=hdf5_path,
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
        if args.check_summary_json is None:
            print("    check_summary_json: none")
        else:
            print(f"    check_summary_json: {args.check_summary_json} (not written)")
    else:
        print("  check: disabled")


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
        overwrite=not args.no_overwrite_hdf5,
    )
    export_summary = recipe_summary.output
    print(
        f"exported {len(export_summary.domains)} domains, "
        f"{export_summary.energy_groups} groups, P{export_summary.legendre_order} "
        f"from recipe {recipe_summary.recipe_path}"
    )

    if args.check:
        ok = run_preflight(
            [hdf5_path],
            output_format=args.format,
            output_path=output_path,
            require_adf=args.require_adf,
            expected_adf_faces=args.expected_adf_faces,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
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
    return True


def _output_path(raw_output: str | None, output_format: str) -> Path:
    if raw_output:
        return Path(raw_output)
    if output_format == "macrolib":
        return Path("out.macrolib.txt")
    return Path("out.mcompo.txt")


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
