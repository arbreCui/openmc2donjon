"""Preflight checks for fixed-OpenMC SPH loop flux mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .donjon_flux import (
    _diagnostic_warnings,
    _load_ids_from_map_h5,
    _map_diagnostics,
    _normalize_scalar_flux_ids,
)


SCHEMA = "openmc2donjon.sph-loop-flux-map-preflight.v1"
PASS_DECISION = "openmc2donjon_sph_loop_flux_map_preflight_passed"
FAIL_DECISION = "openmc2donjon_sph_loop_flux_map_preflight_failed"


@dataclass(frozen=True)
class SphLoopFluxMapPreflightReport:
    input_h5: Path
    reference_flux: str
    map_h5: Path | None
    map_kind: str
    mixture_names: tuple[str, ...]
    energy_groups: int
    scalar_flux_ids: tuple[int, ...]
    minimum_required_flux_unknown_count: int | None
    mixture_flux_map: tuple[tuple[str, int], ...]
    duplicate_scalar_flux_ids: tuple[tuple[int, tuple[str, ...]], ...]
    mesh_shape: tuple[int, ...] | None
    mesh_cell_count: int | None
    mesh_zero_or_negative_id_count: int | None
    mesh_unknown_mixture_names: tuple[str, ...]
    mesh_missing_mixture_names: tuple[str, ...]
    mesh_mixture_cell_counts: tuple[tuple[str, int], ...]
    reference_flux_source: Path | None
    reference_flux_dataset: str | None
    reference_flux_shape: tuple[int, ...] | None
    reference_flux_group_count: int | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    passed: bool

    @property
    def decision(self) -> str:
        return PASS_DECISION if self.passed else FAIL_DECISION


def build_flux_map_preflight_report(
    *,
    input_h5: Path,
    reference_flux: str,
    map_h5: Path | None,
    scalar_flux_ids: dict[str, int] | None,
    scalar_flux_column: int,
) -> SphLoopFluxMapPreflightReport:
    input_path = Path(input_h5)
    mixture_names, energy_groups = _read_mgxs_metadata(input_path)
    errors: list[str] = []
    warnings: list[str] = []

    ids = np.asarray([], dtype=int)
    mesh_payload: dict[str, np.ndarray] | None = None
    map_kind = "missing"
    if map_h5 is not None and scalar_flux_ids is not None:
        errors.append("map_h5 and scalar_flux_map are mutually exclusive")
    elif map_h5 is None and scalar_flux_ids is None:
        errors.append("missing scalar flux map; use map_h5 or scalar_flux_map")
    else:
        try:
            if map_h5 is not None:
                ids, mesh_payload, map_kind = _load_ids_from_map_h5(
                    Path(map_h5),
                    mixture_names=mixture_names,
                    scalar_flux_column=scalar_flux_column,
                )
            else:
                ids = _normalize_scalar_flux_ids(
                    scalar_flux_ids or {},
                    mixture_names=mixture_names,
                )
                map_kind = "scalar_flux_map"
        except ValueError as exc:
            errors.append(str(exc))

    map_diagnostics = _empty_map_diagnostics()
    if ids.size:
        map_diagnostics = _map_diagnostics(
            mixture_names=mixture_names,
            scalar_flux_ids=ids,
            flux_unknown_count=int(np.max(ids)),
            mesh_payload=mesh_payload,
        )
        warnings.extend(_diagnostic_warnings(map_diagnostics))
        errors.extend(_map_diagnostic_errors(map_diagnostics))

    reference_report = _inspect_reference_flux(
        reference_flux,
        energy_groups=energy_groups,
    )
    warnings.extend(reference_report["warnings"])
    errors.extend(reference_report["errors"])

    scalar_ids = tuple(int(value) for value in ids)
    return SphLoopFluxMapPreflightReport(
        input_h5=input_path,
        reference_flux=reference_flux,
        map_h5=None if map_h5 is None else Path(map_h5),
        map_kind=map_kind,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        scalar_flux_ids=scalar_ids,
        minimum_required_flux_unknown_count=(
            None if not scalar_ids else int(max(scalar_ids))
        ),
        mixture_flux_map=tuple(
            (mixture, int(scalar_id))
            for mixture, scalar_id in zip(mixture_names, scalar_ids)
        ),
        duplicate_scalar_flux_ids=map_diagnostics["duplicate_scalar_flux_ids"],
        mesh_shape=map_diagnostics["mesh_shape"],
        mesh_cell_count=map_diagnostics["mesh_cell_count"],
        mesh_zero_or_negative_id_count=map_diagnostics[
            "mesh_zero_or_negative_id_count"
        ],
        mesh_unknown_mixture_names=map_diagnostics["mesh_unknown_mixture_names"],
        mesh_missing_mixture_names=_mesh_missing_mixture_names(map_diagnostics),
        mesh_mixture_cell_counts=map_diagnostics["mesh_mixture_cell_counts"],
        reference_flux_source=reference_report["source"],
        reference_flux_dataset=reference_report["dataset"],
        reference_flux_shape=reference_report["shape"],
        reference_flux_group_count=reference_report["group_count"],
        warnings=tuple(warnings),
        errors=tuple(errors),
        passed=not errors,
    )


def payload(report: SphLoopFluxMapPreflightReport) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "decision": report.decision,
        "passed": report.passed,
        "input_h5": str(report.input_h5),
        "reference_flux": report.reference_flux,
        "map_h5": None if report.map_h5 is None else str(report.map_h5),
        "map_kind": report.map_kind,
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "energy_groups": report.energy_groups,
        "scalar_flux_ids": list(report.scalar_flux_ids),
        "minimum_required_flux_unknown_count": (
            report.minimum_required_flux_unknown_count
        ),
        "mixture_flux_map": [
            {"mixture": mixture, "scalar_flux_id": scalar_id}
            for mixture, scalar_id in report.mixture_flux_map
        ],
        "duplicate_scalar_flux_ids": [
            {"scalar_flux_id": scalar_id, "mixtures": list(mixtures)}
            for scalar_id, mixtures in report.duplicate_scalar_flux_ids
        ],
        "mesh_shape": None if report.mesh_shape is None else list(report.mesh_shape),
        "mesh_cell_count": report.mesh_cell_count,
        "mesh_zero_or_negative_id_count": report.mesh_zero_or_negative_id_count,
        "mesh_unknown_mixture_names": list(report.mesh_unknown_mixture_names),
        "mesh_missing_mixture_names": list(report.mesh_missing_mixture_names),
        "mesh_mixture_cell_counts": [
            {"mixture": mixture, "cell_count": count}
            for mixture, count in report.mesh_mixture_cell_counts
        ],
        "reference_flux_source": (
            None if report.reference_flux_source is None else str(report.reference_flux_source)
        ),
        "reference_flux_dataset": report.reference_flux_dataset,
        "reference_flux_shape": (
            None
            if report.reference_flux_shape is None
            else list(report.reference_flux_shape)
        ),
        "reference_flux_group_count": report.reference_flux_group_count,
        "warnings": list(report.warnings),
        "errors": list(report.errors),
    }


def format_failure(report: SphLoopFluxMapPreflightReport) -> str:
    if report.passed:
        return "flux-map preflight passed"
    return "flux-map preflight failed: " + "; ".join(report.errors)


def _read_mgxs_metadata(path: Path) -> tuple[tuple[str, ...], int]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 is missing /mixtures")
        mixture_names = tuple(str(name) for name in h5["mixtures"].keys())
        if "energy_groups" in h5.attrs:
            energy_groups = int(h5.attrs["energy_groups"])
        elif "energy_bounds" in h5:
            energy_groups = int(h5["energy_bounds"].shape[0]) - 1
        else:
            raise ValueError("input HDF5 must define energy_groups or energy_bounds")
    if not mixture_names:
        raise ValueError("input HDF5 contains no mixtures")
    if energy_groups <= 0:
        raise ValueError("energy group count must be positive")
    return mixture_names, energy_groups


def _empty_map_diagnostics() -> dict[str, Any]:
    return {
        "duplicate_scalar_flux_ids": (),
        "flux_unknown_count": 0,
        "mesh_shape": None,
        "mesh_cell_count": None,
        "mesh_zero_or_negative_id_count": None,
        "mesh_unknown_mixture_names": (),
        "mesh_mixture_cell_counts": (),
    }


def _map_diagnostic_errors(map_diagnostics: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    duplicates = map_diagnostics["duplicate_scalar_flux_ids"]
    if duplicates:
        rendered = "; ".join(
            f"id {scalar_id}: {','.join(mixtures)}"
            for scalar_id, mixtures in duplicates
        )
        errors.append(f"duplicate scalar flux id mapping ({rendered})")
    zero_count = map_diagnostics["mesh_zero_or_negative_id_count"]
    if zero_count:
        errors.append(
            f"mesh map contains {zero_count} nonpositive scalar flux id cell(s)"
        )
    unknown = map_diagnostics["mesh_unknown_mixture_names"]
    if unknown:
        errors.append(
            "mesh map contains name(s) not present in the MGXS mixtures: "
            + ", ".join(unknown)
        )
    missing = _mesh_missing_mixture_names(map_diagnostics)
    if missing:
        errors.append("mesh map is missing mixture(s): " + ", ".join(missing))
    return tuple(errors)


def _mesh_missing_mixture_names(map_diagnostics: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        mixture
        for mixture, count in map_diagnostics["mesh_mixture_cell_counts"]
        if count <= 0
    )


def _inspect_reference_flux(
    source: str,
    *,
    energy_groups: int,
) -> dict[str, Any]:
    path, dataset = _split_dataset_reference(source)
    warnings: list[str] = []
    errors: list[str] = []
    shape = None
    group_count = None
    selected_dataset = dataset
    if not path.exists():
        return {
            "source": path,
            "dataset": selected_dataset,
            "shape": shape,
            "group_count": group_count,
            "warnings": (),
            "errors": (f"reference flux source does not exist: {path}",),
        }
    if not _looks_like_hdf5(path) and selected_dataset is None:
        warnings.append("reference flux is not HDF5; group count not preflighted")
        return {
            "source": path,
            "dataset": selected_dataset,
            "shape": shape,
            "group_count": group_count,
            "warnings": tuple(warnings),
            "errors": (),
        }

    import h5py

    try:
        with h5py.File(path, "r") as h5:
            if selected_dataset is None:
                selected_dataset = _select_reference_dataset(h5)
            if selected_dataset is None:
                errors.append(f"{path}: reference flux dataset not found")
            elif selected_dataset not in h5:
                errors.append(f"{path}: reference flux dataset not found: /{selected_dataset}")
            elif hasattr(h5[selected_dataset], "keys"):
                errors.append(f"{path}: reference flux path is a group: /{selected_dataset}")
            else:
                obj = h5[selected_dataset]
                shape = tuple(int(value) for value in obj.shape)
                if not shape:
                    errors.append(f"{path}: reference flux dataset is scalar")
                else:
                    group_count = int(shape[-1])
                    if group_count != energy_groups:
                        errors.append(
                            "reference flux group count does not match MGXS: "
                            f"{group_count} != {energy_groups}"
                        )
    except OSError as exc:
        errors.append(f"cannot read reference flux HDF5 {path}: {exc}")
    return {
        "source": path,
        "dataset": selected_dataset,
        "shape": shape,
        "group_count": group_count,
        "warnings": tuple(warnings),
        "errors": tuple(errors),
    }


def _select_reference_dataset(root: Any) -> str | None:
    for candidate in (
        "openmc_volume_flux",
        "reference_flux",
        "volume_flux",
        "flux",
        "scalar_flux",
        "phi",
    ):
        if candidate in root and not hasattr(root[candidate], "keys"):
            return candidate
    return None


def _split_dataset_reference(reference: str) -> tuple[Path, str | None]:
    raw = str(reference)
    if "::" not in raw:
        return Path(raw), None
    path, dataset = raw.split("::", 1)
    dataset = dataset.strip("/")
    if not dataset:
        raise ValueError(f"empty dataset reference in {raw!r}")
    return Path(path), dataset


def _looks_like_hdf5(path: Path) -> bool:
    return path.suffix.lower() in {".h5", ".hdf5", ".hdf"}
