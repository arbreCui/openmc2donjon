"""Scatter-matrix checks for the MGXS HDF5 input contract."""

from __future__ import annotations

import numpy as np

from .mgxs_input_report import InputReport


MOMENT_FIRST_SCATTER_AXES = {
    "moment,from,to",
    "moment,in,out",
    "moment,gin,gout",
    "legendre,from,to",
    "legendre,gin,gout",
}
MOMENT_LAST_SCATTER_AXES = {
    "from,to,moment",
    "in,out,moment",
    "gin,gout,moment",
    "from,to,legendre",
    "gin,gout,legendre",
}


def validate_scatter(
    values: np.ndarray,
    ngroups: int,
    legendre_order: int,
    axes: str | None,
    report: InputReport,
    mix_name: str,
) -> int | None:
    expected_moments = legendre_order + 1
    if axes and axes not in report.scatter_axes:
        report.scatter_axes.append(axes)

    if values.ndim == 2:
        if values.shape != (ngroups, ngroups):
            report.fail(
                f"mixture {mix_name}: scatter_matrix shape {values.shape} is not "
                f"({ngroups}, {ngroups})"
            )
            return None
        if expected_moments != 1:
            report.fail(
                f"mixture {mix_name}: 2D scatter_matrix is valid only for legendre_order=0"
            )
            return None
        if np.any(values < 0.0):
            report.fail(
                f"mixture {mix_name}: P0 scatter values must be non-negative"
            )
        return 1

    if values.ndim != 3:
        report.fail(f"mixture {mix_name}: scatter_matrix must be 2D or 3D")
        return None

    normalized = normalize_axes(axes)
    if normalized in MOMENT_FIRST_SCATTER_AXES:
        shape = values.shape
        expected = (expected_moments, ngroups, ngroups)
    elif normalized in MOMENT_LAST_SCATTER_AXES:
        shape = values.shape
        expected = (ngroups, ngroups, expected_moments)
    elif axes is not None:
        report.fail(
            f"mixture {mix_name}: unsupported scatter_axes={axes!r}; expected "
            "'moment,G_in,G_out' or 'G_in,G_out,moment'"
        )
        return None
    elif (
        values.shape == (expected_moments, ngroups, ngroups)
        and values.shape == (ngroups, ngroups, expected_moments)
    ):
        report.fail(
            f"mixture {mix_name}: ambiguous scatter_matrix shape {values.shape}; "
            "set scatter_axes='moment,G_in,G_out' or 'G_in,G_out,moment'"
        )
        return None
    elif values.shape == (expected_moments, ngroups, ngroups):
        expected = values.shape
        shape = values.shape
        report.warn(f"mixture {mix_name}: scatter axes inferred as moment,G_in,G_out")
    elif values.shape == (ngroups, ngroups, expected_moments):
        expected = values.shape
        shape = values.shape
        report.warn(f"mixture {mix_name}: scatter axes inferred as G_in,G_out,moment")
    else:
        report.fail(
            f"mixture {mix_name}: scatter_matrix shape {values.shape} does not match "
            f"({expected_moments}, {ngroups}, {ngroups}) or "
            f"({ngroups}, {ngroups}, {expected_moments})"
        )
        return None

    if shape != expected:
        report.fail(f"mixture {mix_name}: scatter_matrix shape {shape} expected {expected}")
        return None
    p0 = p0_scatter_matrix(values, axes, ngroups, legendre_order)
    if p0 is not None and np.any(p0 < 0.0):
        report.fail(f"mixture {mix_name}: P0 scatter values must be non-negative")
    return expected_moments


def configure_scatter_row_balance(
    report: InputReport,
    *,
    warn_threshold: float | None,
    fail_threshold: float | None,
) -> None:
    report.scatter_row_balance_checked = (
        warn_threshold is not None or fail_threshold is not None
    )
    report.scatter_row_balance_warn_threshold = warn_threshold
    report.scatter_row_balance_fail_threshold = fail_threshold
    if warn_threshold is not None and warn_threshold < 0.0:
        report.fail("--scatter-row-balance-warn must be non-negative")
    if fail_threshold is not None and fail_threshold < 0.0:
        report.fail("--scatter-row-balance-fail must be non-negative")


def p0_scatter_matrix(
    values: np.ndarray,
    axes: str | None,
    ngroups: int,
    legendre_order: int,
) -> np.ndarray | None:
    expected_moments = legendre_order + 1
    if values.ndim == 2:
        if values.shape != (ngroups, ngroups) or expected_moments != 1:
            return None
        return values
    if values.ndim != 3:
        return None

    normalized = normalize_axes(axes)
    moment_first = values.shape == (expected_moments, ngroups, ngroups)
    moment_last = values.shape == (ngroups, ngroups, expected_moments)
    if normalized in MOMENT_FIRST_SCATTER_AXES and moment_first:
        return values[0]
    if normalized in MOMENT_LAST_SCATTER_AXES and moment_last:
        return values[:, :, 0]
    if axes is not None:
        return None
    if moment_first and not moment_last:
        return values[0]
    if moment_last and not moment_first:
        return values[:, :, 0]
    return None

def normalize_axes(value: str | None) -> str | None:
    if value is None:
        return None
    return value.lower().replace(" ", "").replace("_", "")
