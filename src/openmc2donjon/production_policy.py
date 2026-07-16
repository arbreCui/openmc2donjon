"""Canonical, non-relaxable Converter production-preflight policy."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .mgxs_physics_checks import (
    DEFAULT_CHI_SUM_TOLERANCE,
    DEFAULT_SCATTER_ROW_BALANCE_REL,
    DEFAULT_TRANSPORT_P1_REL,
)


PRODUCTION_PREFLIGHT_POLICY_ID = "openmc2donjon.production-preflight.v1"
PRODUCTION_UNCERTAINTY_WARN = 5.0e-2

# Every numeric item is an upper bound: a smaller requested value is stricter.
# Keep these values in one module so execution, receipts, and acceptance
# validation cannot silently drift apart.
PRODUCTION_CANONICAL_MAXIMUMS: dict[str, float] = {
    "scatter_row_balance_fail": DEFAULT_SCATTER_ROW_BALANCE_REL,
    "transport_p1_fail": DEFAULT_TRANSPORT_P1_REL,
    "chi_sum_tolerance": DEFAULT_CHI_SUM_TOLERANCE,
    "uncertainty_warn": PRODUCTION_UNCERTAINTY_WARN,
    # A formal handoff must not accept a production-critical tally whose
    # one-sigma uncertainty is comparable to its mean.  Ten percent is the
    # same hard precision ceiling used by the native-SPH flux evidence; the
    # five-percent warning remains an earlier statistical-quality signal.
    "uncertainty_fail": 1.0e-1,
    "uncertainty_production_fail": 1.0e-1,
    "uncertainty_mean_abs_floor": 1.0e-12,
}


def canonical_production_thresholds() -> dict[str, float]:
    """Return a fresh copy of the canonical effective threshold set."""

    return dict(PRODUCTION_CANONICAL_MAXIMUMS)


def effective_production_thresholds(
    *,
    scatter_row_balance_fail: float | None,
    transport_p1_fail: float | None,
    chi_sum_tolerance: float | None,
    uncertainty_warn: float | None,
    uncertainty_fail: float | None,
    uncertainty_production_fail: float | None,
    uncertainty_mean_abs_floor: float,
) -> dict[str, float]:
    """Return production thresholds, clamping every request to canonical safety.

    A user can make a production check stricter, but a larger threshold (or a
    missing threshold) resolves to the canonical value.  Engineering checks do
    not use this helper and remain fully configurable.
    """

    requested = {
        "scatter_row_balance_fail": scatter_row_balance_fail,
        "transport_p1_fail": transport_p1_fail,
        "chi_sum_tolerance": chi_sum_tolerance,
        "uncertainty_warn": uncertainty_warn,
        "uncertainty_fail": uncertainty_fail,
        "uncertainty_production_fail": uncertainty_production_fail,
        "uncertainty_mean_abs_floor": uncertainty_mean_abs_floor,
    }
    effective = {
        name: _at_most(requested[name], maximum)
        for name, maximum in PRODUCTION_CANONICAL_MAXIMUMS.items()
    }
    return effective


def production_preflight_policy_payload(
    *,
    production_requested: bool,
    preflight_executed: bool,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Build the auditable policy block stored in a Converter receipt."""

    level = (
        "production"
        if production_requested
        else "engineering"
        if preflight_executed
        else "none"
    )
    payload: dict[str, Any] = {
        "level": level,
        "production_requested": production_requested,
        "preflight_executed": preflight_executed,
    }
    if not production_requested:
        return payload
    if thresholds is None:
        raise ValueError("production receipt requires effective preflight thresholds")
    payload.update(
        {
            "policy_id": PRODUCTION_PREFLIGHT_POLICY_ID,
            "uncertainty_check_enabled": True,
            "require_std_dev_coverage": True,
            "canonical_maximums": dict(PRODUCTION_CANONICAL_MAXIMUMS),
            "effective_thresholds": dict(thresholds),
        }
    )
    return payload


def canonical_production_policy_issues(policy: Any) -> list[str]:
    """Validate a receipt policy block against the canonical preset."""

    if not isinstance(policy, dict):
        return ["Converter receipt has no auditable production preflight policy"]

    issues: list[str] = []
    if policy.get("level") != "production":
        issues.append("Converter receipt preflight policy level is not production")
    if policy.get("production_requested") is not True:
        issues.append("Converter receipt preflight policy did not request production")
    if policy.get("preflight_executed") is not True:
        issues.append("Converter receipt preflight policy did not execute preflight")
    if policy.get("policy_id") != PRODUCTION_PREFLIGHT_POLICY_ID:
        issues.append("Converter receipt production policy id is not canonical")
    if policy.get("uncertainty_check_enabled") is not True:
        issues.append("Converter receipt production policy disabled uncertainty checks")
    if policy.get("require_std_dev_coverage") is not True:
        issues.append("Converter receipt production policy did not require std-dev coverage")
    if policy.get("canonical_maximums") != PRODUCTION_CANONICAL_MAXIMUMS:
        issues.append("Converter receipt production policy maximums are not canonical")

    effective = policy.get("effective_thresholds")
    if not isinstance(effective, dict):
        issues.append("Converter receipt has no effective production thresholds")
        return issues
    for name, maximum in PRODUCTION_CANONICAL_MAXIMUMS.items():
        value = _finite_number(effective.get(name))
        if value is None:
            issues.append(f"Converter receipt production threshold {name} is missing")
        elif value < 0.0:
            issues.append(
                f"Converter receipt production threshold {name} must be non-negative"
            )
        elif value > maximum:
            issues.append(
                f"Converter receipt production threshold {name}={value:g} "
                f"exceeds canonical maximum {maximum:g}"
            )
    return issues


def _at_most(value: float | None, maximum: float) -> float:
    if value is None:
        return maximum
    number = float(value)
    if not math.isfinite(number):
        return maximum
    return min(number, maximum)


def _finite_number(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number
