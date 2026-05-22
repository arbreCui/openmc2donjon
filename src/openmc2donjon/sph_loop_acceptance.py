"""Acceptance checks for the fixed-OpenMC SPH loop."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


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
