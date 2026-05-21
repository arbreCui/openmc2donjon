"""SPH workflow used by the one-step OpenMC CLI."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from .bundle import ArtifactSpec
from .sph_augment import augment_hdf5_with_sph, create_macrolib_sph_sidecar


def print_dry_run_sph(args: argparse.Namespace) -> None:
    if args.sph_source is not None:
        print(f"  sph_source: {args.sph_source} (not read)")
        if args.sph_summary_json is None:
            print("  sph_summary_json: none")
        else:
            print(f"  sph_summary_json: {args.sph_summary_json} (not written)")
    elif args.sph_macrolib is not None:
        paths = _sph_paths(args)
        print(f"  sph_macrolib: {args.sph_macrolib} (not read)")
        print(f"  sph_sidecar: {paths['sph_sidecar']} (not written)")
        print(f"  sph_sidecar_summary: {paths['sph_sidecar_summary']} (not written)")
        if args.sph_summary_json is None:
            print("  sph_summary_json: none")
        else:
            print(f"  sph_summary_json: {args.sph_summary_json} (not written)")
    else:
        print("  sph_source: none")


def sph_managed_paths(args: argparse.Namespace) -> list[Path | None]:
    run_dir = args.run_dir
    managed_paths: list[Path | None] = []
    if args.sph_source is not None:
        managed_paths.append(args.sph_summary_json)
        _append_run_dir_copy(managed_paths, run_dir, args.sph_source)
    if args.sph_macrolib is not None:
        paths = _sph_paths(args)
        managed_paths.extend(
            [
                args.sph_summary_json,
                paths["sph_sidecar"],
                paths["sph_sidecar_summary"],
            ]
        )
        _append_run_dir_copy(managed_paths, run_dir, args.sph_macrolib)
    return managed_paths


def apply_sph_workflow(
    args: argparse.Namespace,
    hdf5_path: Path,
) -> tuple[Path | None, list[ArtifactSpec]]:
    sph_source = args.sph_source
    artifacts: list[ArtifactSpec] = []
    if args.sph_macrolib is not None:
        sph_source, artifacts = _build_macrolib_sph(args, hdf5_path)
    if sph_source is not None:
        _inject_sph(args, hdf5_path, sph_source=sph_source)
    return sph_source, artifacts


def validate_sph_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if args.sph_source is not None and args.sph_macrolib is not None:
        parser.error("--sph-source and --sph-macrolib are mutually exclusive")
    has_sph_source = args.sph_source is not None or args.sph_macrolib is not None
    dependent_options = (
        args.sph_kind is not None
        or args.sph_real is not None
        or args.sph_applied is not None
        or args.sph_source_label is not None
        or args.sph_summary_json is not None
    )
    if not has_sph_source and dependent_options:
        parser.error("SPH provenance/summary options require --sph-source or --sph-macrolib")
    if args.sph_macrolib is not None and args.run_dir is None:
        parser.error("--sph-macrolib requires --run-dir so its generated sidecar is bundled")


def _inject_sph(args: argparse.Namespace, hdf5_path: Path, *, sph_source: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix=f"{hdf5_path.name}.sph.",
        dir=str(hdf5_path.parent),
    ) as tmpdir:
        augmented_path = Path(tmpdir) / hdf5_path.name
        augment_hdf5_with_sph(
            hdf5_path,
            sph_source=sph_source,
            output_h5=augmented_path,
            force=True,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real,
            sph_applied=args.sph_applied,
            sph_source_label=args.sph_source_label,
            summary_json=args.sph_summary_json,
        )
        augmented_path.replace(hdf5_path)
    print(f"injected SPH into HDF5: {hdf5_path}")


def _build_macrolib_sph(
    args: argparse.Namespace,
    hdf5_path: Path,
) -> tuple[Path, list[ArtifactSpec]]:
    paths = _sph_paths(args)
    create_macrolib_sph_sidecar(
        hdf5_path,
        paths["sph_sidecar"],
        macrolib_ascii=args.sph_macrolib,
        force=True,
        sph_kind=args.sph_kind or "macrolib-nsph",
        sph_real=_optional_bool(args.sph_real, default=True),
        sph_applied=_optional_bool(args.sph_applied, default=False),
        summary_json=paths["sph_sidecar_summary"],
    )
    return paths["sph_sidecar"], [
        ArtifactSpec(label="sph-macrolib", source=args.sph_macrolib),
        ArtifactSpec(label="sph-sidecar-summary", source=paths["sph_sidecar_summary"]),
    ]


def _sph_paths(args: argparse.Namespace) -> dict[str, Path]:
    run_dir = args.run_dir
    return {
        "sph_sidecar": run_dir / "sph_sidecar.h5",
        "sph_sidecar_summary": run_dir / "sph_sidecar_summary.json",
    }


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


def _optional_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    return raw == "true"
