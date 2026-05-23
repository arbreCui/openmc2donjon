"""Acceptance checks for the fixed-OpenMC SPH loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .constants import MGXS_DONJON_GROUP_ORDER
from .sph_loop_production_audit import build_production_audit_payload


ACCEPTANCE_PASS_DECISION = "openmc2donjon_sph_loop_acceptance_passed"
ACCEPTANCE_FAIL_DECISION = "openmc2donjon_sph_loop_acceptance_failed"


class _AuditRowLike(Protocol):
    stage: str
    keff: float | None
    sph_minimum: float | None
    sph_maximum: float | None


class _ConvergenceLike(Protocol):
    sph_max_abs_change: float
    sph_max_rel_change: float
    flux_ratio_max_residual: float
    clipped_count: int
    clipped_fraction: float


class _DatasetMetadataLike(Protocol):
    group_order: str | None
    mixture_names: tuple[str, ...]
    energy_groups: int | None
    std_dev_dataset: str | None
    std_dev_max_rel: float | None


class _FluxMapPreflightLike(Protocol):
    passed: bool
    map_kind: str
    mixture_names: tuple[str, ...]
    energy_groups: int
    mgxs_energy_bounds_present: bool
    mgxs_energy_bounds_error_count: int
    mgxs_energy_mesh_id: str | None
    mgxs_volume_defaulted: int
    mgxs_volume_nonpositive: int
    mgxs_h_factor_missing: int
    mgxs_h_factor_invalid: int
    scalar_flux_ids: tuple[int, ...]
    minimum_required_flux_unknown_count: int | None
    mixture_flux_map: tuple[tuple[str, int], ...]


class _WorkflowMetadataLike(Protocol):
    iteration: int
    donjon_volume_flux: _DatasetMetadataLike
    sph_sidecar: _DatasetMetadataLike


class _ArtifactMetadataLike(Protocol):
    reference_flux: _DatasetMetadataLike
    workflows: tuple[_WorkflowMetadataLike, ...]
    final_sph_sidecar: _DatasetMetadataLike | None


@dataclass(frozen=True)
class SphLoopAcceptanceCheck:
    name: str
    actual: bool | float | int | None
    limit: bool | float | int | None
    units: str
    passed: bool
    message: str


@dataclass(frozen=True)
class SphLoopAcceptanceReport:
    enabled: bool
    passed: bool
    fail_on_violation: bool
    decision: str
    checks: tuple[SphLoopAcceptanceCheck, ...]


def build_acceptance_report(
    config: Mapping[str, object],
    *,
    audit_rows: tuple[_AuditRowLike, ...],
    convergence: tuple[_ConvergenceLike, ...],
    completed_iterations: int,
    converged: bool,
    final_solve: object | None,
    artifact_metadata: _ArtifactMetadataLike | None = None,
    flux_map_preflight: _FluxMapPreflightLike | None = None,
) -> SphLoopAcceptanceReport:
    checks: list[SphLoopAcceptanceCheck] = []
    if "min_completed_iterations" in config:
        checks.append(
            _minimum_check(
                "min_completed_iterations",
                actual=completed_iterations,
                limit=int(config["min_completed_iterations"]),
                units="iterations",
            )
        )
    if "require_final_solve" in config:
        checks.append(
            _boolean_check(
                "require_final_solve",
                actual=final_solve is not None,
                limit=bool(config["require_final_solve"]),
            )
        )
    if "require_converged" in config:
        checks.append(
            _boolean_check(
                "require_converged",
                actual=converged,
                limit=bool(config["require_converged"]),
            )
        )
    if bool(config.get("require_artifact_metadata_alignment", False)):
        checks.append(_artifact_metadata_alignment_check(artifact_metadata))
    if bool(config.get("require_production_audit", False)):
        checks.append(_production_audit_check(flux_map_preflight, artifact_metadata))
    if bool(config.get("require_mgxs_explicit_volumes", False)):
        checks.append(
            _boolean_check(
                "require_mgxs_explicit_volumes",
                actual=_mgxs_explicit_volumes_present(flux_map_preflight),
                limit=True,
            )
        )
    if "max_mgxs_default_volume_count" in config:
        checks.append(
            _maximum_check(
                "max_mgxs_default_volume_count",
                actual=_mgxs_default_volume_count(flux_map_preflight),
                limit=int(config["max_mgxs_default_volume_count"]),
                units="calculations",
            )
        )
    if bool(config.get("require_mgxs_h_factor", False)):
        checks.append(
            _boolean_check(
                "require_mgxs_h_factor",
                actual=_mgxs_h_factor_present(flux_map_preflight),
                limit=True,
            )
        )
    if "max_mgxs_missing_h_factor_count" in config:
        checks.append(
            _maximum_check(
                "max_mgxs_missing_h_factor_count",
                actual=_mgxs_missing_h_factor_count(flux_map_preflight),
                limit=int(config["max_mgxs_missing_h_factor_count"]),
                units="calculations",
            )
        )
    if bool(config.get("require_mgxs_energy_bounds", False)):
        checks.append(
            _boolean_check(
                "require_mgxs_energy_bounds",
                actual=_mgxs_energy_bounds_present(flux_map_preflight),
                limit=True,
            )
        )
    if bool(config.get("require_known_mesh", False)):
        checks.append(
            _boolean_check(
                "require_known_mesh",
                actual=_mgxs_known_mesh_present(flux_map_preflight),
                limit=True,
            )
        )
    if bool(config.get("require_reference_flux_std_dev", False)):
        checks.append(
            _boolean_check(
                "require_reference_flux_std_dev",
                actual=_reference_flux_std_dev_present(artifact_metadata),
                limit=True,
            )
        )
    if "max_reference_flux_std_dev_rel" in config:
        checks.append(
            _maximum_check(
                "max_reference_flux_std_dev_rel",
                actual=_reference_flux_std_dev_max_rel(artifact_metadata),
                limit=float(config["max_reference_flux_std_dev_rel"]),
                units="relative",
            )
        )

    last_convergence = convergence[-1] if convergence else None
    if "max_sph_abs_change" in config:
        checks.append(
            _maximum_check(
                "max_sph_abs_change",
                actual=(
                    None
                    if last_convergence is None
                    else last_convergence.sph_max_abs_change
                ),
                limit=float(config["max_sph_abs_change"]),
                units="factor",
            )
        )
    if "max_sph_rel_change" in config:
        checks.append(
            _maximum_check(
                "max_sph_rel_change",
                actual=(
                    None
                    if last_convergence is None
                    else last_convergence.sph_max_rel_change
                ),
                limit=float(config["max_sph_rel_change"]),
                units="relative",
            )
        )
    if "max_flux_ratio_residual" in config:
        checks.append(
            _maximum_check(
                "max_flux_ratio_residual",
                actual=(
                    None
                    if last_convergence is None
                    else last_convergence.flux_ratio_max_residual
                ),
                limit=float(config["max_flux_ratio_residual"]),
                units="relative",
            )
        )
    if "max_final_to_initial_flux_residual_ratio" in config:
        checks.append(
            _maximum_check(
                "max_final_to_initial_flux_residual_ratio",
                actual=_final_to_initial_flux_residual_ratio(convergence),
                limit=float(config["max_final_to_initial_flux_residual_ratio"]),
                units="ratio",
            )
        )
    if "max_final_clipped_fraction" in config:
        checks.append(
            _maximum_check(
                "max_final_clipped_fraction",
                actual=(
                    None
                    if last_convergence is None
                    else last_convergence.clipped_fraction
                ),
                limit=float(config["max_final_clipped_fraction"]),
                units="fraction",
            )
        )
    if "max_final_clipped_count" in config:
        checks.append(
            _maximum_check(
                "max_final_clipped_count",
                actual=None if last_convergence is None else last_convergence.clipped_count,
                limit=int(config["max_final_clipped_count"]),
                units="bins",
            )
        )

    last_iteration = _last_iteration_audit_row(audit_rows)
    if "sph_minimum_floor" in config:
        checks.append(
            _minimum_check(
                "sph_minimum_floor",
                actual=None if last_iteration is None else last_iteration.sph_minimum,
                limit=float(config["sph_minimum_floor"]),
                units="factor",
            )
        )
    if "sph_maximum_ceiling" in config:
        checks.append(
            _maximum_check(
                "sph_maximum_ceiling",
                actual=None if last_iteration is None else last_iteration.sph_maximum,
                limit=float(config["sph_maximum_ceiling"]),
                units="factor",
            )
        )

    keff_values = [row.keff for row in audit_rows if row.keff is not None]
    if "max_keff_step_pcm" in config:
        checks.append(
            _maximum_check(
                "max_keff_step_pcm",
                actual=_max_keff_step_pcm(keff_values),
                limit=float(config["max_keff_step_pcm"]),
                units="pcm",
            )
        )
    if "max_final_keff_delta_pcm" in config:
        checks.append(
            _maximum_check(
                "max_final_keff_delta_pcm",
                actual=_final_keff_delta_pcm(audit_rows),
                limit=float(config["max_final_keff_delta_pcm"]),
                units="pcm",
            )
        )

    enabled = bool(checks)
    passed = all(item.passed for item in checks)
    decision = ACCEPTANCE_PASS_DECISION if passed else ACCEPTANCE_FAIL_DECISION
    return SphLoopAcceptanceReport(
        enabled=enabled,
        passed=passed,
        fail_on_violation=bool(config.get("fail_on_violation", False)),
        decision=decision,
        checks=tuple(checks),
    )


def _maximum_check(
    name: str,
    *,
    actual: float | int | None,
    limit: float | int,
    units: str,
) -> SphLoopAcceptanceCheck:
    passed = actual is not None and float(actual) <= float(limit)
    if actual is None:
        message = f"metric unavailable; required <= {_format_check_value(limit)} {units}"
    else:
        message = (
            f"actual {_format_check_value(actual)} <= "
            f"limit {_format_check_value(limit)} {units}"
        )
    return SphLoopAcceptanceCheck(
        name=name,
        actual=actual,
        limit=limit,
        units=units,
        passed=passed,
        message=message,
    )


def _minimum_check(
    name: str,
    *,
    actual: float | int | None,
    limit: float | int,
    units: str,
) -> SphLoopAcceptanceCheck:
    passed = actual is not None and float(actual) >= float(limit)
    if actual is None:
        message = f"metric unavailable; required >= {_format_check_value(limit)} {units}"
    else:
        message = (
            f"actual {_format_check_value(actual)} >= "
            f"limit {_format_check_value(limit)} {units}"
        )
    return SphLoopAcceptanceCheck(
        name=name,
        actual=actual,
        limit=limit,
        units=units,
        passed=passed,
        message=message,
    )


def _boolean_check(
    name: str,
    *,
    actual: bool,
    limit: bool,
) -> SphLoopAcceptanceCheck:
    passed = actual is limit
    return SphLoopAcceptanceCheck(
        name=name,
        actual=actual,
        limit=limit,
        units="boolean",
        passed=passed,
        message=f"actual {actual} == required {limit}",
    )


def _artifact_metadata_alignment_check(
    metadata: _ArtifactMetadataLike | None,
) -> SphLoopAcceptanceCheck:
    errors = _artifact_metadata_alignment_errors(metadata)
    passed = not errors
    message = "all artifact metadata aligned" if passed else "; ".join(errors[:4])
    if len(errors) > 4:
        message += f"; ... ({len(errors)} total)"
    return SphLoopAcceptanceCheck(
        name="require_artifact_metadata_alignment",
        actual=passed,
        limit=True,
        units="boolean",
        passed=passed,
        message=message,
    )


def _artifact_metadata_alignment_errors(
    metadata: _ArtifactMetadataLike | None,
) -> list[str]:
    if metadata is None:
        return ["artifact metadata unavailable"]
    errors: list[str] = []
    reference = metadata.reference_flux
    reference_order = reference.group_order
    reference_names = reference.mixture_names
    if reference_order != MGXS_DONJON_GROUP_ORDER:
        errors.append(
            "reference_flux group_order "
            f"{reference_order!r} != {MGXS_DONJON_GROUP_ORDER!r}"
        )
    if not reference_names:
        errors.append("reference_flux mixture_names missing")
    for workflow in metadata.workflows:
        _append_dataset_alignment_errors(
            errors,
            f"iter{workflow.iteration} donjon_volume_flux",
            workflow.donjon_volume_flux,
            reference_order=MGXS_DONJON_GROUP_ORDER,
            reference_names=reference_names,
        )
        _append_dataset_alignment_errors(
            errors,
            f"iter{workflow.iteration} sph_sidecar",
            workflow.sph_sidecar,
            reference_order=MGXS_DONJON_GROUP_ORDER,
            reference_names=reference_names,
        )
    if metadata.workflows and metadata.final_sph_sidecar is None:
        errors.append("final_sph_sidecar missing")
    if metadata.final_sph_sidecar is not None:
        _append_dataset_alignment_errors(
            errors,
            "final_sph_sidecar",
            metadata.final_sph_sidecar,
            reference_order=MGXS_DONJON_GROUP_ORDER,
            reference_names=reference_names,
        )
    return errors


def _production_audit_check(
    flux_map_preflight: _FluxMapPreflightLike | None,
    artifact_metadata: _ArtifactMetadataLike | None,
) -> SphLoopAcceptanceCheck:
    if flux_map_preflight is None or artifact_metadata is None:
        errors = []
        if flux_map_preflight is None:
            errors.append("flux map preflight unavailable")
        if artifact_metadata is None:
            errors.append("artifact metadata unavailable")
    else:
        payload = build_production_audit_payload(
            flux_map_preflight=flux_map_preflight,
            artifact_metadata=artifact_metadata,
        )
        errors = [str(item) for item in payload["errors"]]
    passed = not errors
    message = "production audit passed" if passed else "; ".join(errors[:4])
    if len(errors) > 4:
        message += f"; ... ({len(errors)} total)"
    return SphLoopAcceptanceCheck(
        name="require_production_audit",
        actual=passed,
        limit=True,
        units="boolean",
        passed=passed,
        message=message,
    )


def _reference_flux_std_dev_present(
    artifact_metadata: _ArtifactMetadataLike | None,
) -> bool:
    if artifact_metadata is None:
        return False
    return bool(getattr(artifact_metadata.reference_flux, "std_dev_dataset", None))


def _mgxs_explicit_volumes_present(
    flux_map_preflight: _FluxMapPreflightLike | None,
) -> bool:
    if flux_map_preflight is None:
        return False
    return (
        int(getattr(flux_map_preflight, "mgxs_volume_defaulted", 0)) == 0
        and int(getattr(flux_map_preflight, "mgxs_volume_nonpositive", 0)) == 0
    )


def _mgxs_default_volume_count(
    flux_map_preflight: _FluxMapPreflightLike | None,
) -> int | None:
    if flux_map_preflight is None:
        return None
    return int(getattr(flux_map_preflight, "mgxs_volume_defaulted", 0))


def _mgxs_h_factor_present(
    flux_map_preflight: _FluxMapPreflightLike | None,
) -> bool:
    if flux_map_preflight is None:
        return False
    return (
        int(getattr(flux_map_preflight, "mgxs_h_factor_missing", 0)) == 0
        and int(getattr(flux_map_preflight, "mgxs_h_factor_invalid", 0)) == 0
    )


def _mgxs_missing_h_factor_count(
    flux_map_preflight: _FluxMapPreflightLike | None,
) -> int | None:
    if flux_map_preflight is None:
        return None
    return int(getattr(flux_map_preflight, "mgxs_h_factor_missing", 0))


def _mgxs_energy_bounds_present(
    flux_map_preflight: _FluxMapPreflightLike | None,
) -> bool:
    if flux_map_preflight is None:
        return False
    return bool(getattr(flux_map_preflight, "mgxs_energy_bounds_present", False)) and (
        int(getattr(flux_map_preflight, "mgxs_energy_bounds_error_count", 0)) == 0
    )


def _mgxs_known_mesh_present(
    flux_map_preflight: _FluxMapPreflightLike | None,
) -> bool:
    if flux_map_preflight is None:
        return False
    if int(getattr(flux_map_preflight, "mgxs_energy_bounds_error_count", 0)) != 0:
        return False
    return bool(getattr(flux_map_preflight, "mgxs_energy_mesh_id", None))


def _reference_flux_std_dev_max_rel(
    artifact_metadata: _ArtifactMetadataLike | None,
) -> float | None:
    if artifact_metadata is None:
        return None
    value = getattr(artifact_metadata.reference_flux, "std_dev_max_rel", None)
    return None if value is None else float(value)


def _append_dataset_alignment_errors(
    errors: list[str],
    label: str,
    metadata: _DatasetMetadataLike,
    *,
    reference_order: str,
    reference_names: tuple[str, ...],
) -> None:
    if metadata.group_order != reference_order:
        errors.append(
            f"{label} group_order {metadata.group_order!r} != {reference_order!r}"
        )
    if tuple(metadata.mixture_names) != tuple(reference_names):
        errors.append(
            f"{label} mixture_names do not match reference_flux mixture_names"
        )


def _last_iteration_audit_row(
    rows: tuple[_AuditRowLike, ...],
) -> _AuditRowLike | None:
    for row in reversed(rows):
        if row.stage == "iteration":
            return row
    return None


def _max_keff_step_pcm(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    deltas = []
    for before, after in zip(values, values[1:]):
        denominator = max(abs(before), 1.0e-30)
        deltas.append(abs(after - before) / denominator * 1.0e5)
    return float(max(deltas))


def _final_to_initial_flux_residual_ratio(
    convergence: tuple[_ConvergenceLike, ...],
) -> float | None:
    if not convergence:
        return None
    initial = float(convergence[0].flux_ratio_max_residual)
    final = float(convergence[-1].flux_ratio_max_residual)
    if final == 0.0:
        return 0.0
    return final / max(abs(initial), 1.0e-30)


def _final_keff_delta_pcm(rows: tuple[_AuditRowLike, ...]) -> float | None:
    final_rows = [row for row in rows if row.stage == "final" and row.keff is not None]
    iteration_rows = [
        row for row in rows if row.stage == "iteration" and row.keff is not None
    ]
    if not final_rows or not iteration_rows:
        return None
    before = iteration_rows[-1].keff
    after = final_rows[-1].keff
    if before is None or after is None:
        return None
    return float(abs(after - before) / max(abs(before), 1.0e-30) * 1.0e5)


def _format_check_value(value: bool | float | int | None) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return str(value)
    return f"{float(value):.12g}"
