"""Run-directory packaging for the one-step OpenMC CLI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .bundle import (
    ArtifactSpec,
    bundle_artifacts,
    parse_extra_artifact,
    validate_bundle,
)
from .from_openmc_adf import flux_ratio_adf_managed_paths
from .from_openmc_sph import sph_managed_paths
from .handoff_summary import write_handoff_summary


@dataclass(slots=True)
class GeneratedArtifacts:
    adf_source: Path | None = None
    adf_artifacts: list[ArtifactSpec] = field(default_factory=list)
    sph_source: Path | None = None
    sph_artifacts: list[ArtifactSpec] = field(default_factory=list)


def apply_run_dir_defaults(args: argparse.Namespace) -> None:
    if args.run_dir is None:
        return
    run_dir = args.run_dir
    if args.keep_hdf5 is None:
        args.keep_hdf5 = run_dir / "mgxs_library.h5"
    if args.output is None:
        args.output = str(run_dir / default_output_name(args.format))
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


def validate_run_dir_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
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
    extra_artifacts_from_args(args, parser)


def print_dry_run_artifacts(args: argparse.Namespace) -> None:
    if args.extra_artifact:
        print("  extra_artifacts:")
        for artifact in extra_artifacts_from_args(args):
            print(f"    {artifact.label}: {artifact.source} (not copied)")
    else:
        print("  extra_artifacts: none")
    if args.summary_json is None:
        print("  summary_json: none")
    else:
        print(f"  summary_json: {args.summary_json} (not written)")


def print_dry_run_run_dir(args: argparse.Namespace) -> None:
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


def prepare_run_dir(
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


def finalize_run_dir(
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
            adf_enabled=effective_adf_source(args, generated) is not None,
            sph_enabled=effective_sph_source(args, generated) is not None,
        )
        print(f"wrote handoff summary: {args.handoff_summary_json}")
    return report is None or report.ok


def output_path(raw_output: str | None, output_format: str) -> Path:
    if raw_output:
        return Path(raw_output)
    return Path(default_output_name(output_format))


def default_output_name(output_format: str) -> str:
    if output_format == "macrolib":
        return "out.macrolib.txt"
    return "out.mcompo.txt"


def effective_adf_source(
    args: argparse.Namespace,
    generated: GeneratedArtifacts | None = None,
) -> Path | None:
    if generated is not None and generated.adf_source is not None:
        return generated.adf_source
    return args.adf_source


def effective_sph_source(
    args: argparse.Namespace,
    generated: GeneratedArtifacts | None = None,
) -> Path | None:
    if generated is not None and generated.sph_source is not None:
        return generated.sph_source
    return args.sph_source


def extra_artifacts_from_args(
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
    for artifact in extra_artifacts_from_args(args, parser):
        _append_run_dir_copy(managed_paths, run_dir, artifact.source)
    return managed_paths


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
    adf_source = effective_adf_source(args, generated)
    if adf_source is not None:
        artifacts.append(ArtifactSpec(label="adf-source", source=adf_source))
        if args.adf_summary_json is not None:
            artifacts.append(ArtifactSpec(label="adf-summary", source=args.adf_summary_json))
    artifacts.extend(generated.adf_artifacts)
    sph_source = effective_sph_source(args, generated)
    if sph_source is not None:
        artifacts.append(ArtifactSpec(label="sph-source", source=sph_source))
        if args.sph_summary_json is not None:
            artifacts.append(ArtifactSpec(label="sph-summary", source=args.sph_summary_json))
    artifacts.extend(generated.sph_artifacts)
    artifacts.extend(extra_artifacts_from_args(args))
    artifacts.append(ArtifactSpec(label="recipe", source=recipe_path))
    bundle_artifacts(
        output_dir=args.run_dir,
        artifacts=artifacts,
        force=True,
    )


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
