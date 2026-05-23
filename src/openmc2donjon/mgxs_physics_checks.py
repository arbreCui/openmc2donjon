"""Shared physics-consistency checks for converter-facing MGXS HDF5 files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .energy_groups import validate_energy_bounds_internal
from .mgxs_input_scatter import (
    MOMENT_FIRST_SCATTER_AXES,
    MOMENT_LAST_SCATTER_AXES,
    normalize_axes,
    p0_scatter_matrix,
)


DEFAULT_SCATTER_ROW_BALANCE_REL = 5.0e-2
DEFAULT_CHI_SUM_TOLERANCE = 1.0e-6
DEFAULT_NU_RATIO_MINIMUM = 2.0
DEFAULT_NU_RATIO_MAXIMUM = 3.5
DEFAULT_TRANSPORT_P1_REL = 5.0e-2
LOCAL_ENERGY_BOUNDS_RTOL = 1.0e-10
LOCAL_ENERGY_BOUNDS_ATOL = 0.0
FISSION_RATE_FLOOR = 1.0e-30


@dataclass(frozen=True)
class MgxsPhysicsCheckReport:
    energy_bounds_local_count: int = 0
    energy_bounds_consistency_errors: tuple[str, ...] = ()
    scatter_row_balance_checked: int = 0
    scatter_row_balance_max_rel: float | None = None
    scatter_row_balance_max_abs: float | None = None
    scatter_row_balance_worst: str | None = None
    scatter_row_balance_warnings: tuple[str, ...] = ()
    scatter_row_balance_errors: tuple[str, ...] = ()
    chi_checked: int = 0
    chi_sum_max_abs_error: float | None = None
    chi_sum_worst: str | None = None
    chi_errors: tuple[str, ...] = ()
    nu_ratio_checked_bins: int = 0
    nu_ratio_min: float | None = None
    nu_ratio_max: float | None = None
    nu_ratio_worst: str | None = None
    nu_ratio_warnings: tuple[str, ...] = ()
    adf_calculations: int = 0
    adf_faces: tuple[str, ...] = ()
    adf_face_errors: tuple[str, ...] = ()
    transport_p1_checked: int = 0
    transport_p1_max_rel: float | None = None
    transport_p1_max_abs: float | None = None
    transport_p1_worst: str | None = None
    transport_p1_errors: tuple[str, ...] = ()


@dataclass
class _MutablePhysicsReport:
    energy_bounds_local_count: int = 0
    energy_bounds_consistency_errors: list[str] | None = None
    scatter_row_balance_checked: int = 0
    scatter_row_balance_max_rel: float | None = None
    scatter_row_balance_max_abs: float | None = None
    scatter_row_balance_worst: str | None = None
    scatter_row_balance_warnings: list[str] | None = None
    scatter_row_balance_errors: list[str] | None = None
    chi_checked: int = 0
    chi_sum_max_abs_error: float | None = None
    chi_sum_worst: str | None = None
    chi_errors: list[str] | None = None
    nu_ratio_checked_bins: int = 0
    nu_ratio_min: float | None = None
    nu_ratio_max: float | None = None
    nu_ratio_worst: str | None = None
    nu_ratio_warnings: list[str] | None = None
    adf_calculations: int = 0
    adf_faces: tuple[str, ...] = ()
    adf_face_errors: list[str] | None = None
    transport_p1_checked: int = 0
    transport_p1_max_rel: float | None = None
    transport_p1_max_abs: float | None = None
    transport_p1_worst: str | None = None
    transport_p1_errors: list[str] | None = None

    def __post_init__(self) -> None:
        self.energy_bounds_consistency_errors = []
        self.scatter_row_balance_warnings = []
        self.scatter_row_balance_errors = []
        self.chi_errors = []
        self.nu_ratio_warnings = []
        self.adf_face_errors = []
        self.transport_p1_errors = []

    def freeze(self) -> MgxsPhysicsCheckReport:
        return MgxsPhysicsCheckReport(
            energy_bounds_local_count=self.energy_bounds_local_count,
            energy_bounds_consistency_errors=tuple(
                self.energy_bounds_consistency_errors or ()
            ),
            scatter_row_balance_checked=self.scatter_row_balance_checked,
            scatter_row_balance_max_rel=self.scatter_row_balance_max_rel,
            scatter_row_balance_max_abs=self.scatter_row_balance_max_abs,
            scatter_row_balance_worst=self.scatter_row_balance_worst,
            scatter_row_balance_warnings=tuple(
                self.scatter_row_balance_warnings or ()
            ),
            scatter_row_balance_errors=tuple(self.scatter_row_balance_errors or ()),
            chi_checked=self.chi_checked,
            chi_sum_max_abs_error=self.chi_sum_max_abs_error,
            chi_sum_worst=self.chi_sum_worst,
            chi_errors=tuple(self.chi_errors or ()),
            nu_ratio_checked_bins=self.nu_ratio_checked_bins,
            nu_ratio_min=self.nu_ratio_min,
            nu_ratio_max=self.nu_ratio_max,
            nu_ratio_worst=self.nu_ratio_worst,
            nu_ratio_warnings=tuple(self.nu_ratio_warnings or ()),
            adf_calculations=self.adf_calculations,
            adf_faces=self.adf_faces,
            adf_face_errors=tuple(self.adf_face_errors or ()),
            transport_p1_checked=self.transport_p1_checked,
            transport_p1_max_rel=self.transport_p1_max_rel,
            transport_p1_max_abs=self.transport_p1_max_abs,
            transport_p1_worst=self.transport_p1_worst,
            transport_p1_errors=tuple(self.transport_p1_errors or ()),
        )


def evaluate_mgxs_physics(
    h5: Any,
    *,
    mixture_names: tuple[str, ...],
    energy_groups: int,
    legendre_order: int,
    root_energy_bounds: np.ndarray | None,
    energy_bounds_consistency: bool = False,
    scatter_row_balance_rel: float | None = None,
    scatter_row_balance_warn_rel: float | None = None,
    chi_sum_tolerance: float | None = None,
    require_adf_face_consistency: bool = False,
    transport_p1_rel: float | None = None,
    nu_ratio_minimum: float = DEFAULT_NU_RATIO_MINIMUM,
    nu_ratio_maximum: float = DEFAULT_NU_RATIO_MAXIMUM,
) -> MgxsPhysicsCheckReport:
    """Evaluate production physics guardrails without mutating the HDF5 file."""

    report = _MutablePhysicsReport()
    if energy_bounds_consistency and root_energy_bounds is not None:
        _check_local_energy_bounds(
            report,
            root_energy_bounds=root_energy_bounds,
            h5=h5,
            mixture_names=mixture_names,
            energy_groups=energy_groups,
        )

    adf_names_by_calc: list[tuple[str, ...]] = []
    for label, group, parent_group in _iter_calculations(h5, mixture_names):
        parent_attrs = None if parent_group is None else parent_group.attrs
        fissionable = bool(
            _attr_with_parent(group.attrs, parent_attrs, "fissionable", False)
        )
        axes = _scatter_axes(group, h5, parent_group)
        total = _vector_or_none(group, "total", energy_groups)
        absorption = _vector_or_none(group, "absorption", energy_groups)
        fission = _vector_or_none(group, "fission", energy_groups)
        nu_fission = _vector_or_none(group, "nu_fission", energy_groups)
        chi = _vector_or_none(group, "chi", energy_groups)
        scatter = _scatter_or_none(group, "scatter_matrix")

        if (
            scatter_row_balance_rel is not None
            or scatter_row_balance_warn_rel is not None
        ):
            _check_scatter_row_balance(
                report,
                label=label,
                total=total,
                absorption=absorption,
                scatter=scatter,
                axes=axes,
                energy_groups=energy_groups,
                legendre_order=legendre_order,
                fail_threshold=scatter_row_balance_rel,
                warn_threshold=scatter_row_balance_warn_rel,
            )
        if chi_sum_tolerance is not None:
            _check_chi(
                report,
                label=label,
                chi=chi,
                fissionable=fissionable,
                tolerance=chi_sum_tolerance,
            )
        _check_nu_ratio(
            report,
            label=label,
            fission=fission,
            nu_fission=nu_fission,
            fissionable=fissionable,
            minimum=nu_ratio_minimum,
            maximum=nu_ratio_maximum,
        )
        if require_adf_face_consistency:
            adf_names_by_calc.append(_adf_names(group))
        if transport_p1_rel is not None:
            _check_transport_p1(
                report,
                label=label,
                total=total,
                transport_total=_vector_or_none(group, "transport_total", energy_groups),
                scatter=scatter,
                axes=axes,
                energy_groups=energy_groups,
                legendre_order=legendre_order,
                threshold=transport_p1_rel,
            )

    if require_adf_face_consistency:
        _finalize_adf_faces(report, adf_names_by_calc)
    return report.freeze()


def _check_local_energy_bounds(
    report: _MutablePhysicsReport,
    *,
    root_energy_bounds: np.ndarray,
    h5: Any,
    mixture_names: tuple[str, ...],
    energy_groups: int,
) -> None:
    mixtures = h5["mixtures"]
    for mixture_name in mixture_names:
        mixture = mixtures[mixture_name]
        if "energy_bounds" in mixture:
            _check_one_local_energy_bounds(
                report,
                label=f"{mixture_name}/energy_bounds",
                obj=mixture["energy_bounds"],
                root_energy_bounds=root_energy_bounds,
                energy_groups=energy_groups,
            )
        if "states" not in mixture:
            continue
        states = mixture["states"]
        for state_name in _sorted_state_names(states):
            state_group = states[state_name]
            if "energy_bounds" in state_group:
                _check_one_local_energy_bounds(
                    report,
                    label=f"{mixture_name}/states/{state_name}/energy_bounds",
                    obj=state_group["energy_bounds"],
                    root_energy_bounds=root_energy_bounds,
                    energy_groups=energy_groups,
                )


def _check_one_local_energy_bounds(
    report: _MutablePhysicsReport,
    *,
    label: str,
    obj: Any,
    root_energy_bounds: np.ndarray,
    energy_groups: int,
) -> None:
    report.energy_bounds_local_count += 1
    try:
        values = np.asarray(obj[:], dtype=float)
    except (TypeError, ValueError, OSError):
        report.energy_bounds_consistency_errors.append(f"{label} must be numeric")
        return
    issues = validate_energy_bounds_internal(
        values,
        expected_groups=energy_groups,
        expected_order="ascending",
    )
    if issues:
        report.energy_bounds_consistency_errors.extend(
            f"{label}: {issue}" for issue in issues
        )
        return
    if not np.allclose(
        values,
        root_energy_bounds,
        rtol=LOCAL_ENERGY_BOUNDS_RTOL,
        atol=LOCAL_ENERGY_BOUNDS_ATOL,
    ):
        index = int(np.argmax(np.abs(values - root_energy_bounds)))
        report.energy_bounds_consistency_errors.append(
            f"{label} differs from /energy_bounds at index {index}: "
            f"actual={values[index]:.12e} expected={root_energy_bounds[index]:.12e}"
        )


def _check_scatter_row_balance(
    report: _MutablePhysicsReport,
    *,
    label: str,
    total: np.ndarray | None,
    absorption: np.ndarray | None,
    scatter: np.ndarray | None,
    axes: str | None,
    energy_groups: int,
    legendre_order: int,
    fail_threshold: float | None,
    warn_threshold: float | None,
) -> None:
    if total is None or absorption is None or scatter is None:
        return
    p0 = p0_scatter_matrix(scatter, axes, energy_groups, legendre_order)
    if p0 is None:
        return
    if not (
        np.all(np.isfinite(total))
        and np.all(np.isfinite(absorption))
        and np.all(np.isfinite(p0))
    ):
        return
    report.scatter_row_balance_checked += 1
    residual = total - absorption - p0.sum(axis=1)
    rel, max_abs, max_rel, index = _relative_worst(residual, total)
    del rel
    _update_worst(
        current=report,
        attr_rel="scatter_row_balance_max_rel",
        attr_abs="scatter_row_balance_max_abs",
        attr_worst="scatter_row_balance_worst",
        max_rel=max_rel,
        max_abs=max_abs,
        worst=f"{label}: group={index + 1} residual={residual[index]:.6e}",
    )
    detail = (
        "scatter row-balance max relative residual "
        f"{max_rel:.6e} (abs {max_abs:.6e}) at {label}: group={index + 1}"
    )
    if fail_threshold is not None and max_rel > fail_threshold:
        report.scatter_row_balance_errors.append(
            f"{detail} exceeds fail threshold {fail_threshold:.6e}"
        )
    elif warn_threshold is not None and max_rel > warn_threshold:
        report.scatter_row_balance_warnings.append(
            f"{detail} exceeds warn threshold {warn_threshold:.6e}"
        )


def _check_chi(
    report: _MutablePhysicsReport,
    *,
    label: str,
    chi: np.ndarray | None,
    fissionable: bool,
    tolerance: float,
) -> None:
    if not fissionable:
        return
    report.chi_checked += 1
    if chi is None:
        report.chi_errors.append(f"mixture {label}: chi is required for fissionable data")
        return
    if not np.all(np.isfinite(chi)):
        report.chi_errors.append(f"mixture {label}: chi contains non-finite values")
        return
    if np.any(chi < 0.0):
        report.chi_errors.append(f"mixture {label}: chi must be non-negative")
        return
    error = abs(float(np.sum(chi)) - 1.0)
    if report.chi_sum_max_abs_error is None or error > report.chi_sum_max_abs_error:
        report.chi_sum_max_abs_error = error
        report.chi_sum_worst = f"{label}: sum(chi)={float(np.sum(chi)):.12e}"
    if error > tolerance:
        report.chi_errors.append(
            f"mixture {label}: chi sum error {error:.6e} exceeds "
            f"tolerance {tolerance:.6e}"
        )


def _check_nu_ratio(
    report: _MutablePhysicsReport,
    *,
    label: str,
    fission: np.ndarray | None,
    nu_fission: np.ndarray | None,
    fissionable: bool,
    minimum: float,
    maximum: float,
) -> None:
    if not fissionable or fission is None or nu_fission is None:
        return
    if not (np.all(np.isfinite(fission)) and np.all(np.isfinite(nu_fission))):
        return
    mask = fission > FISSION_RATE_FLOOR
    if not np.any(mask):
        return
    ratio = nu_fission[mask] / fission[mask]
    groups = np.nonzero(mask)[0]
    report.nu_ratio_checked_bins += int(ratio.size)
    local_min = float(np.min(ratio))
    local_max = float(np.max(ratio))
    report.nu_ratio_min = (
        local_min if report.nu_ratio_min is None else min(report.nu_ratio_min, local_min)
    )
    report.nu_ratio_max = (
        local_max if report.nu_ratio_max is None else max(report.nu_ratio_max, local_max)
    )
    low = ratio < minimum
    high = ratio > maximum
    if not np.any(low | high):
        return
    distance = np.maximum(minimum - ratio, ratio - maximum)
    index = int(np.argmax(np.where(low | high, distance, -np.inf)))
    group_index = int(groups[index])
    value = float(ratio[index])
    report.nu_ratio_worst = f"{label}: group={group_index + 1} nu={value:.6e}"
    report.nu_ratio_warnings.append(
        f"mixture {label}: nu_fission/fission={value:.6e} in group "
        f"{group_index + 1} is outside [{minimum:.6e}, {maximum:.6e}]"
    )


def _check_transport_p1(
    report: _MutablePhysicsReport,
    *,
    label: str,
    total: np.ndarray | None,
    transport_total: np.ndarray | None,
    scatter: np.ndarray | None,
    axes: str | None,
    energy_groups: int,
    legendre_order: int,
    threshold: float,
) -> None:
    if total is None or transport_total is None or scatter is None:
        return
    p1 = scatter_moment_matrix(scatter, axes, energy_groups, legendre_order, moment=1)
    if p1 is None:
        return
    if not (
        np.all(np.isfinite(total))
        and np.all(np.isfinite(transport_total))
        and np.all(np.isfinite(p1))
    ):
        return
    report.transport_p1_checked += 1
    derived = total - p1.sum(axis=1)
    residual = transport_total - derived
    _, max_abs, max_rel, index = _relative_worst(residual, transport_total)
    _update_worst(
        current=report,
        attr_rel="transport_p1_max_rel",
        attr_abs="transport_p1_max_abs",
        attr_worst="transport_p1_worst",
        max_rel=max_rel,
        max_abs=max_abs,
        worst=(
            f"{label}: group={index + 1} transport_total={transport_total[index]:.6e} "
            f"p1_derived={derived[index]:.6e}"
        ),
    )
    if max_rel > threshold:
        report.transport_p1_errors.append(
            "transport_total/P1 max relative residual "
            f"{max_rel:.6e} (abs {max_abs:.6e}) at {label}: group={index + 1} "
            f"exceeds fail threshold {threshold:.6e}"
        )


def scatter_moment_matrix(
    values: np.ndarray,
    axes: str | None,
    ngroups: int,
    legendre_order: int,
    *,
    moment: int,
) -> np.ndarray | None:
    expected_moments = legendre_order + 1
    if moment >= expected_moments or values.ndim != 3:
        return None
    normalized = normalize_axes(axes)
    moment_first = values.shape == (expected_moments, ngroups, ngroups)
    moment_last = values.shape == (ngroups, ngroups, expected_moments)
    if normalized in MOMENT_FIRST_SCATTER_AXES and moment_first:
        return values[moment]
    if normalized in MOMENT_LAST_SCATTER_AXES and moment_last:
        return values[:, :, moment]
    if axes is not None:
        return None
    if moment_first and not moment_last:
        return values[moment]
    if moment_last and not moment_first:
        return values[:, :, moment]
    return None


def _finalize_adf_faces(
    report: _MutablePhysicsReport,
    adf_names_by_calc: list[tuple[str, ...]],
) -> None:
    if not adf_names_by_calc:
        return
    present = [names for names in adf_names_by_calc if names]
    report.adf_calculations = len(present)
    if not present:
        return
    first = present[0]
    report.adf_faces = first
    for index, names in enumerate(adf_names_by_calc, start=1):
        if names != first:
            report.adf_face_errors.append(
                f"calculation index {index}: ADF faces {names!r} do not match {first!r}"
            )
            return


def _iter_calculations(h5: Any, mixture_names: tuple[str, ...]):
    mixtures = h5["mixtures"]
    for mixture_name in mixture_names:
        mixture = mixtures[mixture_name]
        if "states" in mixture:
            states = mixture["states"]
            for state_name in _sorted_state_names(states):
                yield f"{mixture_name}/states/{state_name}", states[state_name], mixture
        else:
            yield mixture_name, mixture, None


def _sorted_state_names(states_group: Any) -> list[str]:
    def key(name: str) -> tuple[int, int | str]:
        try:
            return (0, int(name))
        except ValueError:
            return (1, name)

    return sorted(states_group.keys(), key=key)


def _vector_or_none(group: Any, name: str, ngroups: int) -> np.ndarray | None:
    if name not in group:
        return None
    try:
        values = np.asarray(group[name][:], dtype=float).reshape(-1)
    except (TypeError, ValueError, OSError):
        return None
    if values.shape != (ngroups,):
        return None
    return values


def _scatter_or_none(group: Any, name: str) -> np.ndarray | None:
    if name not in group:
        return None
    try:
        return np.asarray(group[name][:], dtype=float)
    except (TypeError, ValueError, OSError):
        return None


def _scatter_axes(group: Any, h5: Any, parent_group: Any | None) -> str | None:
    sources = [group.attrs]
    if parent_group is not None:
        sources.append(parent_group.attrs)
    sources.append(h5.attrs)
    for source in sources:
        for key in ("scatter_axes", "axes"):
            if key in source:
                return _attr_text(source[key])
    return None


def _adf_names(group: Any) -> tuple[str, ...]:
    for name in ("adf", "ADF", "discontinuity_factors"):
        if name not in group:
            continue
        obj = group[name]
        if hasattr(obj, "keys"):
            return tuple(str(face_name) for face_name in obj)
        values = np.asarray(obj[:], dtype=float)
        for key in ("names", "face_names", "adf_names"):
            if key in obj.attrs:
                return tuple(
                    _attr_text(value)
                    for value in np.asarray(obj.attrs[key]).reshape(-1)
                )
        if values.ndim == 1:
            return ("FD_B",)
        if values.ndim == 2:
            return tuple(f"FD_{index + 1:05d}" for index in range(values.shape[0]))
    return ()


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


def _attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8")
    return str(value)


def _relative_worst(
    residual: np.ndarray,
    denominator: np.ndarray,
) -> tuple[np.ndarray, float, float, int]:
    abs_residual = np.abs(residual)
    relative = abs_residual / np.maximum(np.abs(denominator), 1.0e-30)
    index = int(np.argmax(relative))
    return relative, float(abs_residual[index]), float(relative[index]), index


def _update_worst(
    *,
    current: _MutablePhysicsReport,
    attr_rel: str,
    attr_abs: str,
    attr_worst: str,
    max_rel: float,
    max_abs: float,
    worst: str,
) -> None:
    current_rel = getattr(current, attr_rel)
    if current_rel is None or max_rel > current_rel:
        setattr(current, attr_rel, max_rel)
        setattr(current, attr_abs, max_abs)
        setattr(current, attr_worst, worst)
