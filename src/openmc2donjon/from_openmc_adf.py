"""Flux-ratio ADF workflow used by the one-step OpenMC CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from .adf_augment import parse_faces
from .adf_sidecar import DEFAULT_CARTESIAN_FACES, create_flux_ratio_adf_sidecar
from .bundle import ArtifactSpec
from .face_flux_check import check_face_flux
from .homogeneous_face_flux import create_homogeneous_face_flux
from .low_order_driver import check_low_order_driver, create_low_order_driver
from .openmc_surface_flux import (
    DEFAULT_TALLY_NAME as DEFAULT_SURFACE_FLUX_TALLY_NAME,
    export_openmc_surface_flux,
)


def print_dry_run_adf(args: argparse.Namespace) -> None:
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
        print(
            f"    face_flux_check_summary: "
            f"{paths['face_flux_check_summary']} (not written)"
        )
        print(f"    adf_sidecar: {paths['adf_sidecar']} (not written)")
        print(f"    adf_sidecar_summary: {paths['adf_sidecar_summary']} (not written)")
    else:
        print("  flux_ratio_adf: disabled")


def flux_ratio_adf_managed_paths(args: argparse.Namespace) -> list[Path | None]:
    run_dir = args.run_dir
    paths = _flux_ratio_adf_paths(args)
    managed_paths: list[Path | None] = [
        paths["face_flux_check_summary"],
        paths["adf_sidecar"],
        paths["adf_sidecar_summary"],
        args.adf_summary_json,
    ]
    if args.export_surface_flux:
        managed_paths.extend([paths["surface_flux"], paths["surface_flux_summary"]])
    elif args.adf_surface_flux is not None:
        _append_run_dir_copy(managed_paths, run_dir, _hdf5_reference_file(args.adf_surface_flux))

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
        _append_run_dir_copy(
            managed_paths,
            run_dir,
            _hdf5_reference_file(args.homogeneous_face_flux),
        )
    return managed_paths


def build_flux_ratio_adf(
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
        surface_flux = _export_surface_flux_for_adf(
            args,
            paths,
            hdf5_path,
            statepoint_path=statepoint_path,
            faces=faces,
        )
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
        homogeneous_face_flux = _build_homogeneous_face_flux_for_adf(
            args,
            paths,
            hdf5_path,
            faces=faces,
            face_widths=face_widths,
        )
    else:
        homogeneous_face_flux = args.homogeneous_face_flux

    _check_and_create_flux_ratio_adf(
        args,
        paths,
        hdf5_path,
        surface_flux=surface_flux,
        homogeneous_face_flux=homogeneous_face_flux,
        faces=faces,
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
        ArtifactSpec(
            label="face-flux-check-summary",
            source=paths["face_flux_check_summary"],
        )
    )
    generated_artifacts.append(
        ArtifactSpec(label="adf-sidecar-summary", source=paths["adf_sidecar_summary"])
    )
    return paths["adf_sidecar"], generated_artifacts


def validate_flux_ratio_adf_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if not args.build_flux_ratio_adf:
        if _has_flux_ratio_adf_options(args):
            parser.error(
                "flux-ratio ADF workflow options require --build-flux-ratio-adf"
            )
        return

    _validate_flux_ratio_adf_required_args(args, parser)
    _validate_flux_ratio_surface_args(args, parser)
    _validate_flux_ratio_low_order_args(args, parser)
    _validate_flux_ratio_numeric_args(args, parser)


def _export_surface_flux_for_adf(
    args: argparse.Namespace,
    paths: dict[str, Path],
    hdf5_path: Path,
    *,
    statepoint_path: Path | None,
    faces: tuple[str, ...],
) -> Path:
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
    return paths["surface_flux"]


def _build_homogeneous_face_flux_for_adf(
    args: argparse.Namespace,
    paths: dict[str, Path],
    hdf5_path: Path,
    *,
    faces: tuple[str, ...],
    face_widths: tuple[float, ...],
) -> Path:
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
    return paths["homogeneous_face_flux"]


def _check_and_create_flux_ratio_adf(
    args: argparse.Namespace,
    paths: dict[str, Path],
    hdf5_path: Path,
    *,
    surface_flux: Path | str,
    homogeneous_face_flux: Path | str,
    faces: tuple[str, ...],
) -> None:
    face_flux_check = check_face_flux(
        hdf5_path,
        surface_flux=surface_flux,
        homogeneous_face_flux=homogeneous_face_flux,
        faces=faces,
        invalid_fill=args.adf_invalid_fill,
        clip_min=args.adf_clip_min,
        clip_max=args.adf_clip_max,
        summary_json=paths["face_flux_check_summary"],
    )
    if not face_flux_check.ok:
        raise ValueError("face-flux contract check failed")

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
        "face_flux_check_summary": run_dir / "face_flux_check_summary.json",
        "adf_sidecar": run_dir / "adf_sidecar.h5",
        "adf_sidecar_summary": run_dir / "adf_sidecar_summary.json",
    }


def _has_flux_ratio_adf_options(args: argparse.Namespace) -> bool:
    return (
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


def _validate_flux_ratio_adf_required_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
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
        _validate_hdf5_reference_arg(args.adf_surface_flux, parser)
    if args.homogeneous_face_flux is not None:
        _validate_hdf5_reference_arg(args.homogeneous_face_flux, parser)


def _validate_flux_ratio_surface_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
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


def _validate_flux_ratio_low_order_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
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


def _validate_flux_ratio_numeric_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
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


def _validate_hdf5_reference_arg(
    reference: str | Path,
    parser: argparse.ArgumentParser,
) -> None:
    try:
        _hdf5_reference_file(reference)
    except ValueError as exc:
        parser.error(str(exc))


def _hdf5_reference_file(reference: str | Path) -> Path:
    raw = str(reference)
    path = raw.split("::", 1)[0]
    if not path:
        raise ValueError(f"empty HDF5 reference path: {reference}")
    return Path(path)


def _flux_ratio_faces(args: argparse.Namespace) -> tuple[str, ...]:
    return parse_faces(args.adf_faces) or DEFAULT_CARTESIAN_FACES


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


def _render_optional_value(value: object) -> str:
    if value is None:
        return "none"
    return str(value)
