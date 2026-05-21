"""One-step OpenMC recipe/statepoint to DONJON ASCII CLI."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .adf_augment import augment_hdf5_with_adf, parse_faces
from .bundle import (
    ArtifactSpec,
    bundle_artifacts,
    parse_extra_artifact,
    validate_bundle,
)
from .from_openmc_adf import (
    build_flux_ratio_adf,
    flux_ratio_adf_managed_paths,
    print_dry_run_adf,
    validate_flux_ratio_adf_args,
)
from .from_openmc_parser import build_parser
from .from_openmc_sph import (
    apply_sph_workflow,
    print_dry_run_sph,
    sph_managed_paths,
    validate_sph_args,
)
from .from_openmc_summary import FROM_OPENMC_SUMMARY_SCHEMA
from .handoff_summary import write_handoff_summary
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import convert_mgxs_hdf5, read_mgxs_hdf5_histories
from .openmc_statepoint import (
    RecipeExportSummary,
    StatepointLoadError,
    dry_run_openmc_statepoint_recipe,
    export_openmc_statepoint_recipe,
)
from .recipe_dry_run_report import (
    print_recipe_dry_run_summary,
    print_strict_dry_run_decision,
)


@dataclass(slots=True)
class GeneratedArtifacts:
    adf_source: Path | None = None
    adf_artifacts: list[ArtifactSpec] = field(default_factory=list)
    sph_source: Path | None = None
    sph_artifacts: list[ArtifactSpec] = field(default_factory=list)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _normalize_args(args)
    _validate_args(args, parser)
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


def _normalize_args(args: argparse.Namespace) -> None:
    if args.build_flux_ratio_adf:
        args.check = True
        args.require_adf = True
    if args.sph_source is not None or args.sph_macrolib is not None:
        args.check = True
        args.require_sph = True
    _apply_run_dir_defaults(args)


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.bundle_validation_summary_json is not None and args.run_dir is None:
        parser.error("--bundle-validation-summary-json requires --run-dir")
    if args.handoff_summary_json is not None and args.run_dir is None:
        parser.error("--handoff-summary-json requires --run-dir")
    if args.extra_artifact and args.run_dir is None:
        parser.error("--extra-artifact requires --run-dir")
    if args.no_validate_bundle and args.bundle_validation_summary_json is not None:
        parser.error("--bundle-validation-summary-json cannot be used with --no-validate-bundle")
    if args.no_handoff_summary and args.handoff_summary_json is not None:
        parser.error("--handoff-summary-json cannot be used with --no-handoff-summary")
    _extra_artifacts_from_args(args, parser)
    if args.expected_adf_faces is None and args.adf_faces is not None:
        args.expected_adf_faces = args.adf_faces
    validate_flux_ratio_adf_args(args, parser)
    validate_sph_args(args, parser)
    if args.strict_dry_run and not args.dry_run:
        parser.error("--strict-dry-run requires --dry-run")


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
    _print_dry_run_output(args, output_path, hdf5_path)
    print_dry_run_adf(args)
    print_dry_run_sph(args)
    _print_dry_run_artifacts(args)
    _print_dry_run_checks(args)
    _print_dry_run_run_dir(args)
    if args.strict_dry_run:
        return print_strict_dry_run_decision(summary)
    return True


def _print_dry_run_output(
    args: argparse.Namespace,
    output_path: Path,
    hdf5_path: Path | None,
) -> None:
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


def _print_dry_run_artifacts(args: argparse.Namespace) -> None:
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


def _print_dry_run_checks(args: argparse.Namespace) -> None:
    if args.check:
        print("  check: enabled after HDF5 export")
        print(f"    require_volume: {_yes_no(args.require_volume)}")
        print(f"    require_transport_dataset: {_yes_no(args.require_transport_dataset)}")
        print(f"    require_adf: {_yes_no(args.require_adf)}")
        print(f"    require_sph: {_yes_no(args.require_sph)}")
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


def _print_dry_run_run_dir(args: argparse.Namespace) -> None:
    if args.run_dir is not None:
        if args.no_validate_bundle:
            print("  bundle_validation_summary_json: disabled")
        else:
            print(
                "  bundle_validation_summary_json: "
                f"{args.bundle_validation_summary_json} (not written)"
            )
        if args.no_handoff_summary:
            print("  handoff_summary_json: disabled")
        else:
            print(f"  handoff_summary_json: {args.handoff_summary_json} (not written)")


def _run_pipeline(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    *,
    hdf5_kept: bool,
) -> bool:
    generated = GeneratedArtifacts()
    recipe_summary = _export_pipeline_hdf5(args, hdf5_path)
    export_summary = recipe_summary.output

    _apply_pipeline_corrections(args, hdf5_path, recipe_summary, generated)
    if not _run_pipeline_preflight(args, hdf5_path, output_path, hdf5_kept=hdf5_kept):
        return False

    histories, _energy_bounds, burnup_values = read_mgxs_hdf5_histories(
        hdf5_path,
        h_factor_default=args.h_factor_default,
    )
    nstates = histories[0].nstates if histories else 0
    _print_pipeline_readiness(histories, nstates, burnup_values)
    _convert_pipeline_hdf5(args, hdf5_path, output_path)
    summary = _write_pipeline_summary(
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
    return _finalize_run_dir(
        args,
        hdf5_path=hdf5_path,
        output_path=output_path,
        recipe_path=recipe_summary.recipe_path,
        statepoint_path=recipe_summary.statepoint_path,
        summary=summary,
        generated=generated,
    )


def _export_pipeline_hdf5(
    args: argparse.Namespace,
    hdf5_path: Path,
) -> RecipeExportSummary:
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
    return recipe_summary


def _apply_pipeline_corrections(
    args: argparse.Namespace,
    hdf5_path: Path,
    recipe_summary: RecipeExportSummary,
    generated: GeneratedArtifacts,
) -> None:
    if args.build_flux_ratio_adf:
        generated.adf_source, generated.adf_artifacts = build_flux_ratio_adf(
            args,
            hdf5_path,
            statepoint_path=recipe_summary.statepoint_path,
        )

    adf_source = _effective_adf_source(args, generated)
    if adf_source is not None:
        _inject_adf(args, hdf5_path, adf_source=adf_source)

    generated.sph_source, generated.sph_artifacts = apply_sph_workflow(args, hdf5_path)


def _run_pipeline_preflight(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    *,
    hdf5_kept: bool,
) -> bool:
    if not args.check:
        return True
    ok = run_preflight(
        [hdf5_path],
        output_format=args.format,
        output_path=output_path,
        require_adf=args.require_adf,
        require_sph=args.require_sph,
        expected_adf_faces=args.expected_adf_faces,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        scatter_row_balance_warn=args.scatter_row_balance_warn,
        scatter_row_balance_fail=args.scatter_row_balance_fail,
        summary_json=args.check_summary_json,
    )
    if not ok and hdf5_kept:
        print(f"kept HDF5: {hdf5_path}")
    return ok


def _print_pipeline_readiness(histories, nstates: int, burnup_values) -> None:
    burnup_detail = "none" if burnup_values is None else str(len(burnup_values))
    print(
        f"preflight OK: mixtures={len(histories)} "
        f"state_points={nstates} burnup_axis={burnup_detail}"
    )


def _convert_pipeline_hdf5(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
) -> None:
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


def _write_pipeline_summary(
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
    summary = _summary_payload(
        args,
        recipe_path=recipe_path,
        statepoint_path=statepoint_path,
        hdf5_path=hdf5_path,
        hdf5_kept=hdf5_kept,
        output_path=output_path,
        mixture_names=mixture_names,
        nstates=nstates,
        burnup_values=burnup_values,
        energy_groups=energy_groups,
        legendre_order=legendre_order,
    )
    if args.summary_json is not None:
        _write_json(args.summary_json, summary)
        print(f"wrote summary: {args.summary_json}")
    return summary


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
    if (args.sph_source is not None or args.sph_macrolib is not None) and args.sph_summary_json is None:
        args.sph_summary_json = run_dir / "sph_summary.json"
    if not args.no_validate_bundle and args.bundle_validation_summary_json is None:
        args.bundle_validation_summary_json = run_dir / "bundle_validation_summary.json"
    if not args.no_handoff_summary and args.handoff_summary_json is None:
        args.handoff_summary_json = run_dir / "handoff_summary.json"


def _prepare_run_dir(
    args: argparse.Namespace,
    output_path: Path,
    parser: argparse.ArgumentParser,
) -> None:
    if args.run_dir is None:
        return
    managed_paths = _managed_run_dir_paths(args, output_path, parser)
    existing = [path for path in managed_paths if path is not None and path.exists()]
    if existing and not args.force_run_dir:
        rendered = ", ".join(str(path) for path in existing)
        parser.error(f"--run-dir managed artifacts already exist; use --force-run-dir: {rendered}")
    args.run_dir.mkdir(parents=True, exist_ok=True)


def _managed_run_dir_paths(
    args: argparse.Namespace,
    output_path: Path,
    parser: argparse.ArgumentParser,
) -> list[Path | None]:
    run_dir = args.run_dir
    managed_paths = [
        args.keep_hdf5,
        output_path,
        args.summary_json,
        run_dir / "manifest.json",
    ]
    if not args.no_validate_bundle:
        managed_paths.append(args.bundle_validation_summary_json)
    if not args.no_handoff_summary:
        managed_paths.append(args.handoff_summary_json)
    _append_run_dir_copy(managed_paths, run_dir, args.recipe)
    if args.check:
        managed_paths.append(args.check_summary_json)
    if args.adf_source is not None:
        managed_paths.append(args.adf_summary_json)
        _append_run_dir_copy(managed_paths, run_dir, args.adf_source)
    managed_paths.extend(sph_managed_paths(args))
    if args.build_flux_ratio_adf:
        managed_paths.extend(flux_ratio_adf_managed_paths(args))
    for artifact in _extra_artifacts_from_args(args, parser):
        _append_run_dir_copy(managed_paths, run_dir, artifact.source)
    return managed_paths


def _append_run_dir_copy(
    paths: list[Path | None],
    run_dir: Path,
    source: Path,
) -> None:
    destination = run_dir / source.name
    if not _same_path(source, destination):
        paths.append(destination)


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


def _effective_adf_source(
    args: argparse.Namespace,
    generated: GeneratedArtifacts | None = None,
) -> Path | None:
    if generated is not None and generated.adf_source is not None:
        return generated.adf_source
    return args.adf_source


def _effective_sph_source(
    args: argparse.Namespace,
    generated: GeneratedArtifacts | None = None,
) -> Path | None:
    if generated is not None and generated.sph_source is not None:
        return generated.sph_source
    return args.sph_source


def _finalize_run_dir(
    args: argparse.Namespace,
    *,
    hdf5_path: Path,
    output_path: Path,
    recipe_path: Path,
    statepoint_path: Path | None,
    summary: dict[str, object],
    generated: GeneratedArtifacts,
) -> bool:
    if args.run_dir is None:
        return True

    manifest_path = args.run_dir / "manifest.json"
    _write_run_dir_manifest(
        args,
        hdf5_path,
        output_path,
        recipe_path,
        generated=generated,
    )
    report = None
    if not args.no_validate_bundle:
        report = validate_bundle(
            manifest_path,
            summary_json=args.bundle_validation_summary_json,
        )
    if not args.no_handoff_summary:
        write_handoff_summary(
            args.handoff_summary_json,
            package_version=__version__,
            run_dir=args.run_dir,
            summary=summary,
            recipe_path=recipe_path,
            statepoint_path=statepoint_path,
            hdf5_path=hdf5_path,
            output_path=output_path,
            output_format=args.format,
            run_summary_json=args.summary_json,
            check_summary_json=args.check_summary_json if args.check else None,
            manifest_path=manifest_path,
            bundle_validation_summary_json=(
                args.bundle_validation_summary_json
                if not args.no_validate_bundle
                else None
            ),
            bundle_validation_passed=None if report is None else report.ok,
            bundle_validation_decision=None if report is None else report.decision,
            adf_enabled=_effective_adf_source(args, generated) is not None,
            sph_enabled=_effective_sph_source(args, generated) is not None,
        )
        print(f"wrote handoff summary: {args.handoff_summary_json}")
    return report is None or report.ok


def _write_run_dir_manifest(
    args: argparse.Namespace,
    hdf5_path: Path,
    output_path: Path,
    recipe_path: Path,
    *,
    generated: GeneratedArtifacts,
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
    adf_source = _effective_adf_source(args, generated)
    if adf_source is not None:
        artifacts.append(ArtifactSpec(label="adf-source", source=adf_source))
        if args.adf_summary_json is not None:
            artifacts.append(ArtifactSpec(label="adf-summary", source=args.adf_summary_json))
    artifacts.extend(generated.adf_artifacts)
    sph_source = _effective_sph_source(args, generated)
    if sph_source is not None:
        artifacts.append(ArtifactSpec(label="sph-source", source=sph_source))
        if args.sph_summary_json is not None:
            artifacts.append(ArtifactSpec(label="sph-summary", source=args.sph_summary_json))
    artifacts.extend(generated.sph_artifacts)
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
