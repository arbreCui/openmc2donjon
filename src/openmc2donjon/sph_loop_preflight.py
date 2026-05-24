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
from .constants import MGXS_DONJON_GROUP_ORDER
from .energy_groups import (
    MESH_ABSOLUTE_TOLERANCE,
    MESH_RELATIVE_TOLERANCE,
    energy_bounds_order,
    energy_bounds_sha256,
    identify_mesh,
    validate_energy_bounds_internal,
)
from .hdf5_names import read_mixture_names
from .mgxs_physics_checks import evaluate_mgxs_physics


SCHEMA = "openmc2donjon.sph-loop-flux-map-preflight.v1"
PASS_DECISION = "openmc2donjon_sph_loop_flux_map_preflight_passed"
FAIL_DECISION = "openmc2donjon_sph_loop_flux_map_preflight_failed"
H_FACTOR_DATASETS = (
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)
MGXS_STD_DEV_DATASETS = (
    "total",
    "absorption",
    "fission",
    "nu_fission",
    "chi",
    "transport_total",
    "inverse_velocity",
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
    "scatter_matrix",
)


@dataclass(frozen=True)
class SphLoopFluxMapPreflightReport:
    input_h5: Path
    reference_flux: str
    map_h5: Path | None
    map_kind: str
    mixture_names: tuple[str, ...]
    energy_groups: int
    mgxs_declared_mixture_order: bool
    mgxs_energy_bounds_present: bool
    mgxs_energy_bounds_order: str | None
    mgxs_energy_bounds_sha256: str | None
    mgxs_energy_bounds_error_count: int
    mgxs_energy_mesh_id: str | None
    mgxs_energy_mesh_name: str | None
    mgxs_energy_mesh_tolerance: float
    mgxs_energy_bounds_local_count: int
    mgxs_energy_bounds_consistency_error_count: int
    mgxs_scatter_row_balance_checked: int
    mgxs_scatter_row_balance_max_rel: float | None
    mgxs_scatter_row_balance_max_abs: float | None
    mgxs_scatter_row_balance_worst: str | None
    mgxs_chi_checked: int
    mgxs_chi_sum_max_abs_error: float | None
    mgxs_chi_sum_worst: str | None
    mgxs_chi_error_count: int
    mgxs_nu_ratio_checked_bins: int
    mgxs_nu_ratio_min: float | None
    mgxs_nu_ratio_max: float | None
    mgxs_nu_ratio_worst: str | None
    mgxs_nu_ratio_warning_count: int
    mgxs_adf_calculations: int
    mgxs_adf_faces: tuple[str, ...]
    mgxs_adf_face_error_count: int
    mgxs_transport_p1_checked: int
    mgxs_transport_p1_max_rel: float | None
    mgxs_transport_p1_max_abs: float | None
    mgxs_transport_p1_worst: str | None
    mgxs_transport_p1_error_count: int
    mgxs_source_domain_indices: tuple[int | None, ...]
    mgxs_source_domain_order_errors: tuple[str, ...]
    mgxs_calculations: int
    mgxs_volume_attributes: int
    mgxs_volume_defaulted: int
    mgxs_volume_nonpositive: int
    mgxs_fissionable_calculations: int
    mgxs_h_factor_datasets: int
    mgxs_h_factor_missing: int
    mgxs_h_factor_invalid: int
    mgxs_std_dev_datasets: int
    mgxs_std_dev_expected_datasets: int
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
    reference_flux_group_order: str | None
    reference_flux_mixture_names: tuple[str, ...]
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
    require_mgxs_domain_order: bool = False,
    require_mgxs_energy_bounds: bool = False,
    require_known_mesh: bool = False,
    mesh_tolerance: float = MESH_RELATIVE_TOLERANCE,
    require_mgxs_energy_bounds_consistency: bool = False,
    max_mgxs_scatter_row_balance_rel: float | None = None,
    max_mgxs_chi_sum_error: float | None = None,
    require_mgxs_adf_face_consistency: bool = False,
    max_mgxs_transport_p1_rel: float | None = None,
) -> SphLoopFluxMapPreflightReport:
    input_path = Path(input_h5)
    mgxs_metadata = _read_mgxs_metadata(
        input_path,
        mesh_tolerance=mesh_tolerance,
        energy_bounds_consistency=require_mgxs_energy_bounds_consistency,
        scatter_row_balance_rel=max_mgxs_scatter_row_balance_rel,
        chi_sum_tolerance=max_mgxs_chi_sum_error,
        require_adf_face_consistency=require_mgxs_adf_face_consistency,
        transport_p1_rel=max_mgxs_transport_p1_rel,
    )
    mixture_names = mgxs_metadata["mixture_names"]
    energy_groups = mgxs_metadata["energy_groups"]
    errors: list[str] = []
    warnings: list[str] = []
    if require_mgxs_domain_order:
        errors.extend(mgxs_metadata["source_domain_order_errors"])
    if require_mgxs_energy_bounds and not mgxs_metadata["energy_bounds_present"]:
        errors.append("/energy_bounds dataset is required for production SPH mapping")
    if (
        require_known_mesh
        and mgxs_metadata["energy_bounds_present"]
        and not mgxs_metadata["energy_bounds_errors"]
        and mgxs_metadata["energy_mesh_id"] is None
    ):
        errors.append(
            "/energy_bounds does not match a bundled known energy mesh "
            f"within rtol={mesh_tolerance:g}"
        )
    errors.extend(mgxs_metadata["energy_bounds_errors"])
    errors.extend(mgxs_metadata["energy_bounds_consistency_errors"])
    errors.extend(mgxs_metadata["scatter_row_balance_errors"])
    errors.extend(mgxs_metadata["chi_errors"])
    errors.extend(mgxs_metadata["adf_face_errors"])
    errors.extend(mgxs_metadata["transport_p1_errors"])
    errors.extend(mgxs_metadata["volume_errors"])
    errors.extend(mgxs_metadata["h_factor_errors"])
    warnings.extend(mgxs_metadata["energy_bounds_warnings"])
    warnings.extend(mgxs_metadata["scatter_row_balance_warnings"])
    warnings.extend(mgxs_metadata["nu_ratio_warnings"])
    if mgxs_metadata["volume_defaulted"]:
        warnings.append(
            f"{mgxs_metadata['volume_defaulted']}/"
            f"{mgxs_metadata['calculations']} MGXS calculation(s) are missing "
            "volume; converter readers will use default volume 1.0"
        )
    if mgxs_metadata["h_factor_missing"]:
        warnings.append(
            f"{mgxs_metadata['h_factor_missing']}/"
            f"{mgxs_metadata['fissionable_calculations']} fissionable MGXS "
            "calculation(s) are missing H-FACTOR/kappa_fission"
        )

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
        mixture_names=mixture_names,
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
        mgxs_declared_mixture_order=mgxs_metadata["declared_mixture_order"],
        mgxs_energy_bounds_present=mgxs_metadata["energy_bounds_present"],
        mgxs_energy_bounds_order=mgxs_metadata["energy_bounds_order"],
        mgxs_energy_bounds_sha256=mgxs_metadata["energy_bounds_sha256"],
        mgxs_energy_bounds_error_count=len(mgxs_metadata["energy_bounds_errors"]),
        mgxs_energy_mesh_id=mgxs_metadata["energy_mesh_id"],
        mgxs_energy_mesh_name=mgxs_metadata["energy_mesh_name"],
        mgxs_energy_mesh_tolerance=float(mesh_tolerance),
        mgxs_energy_bounds_local_count=mgxs_metadata[
            "energy_bounds_local_count"
        ],
        mgxs_energy_bounds_consistency_error_count=len(
            mgxs_metadata["energy_bounds_consistency_errors"]
        ),
        mgxs_scatter_row_balance_checked=mgxs_metadata[
            "scatter_row_balance_checked"
        ],
        mgxs_scatter_row_balance_max_rel=mgxs_metadata[
            "scatter_row_balance_max_rel"
        ],
        mgxs_scatter_row_balance_max_abs=mgxs_metadata[
            "scatter_row_balance_max_abs"
        ],
        mgxs_scatter_row_balance_worst=mgxs_metadata[
            "scatter_row_balance_worst"
        ],
        mgxs_chi_checked=mgxs_metadata["chi_checked"],
        mgxs_chi_sum_max_abs_error=mgxs_metadata["chi_sum_max_abs_error"],
        mgxs_chi_sum_worst=mgxs_metadata["chi_sum_worst"],
        mgxs_chi_error_count=len(mgxs_metadata["chi_errors"]),
        mgxs_nu_ratio_checked_bins=mgxs_metadata["nu_ratio_checked_bins"],
        mgxs_nu_ratio_min=mgxs_metadata["nu_ratio_min"],
        mgxs_nu_ratio_max=mgxs_metadata["nu_ratio_max"],
        mgxs_nu_ratio_worst=mgxs_metadata["nu_ratio_worst"],
        mgxs_nu_ratio_warning_count=mgxs_metadata["nu_ratio_warning_count"],
        mgxs_adf_calculations=mgxs_metadata["adf_calculations"],
        mgxs_adf_faces=mgxs_metadata["adf_faces"],
        mgxs_adf_face_error_count=len(mgxs_metadata["adf_face_errors"]),
        mgxs_transport_p1_checked=mgxs_metadata["transport_p1_checked"],
        mgxs_transport_p1_max_rel=mgxs_metadata["transport_p1_max_rel"],
        mgxs_transport_p1_max_abs=mgxs_metadata["transport_p1_max_abs"],
        mgxs_transport_p1_worst=mgxs_metadata["transport_p1_worst"],
        mgxs_transport_p1_error_count=len(mgxs_metadata["transport_p1_errors"]),
        mgxs_source_domain_indices=mgxs_metadata["source_domain_indices"],
        mgxs_source_domain_order_errors=mgxs_metadata["source_domain_order_errors"],
        mgxs_calculations=mgxs_metadata["calculations"],
        mgxs_volume_attributes=mgxs_metadata["volume_attributes"],
        mgxs_volume_defaulted=mgxs_metadata["volume_defaulted"],
        mgxs_volume_nonpositive=mgxs_metadata["volume_nonpositive"],
        mgxs_fissionable_calculations=mgxs_metadata["fissionable_calculations"],
        mgxs_h_factor_datasets=mgxs_metadata["h_factor_datasets"],
        mgxs_h_factor_missing=mgxs_metadata["h_factor_missing"],
        mgxs_h_factor_invalid=mgxs_metadata["h_factor_invalid"],
        mgxs_std_dev_datasets=mgxs_metadata["std_dev_datasets"],
        mgxs_std_dev_expected_datasets=mgxs_metadata["std_dev_expected_datasets"],
        scalar_flux_ids=scalar_ids,
        minimum_required_flux_unknown_count=(
            None if not scalar_ids else int(max(scalar_ids))
        ),
        mixture_flux_map=tuple(
            (mixture, int(scalar_id))
            for mixture, scalar_id in zip(mixture_names, scalar_ids, strict=True)
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
        reference_flux_group_order=reference_report["group_order"],
        reference_flux_mixture_names=reference_report["mixture_names"],
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
        "mgxs_declared_mixture_order": report.mgxs_declared_mixture_order,
        "mgxs_energy_bounds_present": report.mgxs_energy_bounds_present,
        "mgxs_energy_bounds_order": report.mgxs_energy_bounds_order,
        "mgxs_energy_bounds_sha256": report.mgxs_energy_bounds_sha256,
        "mgxs_energy_bounds_error_count": report.mgxs_energy_bounds_error_count,
        "mgxs_energy_mesh_id": report.mgxs_energy_mesh_id,
        "mgxs_energy_mesh_name": report.mgxs_energy_mesh_name,
        "mgxs_energy_mesh_tolerance": report.mgxs_energy_mesh_tolerance,
        "mgxs_energy_bounds_local_count": report.mgxs_energy_bounds_local_count,
        "mgxs_energy_bounds_consistency_error_count": (
            report.mgxs_energy_bounds_consistency_error_count
        ),
        "mgxs_scatter_row_balance_checked": (
            report.mgxs_scatter_row_balance_checked
        ),
        "mgxs_scatter_row_balance_max_rel": (
            report.mgxs_scatter_row_balance_max_rel
        ),
        "mgxs_scatter_row_balance_max_abs": (
            report.mgxs_scatter_row_balance_max_abs
        ),
        "mgxs_scatter_row_balance_worst": (
            report.mgxs_scatter_row_balance_worst
        ),
        "mgxs_chi_checked": report.mgxs_chi_checked,
        "mgxs_chi_sum_max_abs_error": report.mgxs_chi_sum_max_abs_error,
        "mgxs_chi_sum_worst": report.mgxs_chi_sum_worst,
        "mgxs_chi_error_count": report.mgxs_chi_error_count,
        "mgxs_nu_ratio_checked_bins": report.mgxs_nu_ratio_checked_bins,
        "mgxs_nu_ratio_min": report.mgxs_nu_ratio_min,
        "mgxs_nu_ratio_max": report.mgxs_nu_ratio_max,
        "mgxs_nu_ratio_worst": report.mgxs_nu_ratio_worst,
        "mgxs_nu_ratio_warning_count": report.mgxs_nu_ratio_warning_count,
        "mgxs_adf_calculations": report.mgxs_adf_calculations,
        "mgxs_adf_faces": list(report.mgxs_adf_faces),
        "mgxs_adf_face_error_count": report.mgxs_adf_face_error_count,
        "mgxs_transport_p1_checked": report.mgxs_transport_p1_checked,
        "mgxs_transport_p1_max_rel": report.mgxs_transport_p1_max_rel,
        "mgxs_transport_p1_max_abs": report.mgxs_transport_p1_max_abs,
        "mgxs_transport_p1_worst": report.mgxs_transport_p1_worst,
        "mgxs_transport_p1_error_count": report.mgxs_transport_p1_error_count,
        "mgxs_source_domain_indices": list(report.mgxs_source_domain_indices),
        "mgxs_source_domain_order_errors": list(
            report.mgxs_source_domain_order_errors
        ),
        "mgxs_calculations": report.mgxs_calculations,
        "mgxs_volume_attributes": report.mgxs_volume_attributes,
        "mgxs_volume_defaulted": report.mgxs_volume_defaulted,
        "mgxs_volume_nonpositive": report.mgxs_volume_nonpositive,
        "mgxs_fissionable_calculations": report.mgxs_fissionable_calculations,
        "mgxs_h_factor_datasets": report.mgxs_h_factor_datasets,
        "mgxs_h_factor_missing": report.mgxs_h_factor_missing,
        "mgxs_h_factor_invalid": report.mgxs_h_factor_invalid,
        "mgxs_std_dev_datasets": report.mgxs_std_dev_datasets,
        "mgxs_std_dev_expected_datasets": report.mgxs_std_dev_expected_datasets,
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
        "reference_flux_group_order": report.reference_flux_group_order,
        "reference_flux_mixture_names": list(report.reference_flux_mixture_names),
        "warnings": list(report.warnings),
        "errors": list(report.errors),
    }


def format_failure(report: SphLoopFluxMapPreflightReport) -> str:
    if report.passed:
        return "flux-map preflight passed"
    return "flux-map preflight failed: " + "; ".join(report.errors)


def _read_mgxs_metadata(
    path: Path,
    *,
    mesh_tolerance: float = MESH_RELATIVE_TOLERANCE,
    energy_bounds_consistency: bool = False,
    scatter_row_balance_rel: float | None = None,
    chi_sum_tolerance: float | None = None,
    require_adf_face_consistency: bool = False,
    transport_p1_rel: float | None = None,
) -> dict[str, Any]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5:
            raise ValueError("input HDF5 is missing /mixtures")
        mixture_names = read_mixture_names(h5)
        declared_mixture_order = "mixture_names" in h5
        source_domain_indices, source_domain_errors = _source_domain_order_contract(
            h5,
            mixture_names,
            declared_mixture_order=declared_mixture_order,
        )
        if "energy_groups" in h5.attrs:
            energy_groups = int(h5.attrs["energy_groups"])
        elif "energy_bounds" in h5:
            energy_groups = int(h5["energy_bounds"].shape[0]) - 1
        else:
            raise ValueError("input HDF5 must define energy_groups or energy_bounds")
        energy_bounds_contract = _energy_bounds_contract(
            h5,
            energy_groups,
            mesh_tolerance=mesh_tolerance,
        )
        legendre_order = int(h5.attrs.get("legendre_order", 0))
        root_energy_bounds = None
        if "energy_bounds" in h5 and not energy_bounds_contract["energy_bounds_errors"]:
            root_energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        physics_contract = _physics_contract(
            h5,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
            legendre_order=legendre_order,
            root_energy_bounds=root_energy_bounds,
            energy_bounds_consistency=energy_bounds_consistency,
            scatter_row_balance_rel=scatter_row_balance_rel,
            chi_sum_tolerance=chi_sum_tolerance,
            require_adf_face_consistency=require_adf_face_consistency,
            transport_p1_rel=transport_p1_rel,
        )
        volume_contract = _volume_contract(h5, mixture_names)
        h_factor_contract = _h_factor_contract(h5, mixture_names, energy_groups)
        std_dev_contract = _std_dev_contract(h5, mixture_names)
    if not mixture_names:
        raise ValueError("input HDF5 contains no mixtures")
    if energy_groups <= 0:
        raise ValueError("energy group count must be positive")
    return {
        "mixture_names": mixture_names,
        "energy_groups": energy_groups,
        "declared_mixture_order": declared_mixture_order,
        "source_domain_indices": source_domain_indices,
        "source_domain_order_errors": source_domain_errors,
        **energy_bounds_contract,
        **physics_contract,
        **volume_contract,
        **h_factor_contract,
        **std_dev_contract,
    }


def _physics_contract(
    h5: Any,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    legendre_order: int,
    root_energy_bounds: np.ndarray | None,
    energy_bounds_consistency: bool,
    scatter_row_balance_rel: float | None,
    chi_sum_tolerance: float | None,
    require_adf_face_consistency: bool,
    transport_p1_rel: float | None,
) -> dict[str, Any]:
    report = evaluate_mgxs_physics(
        h5,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
        legendre_order=legendre_order,
        root_energy_bounds=root_energy_bounds,
        energy_bounds_consistency=energy_bounds_consistency,
        scatter_row_balance_rel=scatter_row_balance_rel,
        chi_sum_tolerance=chi_sum_tolerance,
        require_adf_face_consistency=require_adf_face_consistency,
        transport_p1_rel=transport_p1_rel,
    )
    return {
        "energy_bounds_local_count": report.energy_bounds_local_count,
        "energy_bounds_consistency_errors": (
            report.energy_bounds_consistency_errors
        ),
        "scatter_row_balance_checked": report.scatter_row_balance_checked,
        "scatter_row_balance_max_rel": report.scatter_row_balance_max_rel,
        "scatter_row_balance_max_abs": report.scatter_row_balance_max_abs,
        "scatter_row_balance_worst": report.scatter_row_balance_worst,
        "scatter_row_balance_warnings": report.scatter_row_balance_warnings,
        "scatter_row_balance_errors": report.scatter_row_balance_errors,
        "chi_checked": report.chi_checked,
        "chi_sum_max_abs_error": report.chi_sum_max_abs_error,
        "chi_sum_worst": report.chi_sum_worst,
        "chi_errors": report.chi_errors,
        "nu_ratio_checked_bins": report.nu_ratio_checked_bins,
        "nu_ratio_min": report.nu_ratio_min,
        "nu_ratio_max": report.nu_ratio_max,
        "nu_ratio_worst": report.nu_ratio_worst,
        "nu_ratio_warning_count": report.nu_ratio_warning_count,
        "nu_ratio_warnings": report.nu_ratio_warnings,
        "adf_calculations": report.adf_calculations,
        "adf_faces": report.adf_faces,
        "adf_face_errors": report.adf_face_errors,
        "transport_p1_checked": report.transport_p1_checked,
        "transport_p1_max_rel": report.transport_p1_max_rel,
        "transport_p1_max_abs": report.transport_p1_max_abs,
        "transport_p1_worst": report.transport_p1_worst,
        "transport_p1_errors": report.transport_p1_errors,
    }


def _energy_bounds_contract(
    h5: Any,
    energy_groups: int,
    *,
    mesh_tolerance: float,
) -> dict[str, Any]:
    if "energy_bounds" not in h5:
        return {
            "energy_bounds_present": False,
            "energy_bounds_order": None,
            "energy_bounds_sha256": None,
            "energy_bounds_errors": (),
            "energy_bounds_warnings": (),
            "energy_mesh_id": None,
            "energy_mesh_name": None,
        }

    try:
        bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    except (TypeError, ValueError, OSError):
        return {
            "energy_bounds_present": True,
            "energy_bounds_order": "unreadable",
            "energy_bounds_sha256": None,
            "energy_bounds_errors": ("/energy_bounds must be a numeric vector",),
            "energy_bounds_warnings": (),
            "energy_mesh_id": None,
            "energy_mesh_name": None,
        }

    errors = tuple(
        f"/{issue}"
        for issue in validate_energy_bounds_internal(
            bounds,
            expected_groups=energy_groups,
            expected_order="ascending",
        )
    )
    order = energy_bounds_order(bounds)
    digest = energy_bounds_sha256(bounds)
    if errors:
        return {
            "energy_bounds_present": True,
            "energy_bounds_order": order,
            "energy_bounds_sha256": digest,
            "energy_bounds_errors": errors,
            "energy_bounds_warnings": (),
            "energy_mesh_id": None,
            "energy_mesh_name": None,
        }

    mesh = identify_mesh(
        bounds,
        rtol=mesh_tolerance,
        atol=MESH_ABSOLUTE_TOLERANCE,
    )
    warnings: tuple[str, ...] = ()
    if mesh is None:
        warnings = (
            "/energy_bounds did not match a bundled known energy mesh "
            f"within rtol={mesh_tolerance:g}",
        )

    return {
        "energy_bounds_present": True,
        "energy_bounds_order": order,
        "energy_bounds_sha256": digest,
        "energy_bounds_errors": (),
        "energy_bounds_warnings": warnings,
        "energy_mesh_id": None if mesh is None else mesh.mesh_id,
        "energy_mesh_name": None if mesh is None else mesh.name,
    }


def _volume_contract(h5: Any, mixture_names: tuple[str, ...]) -> dict[str, Any]:
    volume_attributes = 0
    volume_defaulted = 0
    volume_nonpositive = 0
    calculations = 0
    errors: list[str] = []

    for label, group, parent_group in _iter_calculations(h5, mixture_names):
        calculations += 1
        result = _volume_status(
            label,
            group.attrs,
            None if parent_group is None else parent_group.attrs,
        )
        volume_attributes += result["attributes"]
        volume_defaulted += result["defaulted"]
        volume_nonpositive += result["nonpositive"]
        errors.extend(result["errors"])

    return {
        "calculations": calculations,
        "volume_attributes": volume_attributes,
        "volume_defaulted": volume_defaulted,
        "volume_nonpositive": volume_nonpositive,
        "volume_errors": tuple(errors),
    }


def _h_factor_contract(
    h5: Any,
    mixture_names: tuple[str, ...],
    ngroups: int,
) -> dict[str, Any]:
    fissionable_calculations = 0
    h_factor_datasets = 0
    h_factor_missing = 0
    h_factor_invalid = 0
    errors: list[str] = []

    for label, group, parent_group in _iter_calculations(h5, mixture_names):
        parent_attrs = None if parent_group is None else parent_group.attrs
        fissionable = bool(
            _attr_with_parent(group.attrs, parent_attrs, "fissionable", False)
        )
        if fissionable:
            fissionable_calculations += 1

        dataset_name = _h_factor_dataset_name(group)
        if dataset_name is None:
            if fissionable:
                h_factor_missing += 1
            continue

        h_factor_datasets += 1
        issue = _h_factor_issue(
            group[dataset_name],
            label=label,
            dataset_name=dataset_name,
            ngroups=ngroups,
            fissionable=fissionable,
        )
        if issue is not None:
            h_factor_invalid += 1
            errors.append(issue)

    return {
        "fissionable_calculations": fissionable_calculations,
        "h_factor_datasets": h_factor_datasets,
        "h_factor_missing": h_factor_missing,
        "h_factor_invalid": h_factor_invalid,
        "h_factor_errors": tuple(errors),
    }


def _std_dev_contract(h5: Any, mixture_names: tuple[str, ...]) -> dict[str, Any]:
    expected = 0
    present = 0
    for _label, group, parent_group in _iter_calculations(h5, mixture_names):
        parent_attrs = None if parent_group is None else parent_group.attrs
        fissionable = bool(
            _attr_with_parent(group.attrs, parent_attrs, "fissionable", False)
        )
        for dataset_name in MGXS_STD_DEV_DATASETS:
            if dataset_name not in group:
                continue
            if _is_synthetic_nonfission_placeholder(
                group,
                dataset_name=dataset_name,
                fissionable=fissionable,
            ):
                continue
            expected += 1
            if f"{dataset_name}_std_dev" in group:
                present += 1
    return {
        "std_dev_datasets": present,
        "std_dev_expected_datasets": expected,
    }


def _iter_calculations(h5: Any, mixture_names: tuple[str, ...]):
    mixtures = h5["mixtures"]
    for mixture_name in mixture_names:
        mixture = mixtures[mixture_name]
        if "states" in mixture:
            states = mixture["states"]
            for state_name in sorted(states):
                yield f"{mixture_name}/states/{state_name}", states[state_name], mixture
        else:
            yield mixture_name, mixture, None


def _volume_status(
    label: str,
    attrs: Any,
    parent_attrs: Any | None,
) -> dict[str, Any]:
    value = attrs.get("volume")
    if value is None and parent_attrs is not None:
        value = parent_attrs.get("volume")
    if value is None:
        return {
            "attributes": 0,
            "defaulted": 1,
            "nonpositive": 0,
            "errors": (),
        }
    try:
        volume = float(value)
    except (TypeError, ValueError):
        return {
            "attributes": 1,
            "defaulted": 0,
            "nonpositive": 1,
            "errors": (f"mixture {label}: volume attribute must be numeric",),
        }
    if volume <= 0.0:
        return {
            "attributes": 1,
            "defaulted": 0,
            "nonpositive": 1,
            "errors": (f"mixture {label}: volume attribute must be positive",),
        }
    return {
        "attributes": 1,
        "defaulted": 0,
        "nonpositive": 0,
        "errors": (),
    }


def _h_factor_dataset_name(group: Any) -> str | None:
    for name in H_FACTOR_DATASETS:
        if name in group:
            return name
    return None


def _is_synthetic_nonfission_placeholder(
    group: Any,
    *,
    dataset_name: str,
    fissionable: bool,
) -> bool:
    if fissionable or dataset_name not in {"fission", "nu_fission", "chi"}:
        return False
    try:
        values = np.asarray(group[dataset_name][:], dtype=float)
    except (TypeError, ValueError, OSError):
        return False
    return bool(values.size and np.all(np.isfinite(values)) and not np.any(values))


def _h_factor_issue(
    obj: Any,
    *,
    label: str,
    dataset_name: str,
    ngroups: int,
    fissionable: bool,
) -> str | None:
    try:
        values = np.asarray(obj[:], dtype=float).reshape(-1)
    except (TypeError, ValueError, OSError):
        return f"mixture {label}: {dataset_name} must be a numeric vector"
    if values.shape != (ngroups,):
        return (
            f"mixture {label}: {dataset_name} must have {ngroups} values, "
            f"got {values.shape[0]}"
        )
    if not np.all(np.isfinite(values)):
        return f"mixture {label}: {dataset_name} contains non-finite values"
    if np.any(values < 0.0):
        return f"mixture {label}: {dataset_name} values must be non-negative"
    if fissionable and not np.any(values > 0.0):
        return (
            f"mixture {label}: fissionable {dataset_name} must include "
            "a positive value"
        )
    return None


def _attr_with_parent(
    attrs: Any,
    parent_attrs: Any | None,
    name: str,
    default: object,
) -> object:
    value = attrs.get(name)
    if value is None and parent_attrs is not None:
        value = parent_attrs.get(name)
    return default if value is None else value


def _source_domain_order_contract(
    h5: Any,
    mixture_names: tuple[str, ...],
    *,
    declared_mixture_order: bool,
) -> tuple[tuple[int | None, ...], tuple[str, ...]]:
    errors: list[str] = []
    indices: list[int | None] = []
    if not declared_mixture_order:
        errors.append("MGXS input must declare /mixture_names for production SPH mapping")

    mixtures = h5["mixtures"]
    for expected_index, name in enumerate(mixture_names, start=1):
        group = mixtures[name]
        if "source_domain_index" not in group.attrs:
            indices.append(None)
            errors.append(f"MGXS mixture {name}: source_domain_index is required")
            continue
        try:
            source_domain_index = int(group.attrs["source_domain_index"])
        except (TypeError, ValueError):
            indices.append(None)
            errors.append(
                f"MGXS mixture {name}: source_domain_index must be an integer"
            )
            continue
        indices.append(source_domain_index)
        if source_domain_index != expected_index:
            errors.append(
                f"MGXS mixture {name}: source_domain_index {source_domain_index} "
                f"does not match /mixture_names position {expected_index}"
            )
    return tuple(indices), tuple(errors)


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
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> dict[str, Any]:
    path, dataset = _split_dataset_reference(source)
    warnings: list[str] = []
    errors: list[str] = []
    shape = None
    group_count = None
    group_order = None
    declared_mixture_names: tuple[str, ...] = ()
    selected_dataset = dataset
    if not path.exists():
        return {
            "source": path,
            "dataset": selected_dataset,
            "shape": shape,
            "group_count": group_count,
            "group_order": group_order,
            "mixture_names": declared_mixture_names,
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
            "group_order": group_order,
            "mixture_names": declared_mixture_names,
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
                group_order = _hdf5_text_attr(obj, h5, "group_order")
                if group_order is None:
                    errors.append("reference flux HDF5 must declare group_order")
                elif group_order != MGXS_DONJON_GROUP_ORDER:
                    errors.append(
                        "reference flux group_order must be "
                        f"{MGXS_DONJON_GROUP_ORDER!r}, got {group_order!r}"
                    )
                declared = _names_from_hdf5(
                    obj,
                    h5,
                    ("mixture_names", "mixtures", "domain_names"),
                )
                if declared is None:
                    errors.append(
                        "reference flux HDF5 must declare mixture_names, "
                        "mixtures, or domain_names"
                    )
                else:
                    declared_mixture_names = tuple(_flatten_names(declared))
                    if declared_mixture_names != mixture_names:
                        errors.append(
                            "reference flux mixture names do not match MGXS "
                            "declared order: "
                            f"{declared_mixture_names!r} != {mixture_names!r}"
                        )
                if not shape:
                    errors.append(f"{path}: reference flux dataset is scalar")
                else:
                    group_count = int(shape[-1])
                    expected_shape = (len(mixture_names), energy_groups)
                    if shape != expected_shape:
                        errors.append(
                            "reference flux shape does not match MGXS mixture/group "
                            f"order: {shape} != {expected_shape}"
                        )
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
        "group_order": group_order,
        "mixture_names": declared_mixture_names,
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


def _names_from_hdf5(obj: Any, root: Any, candidates: tuple[str, ...]) -> Any:
    for candidate in candidates:
        if candidate in obj.attrs:
            return obj.attrs[candidate]
    for candidate in candidates:
        if candidate in root.attrs:
            return root.attrs[candidate]
    for candidate in candidates:
        if candidate in root and not hasattr(root[candidate], "keys"):
            return root[candidate][:]
    return None


def _hdf5_text_attr(obj: Any, root: Any, name: str) -> str | None:
    for source in (obj.attrs, root.attrs):
        if name in source:
            value = source[name]
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)
    return None


def _flatten_names(raw: Any) -> tuple[str, ...]:
    arr = np.asarray(raw)
    out: list[str] = []
    for item in arr.reshape(-1):
        if isinstance(item, bytes):
            out.append(item.decode("utf-8"))
        else:
            out.append(str(item))
    return tuple(out)
