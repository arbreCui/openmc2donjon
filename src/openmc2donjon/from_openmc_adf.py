"""Flux-ratio ADF workflow used by the one-step OpenMC CLI."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .adf_augment import augment_hdf5_with_adf, parse_faces
from .adf_sidecar import DEFAULT_CARTESIAN_FACES, create_flux_ratio_adf_sidecar
from .bundle import ArtifactSpec
from .face_flux_check import check_face_flux
from .homogeneous_face_flux import create_homogeneous_face_flux
from .low_order_driver import check_low_order_driver, create_low_order_driver
from .openmc_surface_flux import (
    DEFAULT_TALLY_NAME as DEFAULT_SURFACE_FLUX_TALLY_NAME,
    export_openmc_surface_flux,
)


@dataclass(frozen=True, slots=True)
class AdfConfig:
    run_dir: Path | None
    statepoint: Path | None
    dry_run: bool
    adf_source: Path | None
    adf_faces: str | None
    adf_summary_json: Path | None
    adf_kind: str | None
    adf_real: str | None
    adf_source_label: str | None
    build_flux_ratio_adf: bool
    adf_surface_flux: str | Path | None
    export_surface_flux: bool
    surface_flux_tally_name: str
    surface_flux_mesh_shape: str | None
    surface_flux_mu_edges: str | None
    surface_flux_face_area: float
    homogeneous_face_flux: str | Path | None
    low_order_raw_driver: str | Path | None
    low_order_volume_flux: str | Path | None
    low_order_net_current: str | Path | None
    low_order_net_current_sign_convention: str | None
    low_order_source_label: str
    adf_face_widths: str
    adf_invalid_fill: float | None
    adf_clip_min: float | None
    adf_clip_max: float | None


def print_dry_run_adf(config: AdfConfig) -> None:
    if config.adf_source is None:
        print("  adf_source: none")
    else:
        print(f"  adf_source: {config.adf_source} (not read)")
        print(f"  adf_faces: {_render_optional_value(config.adf_faces)}")
        if config.adf_summary_json is None:
            print("  adf_summary_json: none")
        else:
            print(f"  adf_summary_json: {config.adf_summary_json} (not written)")
    if config.build_flux_ratio_adf:
        paths = _flux_ratio_adf_paths(config)
        print("  flux_ratio_adf: enabled")
        if config.export_surface_flux:
            print(f"    surface_flux: {paths['surface_flux']} (not written)")
            print(f"    surface_flux_summary: {paths['surface_flux_summary']} (not written)")
            print(f"    surface_flux_tally: {config.surface_flux_tally_name}")
            print(f"    surface_flux_mesh_shape: {_render_optional_value(config.surface_flux_mesh_shape)}")
            print(f"    surface_flux_mu_edges: {_render_optional_value(config.surface_flux_mu_edges)}")
            print(f"    surface_flux_face_area: {config.surface_flux_face_area}")
        else:
            print(f"    surface_flux: {config.adf_surface_flux} (not read)")
        print(
            "    low_order_raw_driver: "
            f"{_render_optional_value(config.low_order_raw_driver)}"
        )
        if config.homogeneous_face_flux is not None:
            print(f"    homogeneous_face_flux: {config.homogeneous_face_flux} (not read)")
        else:
            print(
                "    low_order_volume_flux: "
                f"{_render_optional_value(config.low_order_volume_flux)}"
            )
            print(
                "    low_order_net_current: "
                f"{_render_optional_value(config.low_order_net_current)}"
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


def flux_ratio_adf_managed_paths(config: AdfConfig) -> list[Path | None]:
    run_dir = config.run_dir
    if run_dir is None:
        return []
    paths = _flux_ratio_adf_paths(config)
    managed_paths: list[Path | None] = [
        paths["face_flux_check_summary"],
        paths["adf_sidecar"],
        paths["adf_sidecar_summary"],
        config.adf_summary_json,
    ]
    if config.export_surface_flux:
        managed_paths.extend([paths["surface_flux"], paths["surface_flux_summary"]])
    elif config.adf_surface_flux is not None:
        _append_run_dir_copy(managed_paths, run_dir, _hdf5_reference_file(config.adf_surface_flux))

    if config.homogeneous_face_flux is None:
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
            _hdf5_reference_file(config.homogeneous_face_flux),
        )
    return managed_paths


def build_flux_ratio_adf(
    config: AdfConfig,
    hdf5_path: Path,
    *,
    statepoint_path: Path | None,
) -> tuple[Path, list[ArtifactSpec]]:
    paths = _flux_ratio_adf_paths(config)
    faces = _flux_ratio_faces(config)
    face_widths = _parse_float_tuple(config.adf_face_widths, "--adf-face-widths")
    generated_artifacts: list[ArtifactSpec] = []

    if config.export_surface_flux:
        surface_flux = _export_surface_flux_for_adf(
            config,
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
        surface_flux = config.adf_surface_flux
        generated_artifacts.append(
            ArtifactSpec(label="surface-flux", source=_hdf5_reference_file(surface_flux))
        )

    if config.homogeneous_face_flux is None:
        homogeneous_face_flux = _build_homogeneous_face_flux_for_adf(
            config,
            paths,
            hdf5_path,
            faces=faces,
            face_widths=face_widths,
        )
    else:
        homogeneous_face_flux = config.homogeneous_face_flux

    _check_and_create_flux_ratio_adf(
        config,
        paths,
        hdf5_path,
        surface_flux=surface_flux,
        homogeneous_face_flux=homogeneous_face_flux,
        faces=faces,
    )

    if config.homogeneous_face_flux is None:
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
                source=_hdf5_reference_file(config.homogeneous_face_flux),
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


def inject_adf(config: AdfConfig, hdf5_path: Path, *, adf_source: Path) -> None:
    with tempfile.TemporaryDirectory(
        prefix=f"{hdf5_path.name}.adf.",
        dir=str(hdf5_path.parent),
    ) as tmpdir:
        augmented_path = Path(tmpdir) / hdf5_path.name
        augment_hdf5_with_adf(
            hdf5_path,
            adf_source=adf_source,
            output_h5=augmented_path,
            expected_faces=parse_faces(config.adf_faces),
            force=True,
            adf_kind=config.adf_kind,
            adf_real=config.adf_real,
            adf_source_label=config.adf_source_label,
            summary_json=config.adf_summary_json,
        )
        augmented_path.replace(hdf5_path)
    print(f"injected ADF into HDF5: {hdf5_path}")


def validate_flux_ratio_adf_config(config: AdfConfig) -> None:
    if not config.build_flux_ratio_adf:
        if _has_flux_ratio_adf_options(config):
            raise ValueError("flux-ratio ADF workflow options require --build-flux-ratio-adf")
        return

    _validate_flux_ratio_adf_required_config(config)
    _validate_flux_ratio_surface_config(config)
    _validate_flux_ratio_low_order_config(config)
    _validate_flux_ratio_numeric_config(config)


def _export_surface_flux_for_adf(
    config: AdfConfig,
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
        tally_name=config.surface_flux_tally_name,
        mesh_shape=_parse_optional_int_pair(
            config.surface_flux_mesh_shape,
            "--surface-flux-mesh-shape",
        ),
        mu_edges=_parse_float_tuple(config.surface_flux_mu_edges, "--surface-flux-mu-edges"),
        face_area=config.surface_flux_face_area,
        face_names=faces,
        force=True,
        summary_json=paths["surface_flux_summary"],
    )
    return paths["surface_flux"]


def _build_homogeneous_face_flux_for_adf(
    config: AdfConfig,
    paths: dict[str, Path],
    hdf5_path: Path,
    *,
    faces: tuple[str, ...],
    face_widths: tuple[float, ...],
) -> Path:
    create_low_order_driver(
        hdf5_path,
        paths["low_order_driver"],
        raw_driver=config.low_order_raw_driver,
        volume_flux=config.low_order_volume_flux,
        net_current=config.low_order_net_current,
        faces=faces,
        net_current_sign_convention=config.low_order_net_current_sign_convention,
        source_label=config.low_order_source_label,
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
    config: AdfConfig,
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
        invalid_fill=config.adf_invalid_fill,
        clip_min=config.adf_clip_min,
        clip_max=config.adf_clip_max,
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
        invalid_fill=config.adf_invalid_fill,
        clip_min=config.adf_clip_min,
        clip_max=config.adf_clip_max,
        adf_kind=config.adf_kind or "flux-ratio",
        adf_real=_optional_bool(config.adf_real, default=True),
        adf_source_label=(
            config.adf_source_label
            or "openmc2donjon-from-openmc flux-ratio ADF workflow"
        ),
    )


def _flux_ratio_adf_paths(config: AdfConfig) -> dict[str, Path]:
    run_dir = config.run_dir
    if run_dir is None:
        raise ValueError("--build-flux-ratio-adf requires --run-dir")
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


def _has_flux_ratio_adf_options(config: AdfConfig) -> bool:
    return (
        config.adf_surface_flux is not None
        or config.export_surface_flux
        or config.surface_flux_tally_name != DEFAULT_SURFACE_FLUX_TALLY_NAME
        or config.surface_flux_mesh_shape is not None
        or config.surface_flux_mu_edges is not None
        or config.surface_flux_face_area != 1.0
        or config.homogeneous_face_flux is not None
        or config.low_order_raw_driver is not None
        or config.low_order_volume_flux is not None
        or config.low_order_net_current is not None
        or config.low_order_net_current_sign_convention is not None
        or config.low_order_source_label != "external low-order driver"
        or config.adf_face_widths != "1.0"
        or config.adf_invalid_fill is not None
        or config.adf_clip_min is not None
        or config.adf_clip_max is not None
    )


def _validate_flux_ratio_adf_required_config(config: AdfConfig) -> None:
    if config.run_dir is None:
        raise ValueError("--build-flux-ratio-adf requires --run-dir")
    if config.adf_source is not None:
        raise ValueError("--build-flux-ratio-adf creates --adf-source internally")
    if bool(config.export_surface_flux) == bool(config.adf_surface_flux):
        raise ValueError(
            "--build-flux-ratio-adf requires exactly one of "
            "--export-surface-flux or --adf-surface-flux"
        )
    if config.adf_surface_flux is not None:
        _validate_hdf5_reference_arg(config.adf_surface_flux)
    if config.homogeneous_face_flux is not None:
        _validate_hdf5_reference_arg(config.homogeneous_face_flux)


def _validate_flux_ratio_surface_config(config: AdfConfig) -> None:
    if config.export_surface_flux:
        if config.statepoint is None and not config.dry_run:
            raise ValueError("--export-surface-flux requires --statepoint")
        if config.surface_flux_mu_edges is None:
            raise ValueError("--export-surface-flux requires --surface-flux-mu-edges")
        try:
            _parse_float_tuple(config.surface_flux_mu_edges, "--surface-flux-mu-edges")
            _parse_optional_int_pair(config.surface_flux_mesh_shape, "--surface-flux-mesh-shape")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not (config.surface_flux_face_area > 0.0):
            raise ValueError("--surface-flux-face-area must be positive")


def _validate_flux_ratio_low_order_config(config: AdfConfig) -> None:
    has_raw_low_order = config.low_order_raw_driver is not None
    has_explicit_low_order = (
        config.low_order_volume_flux is not None and config.low_order_net_current is not None
    )
    has_homogeneous_face_flux = config.homogeneous_face_flux is not None
    if has_homogeneous_face_flux and (has_raw_low_order or has_explicit_low_order):
        raise ValueError(
            "--homogeneous-face-flux cannot be combined with low-order driver inputs"
        )
    if has_homogeneous_face_flux and config.low_order_net_current_sign_convention is not None:
        raise ValueError(
            "--low-order-net-current-sign-convention requires low-order driver inputs"
        )
    if has_homogeneous_face_flux and config.low_order_source_label != "external low-order driver":
        raise ValueError("--low-order-source-label requires low-order driver inputs")
    if has_homogeneous_face_flux and config.adf_face_widths != "1.0":
        raise ValueError("--adf-face-widths requires low-order driver inputs")
    if not (has_homogeneous_face_flux or has_raw_low_order or has_explicit_low_order):
        raise ValueError(
            "--build-flux-ratio-adf requires --homogeneous-face-flux, "
            "--low-order-raw-driver, or both --low-order-volume-flux and "
            "--low-order-net-current"
        )
    if config.low_order_volume_flux is None and config.low_order_net_current is not None:
        raise ValueError("--low-order-net-current also requires --low-order-volume-flux")
    if config.low_order_volume_flux is not None and config.low_order_net_current is None:
        raise ValueError("--low-order-volume-flux also requires --low-order-net-current")


def _validate_flux_ratio_numeric_config(config: AdfConfig) -> None:
    try:
        _flux_ratio_faces(config)
        _parse_float_tuple(config.adf_face_widths, "--adf-face-widths")
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if (config.adf_clip_min is None) ^ (config.adf_clip_max is None):
        raise ValueError("--adf-clip-min and --adf-clip-max must be supplied together")
    if config.adf_clip_min is not None and config.adf_clip_max is not None:
        if config.adf_clip_min <= 0.0:
            raise ValueError("--adf-clip-min must be positive")
        if config.adf_clip_min > config.adf_clip_max:
            raise ValueError("--adf-clip-min must be <= --adf-clip-max")
    if config.adf_invalid_fill is not None and config.adf_invalid_fill <= 0.0:
        raise ValueError("--adf-invalid-fill must be positive")


def _validate_hdf5_reference_arg(reference: str | Path) -> None:
    _hdf5_reference_file(reference)


def _hdf5_reference_file(reference: str | Path) -> Path:
    raw = str(reference)
    path = raw.split("::", 1)[0]
    if not path:
        raise ValueError(f"empty HDF5 reference path: {reference}")
    return Path(path)


def _flux_ratio_faces(config: AdfConfig) -> tuple[str, ...]:
    return parse_faces(config.adf_faces) or DEFAULT_CARTESIAN_FACES


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
