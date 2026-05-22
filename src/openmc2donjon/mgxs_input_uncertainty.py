"""Statistical-uncertainty checks for MGXS HDF5 inputs."""

from __future__ import annotations

from dataclasses import dataclass

import h5py
import numpy as np

from .mgxs_input_report import InputReport
from .mgxs_input_scatter import (
    MOMENT_FIRST_SCATTER_AXES,
    MOMENT_LAST_SCATTER_AXES,
    normalize_axes,
)


STD_DEV_SUFFIX = "_std_dev"
TOP_FINDING_LIMIT = 5


@dataclass(frozen=True)
class UncertaintyConfig:
    warn_threshold: float | None = 0.05
    fail_threshold: float | None = None
    production_fail_threshold: float | None = None
    mean_abs_floor: float = 1.0e-12


def configure_uncertainty(report: InputReport, config: UncertaintyConfig) -> None:
    report.uncertainty_checked = (
        config.warn_threshold is not None
        or config.fail_threshold is not None
        or config.production_fail_threshold is not None
    )
    report.uncertainty_warn_threshold = config.warn_threshold
    report.uncertainty_fail_threshold = config.fail_threshold
    report.uncertainty_production_fail_threshold = config.production_fail_threshold
    report.uncertainty_mean_abs_floor = config.mean_abs_floor
    if config.warn_threshold is not None and config.warn_threshold < 0.0:
        report.fail("--uncertainty-warn must be non-negative")
    if config.fail_threshold is not None and config.fail_threshold < 0.0:
        report.fail("--uncertainty-fail must be non-negative")
    if (
        config.production_fail_threshold is not None
        and config.production_fail_threshold < 0.0
    ):
        report.fail("--uncertainty-production-fail must be non-negative")
    if config.mean_abs_floor < 0.0:
        report.fail("--uncertainty-mean-abs-floor must be non-negative")


def validate_uncertainty_for_calculation(
    group: h5py.Group,
    name: str,
    mean_dataset_names: tuple[str, ...],
    *,
    scatter_axes: str | None,
    ngroups: int,
    legendre_order: int,
    report: InputReport,
) -> None:
    if not report.uncertainty_checked:
        return

    for dataset_name in mean_dataset_names:
        if dataset_name not in group:
            continue
        report.uncertainty_expected_datasets += 1
        std_name = f"{dataset_name}{STD_DEV_SUFFIX}"
        if std_name not in group:
            continue
        report.uncertainty_datasets += 1
        _validate_std_dev_dataset(
            mean=group[dataset_name],
            std_dev=group[std_name],
            name=name,
            dataset_name=dataset_name,
            scatter_axes=scatter_axes,
            ngroups=ngroups,
            legendre_order=legendre_order,
            report=report,
        )

    for dataset_name in group:
        if not str(dataset_name).endswith(STD_DEV_SUFFIX):
            continue
        base_name = str(dataset_name)[: -len(STD_DEV_SUFFIX)]
        if base_name not in group:
            report.fail(
                f"mixture {name}: {dataset_name} has no matching {base_name} dataset"
            )


def finalize_uncertainty(report: InputReport) -> None:
    if not report.uncertainty_checked:
        return
    _warn_missing_std_dev_coverage(report)
    if report.uncertainty_max_rel is None:
        return
    detail = (
        "MGXS statistical uncertainty max relative sigma "
        f"{report.uncertainty_max_rel:.6e} at {report.uncertainty_worst}"
    )
    fail_threshold = report.uncertainty_fail_threshold
    production_fail_threshold = report.uncertainty_production_fail_threshold
    warn_threshold = report.uncertainty_warn_threshold
    if (
        production_fail_threshold is not None
        and report.uncertainty_production_max_rel is not None
        and report.uncertainty_production_max_rel > production_fail_threshold
    ):
        report.fail(
            "MGXS production uncertainty max relative sigma "
            f"{report.uncertainty_production_max_rel:.6e} at "
            f"{report.uncertainty_production_worst} exceeds production fail "
            f"threshold {production_fail_threshold:.6e}"
        )
    if fail_threshold is not None and report.uncertainty_max_rel > fail_threshold:
        report.fail(f"{detail} exceeds fail threshold {fail_threshold:.6e}")
    elif warn_threshold is not None and report.uncertainty_max_rel > warn_threshold:
        report.warn(f"{detail} exceeds warn threshold {warn_threshold:.6e}")


def _warn_missing_std_dev_coverage(report: InputReport) -> None:
    missing = report.uncertainty_expected_datasets - report.uncertainty_datasets
    if missing <= 0:
        return
    if (
        report.uncertainty_fail_threshold is None
        and report.uncertainty_production_fail_threshold is None
    ):
        return
    report.warn(
        "MGXS statistical uncertainty std_dev coverage incomplete: "
        f"{report.uncertainty_datasets}/{report.uncertainty_expected_datasets} "
        f"dataset(s) present, {missing} missing; export OpenMC MGXS *_std_dev "
        "datasets to make tally noise visible in preflight"
    )


def _validate_std_dev_dataset(
    *,
    mean: h5py.Dataset,
    std_dev: h5py.Dataset,
    name: str,
    dataset_name: str,
    scatter_axes: str | None,
    ngroups: int,
    legendre_order: int,
    report: InputReport,
) -> None:
    if std_dev.shape != mean.shape:
        report.fail(
            f"mixture {name}: {std_dev.name.rsplit('/', maxsplit=1)[-1]} shape "
            f"{std_dev.shape} must match {dataset_name} shape {mean.shape}"
        )
        return
    std_values = np.asarray(std_dev[:], dtype=float)
    if not np.all(np.isfinite(std_values)):
        report.fail(f"mixture {name}: {std_dev.name} contains non-finite values")
        return
    if np.any(std_values < 0.0):
        report.fail(f"mixture {name}: {std_dev.name} contains negative values")
        return
    mean_values = np.asarray(mean[:], dtype=float)
    if not np.all(np.isfinite(mean_values)):
        return

    mask = np.abs(mean_values) > report.uncertainty_mean_abs_floor
    if not np.any(mask):
        return
    rel = np.zeros_like(mean_values, dtype=float)
    rel[mask] = std_values[mask] / np.abs(mean_values[mask])
    report.uncertainty_bins_checked += int(np.count_nonzero(mask))
    index = tuple(
        int(value) for value in np.unravel_index(int(np.argmax(rel)), rel.shape)
    )
    max_rel = float(rel[index])
    detail = _finding_detail(
        name=name,
        dataset_name=dataset_name,
        index=index,
        mean=float(mean_values[index]),
        std_dev=float(std_values[index]),
        rel=max_rel,
        scatter_axes=scatter_axes,
        shape=mean_values.shape,
        ngroups=ngroups,
        legendre_order=legendre_order,
    )
    _record_finding(report, max_rel, detail)

    production_mask = mask & _production_gate_mask(
        dataset_name=dataset_name,
        shape=mean_values.shape,
        scatter_axes=scatter_axes,
        ngroups=ngroups,
        legendre_order=legendre_order,
    )
    if not np.any(production_mask):
        return
    production_rel = np.zeros_like(mean_values, dtype=float)
    production_rel[production_mask] = rel[production_mask]
    report.uncertainty_production_bins_checked += int(
        np.count_nonzero(production_mask)
    )
    production_index = tuple(
        int(value)
        for value in np.unravel_index(int(np.argmax(production_rel)), rel.shape)
    )
    production_max_rel = float(production_rel[production_index])
    production_detail = _finding_detail(
        name=name,
        dataset_name=dataset_name,
        index=production_index,
        mean=float(mean_values[production_index]),
        std_dev=float(std_values[production_index]),
        rel=production_max_rel,
        scatter_axes=scatter_axes,
        shape=mean_values.shape,
        ngroups=ngroups,
        legendre_order=legendre_order,
    )
    _record_production_finding(report, production_max_rel, production_detail)


def _record_finding(report: InputReport, rel: float, detail: str) -> None:
    if report.uncertainty_max_rel is None or rel > report.uncertainty_max_rel:
        report.uncertainty_max_rel = rel
        report.uncertainty_worst = detail
    threshold = report.uncertainty_warn_threshold
    if threshold is None or rel <= threshold:
        return
    report.uncertainty_top.append(detail)
    report.uncertainty_top.sort(key=_rel_from_detail, reverse=True)
    del report.uncertainty_top[TOP_FINDING_LIMIT:]


def _record_production_finding(report: InputReport, rel: float, detail: str) -> None:
    if (
        report.uncertainty_production_max_rel is None
        or rel > report.uncertainty_production_max_rel
    ):
        report.uncertainty_production_max_rel = rel
        report.uncertainty_production_worst = detail


def _rel_from_detail(detail: str) -> float:
    marker = " rel="
    if marker not in detail:
        return 0.0
    try:
        return float(detail.rsplit(marker, maxsplit=1)[-1])
    except ValueError:
        return 0.0


def _production_gate_mask(
    *,
    dataset_name: str,
    shape: tuple[int, ...],
    scatter_axes: str | None,
    ngroups: int,
    legendre_order: int,
) -> np.ndarray:
    if dataset_name != "scatter_matrix":
        return np.ones(shape, dtype=bool)
    if len(shape) == 2:
        return np.ones(shape, dtype=bool)
    if len(shape) != 3:
        return np.ones(shape, dtype=bool)

    mask = np.zeros(shape, dtype=bool)
    moment_axis = _scatter_moment_axis(
        scatter_axes,
        shape,
        ngroups=ngroups,
        legendre_order=legendre_order,
    )
    if moment_axis is None:
        return np.ones(shape, dtype=bool)
    selector = [slice(None)] * len(shape)
    selector[moment_axis] = 0
    mask[tuple(selector)] = True
    return mask


def _scatter_moment_axis(
    axes: str | None,
    shape: tuple[int, ...],
    *,
    ngroups: int,
    legendre_order: int,
) -> int | None:
    expected_moments = legendre_order + 1
    normalized = normalize_axes(axes)
    moment_first = shape == (expected_moments, ngroups, ngroups)
    moment_last = shape == (ngroups, ngroups, expected_moments)
    if normalized in MOMENT_FIRST_SCATTER_AXES or (
        axes is None and moment_first and not moment_last
    ):
        return 0
    if normalized in MOMENT_LAST_SCATTER_AXES or (
        axes is None and moment_last and not moment_first
    ):
        return 2
    return None


def _finding_detail(
    *,
    name: str,
    dataset_name: str,
    index: tuple[int, ...],
    mean: float,
    std_dev: float,
    rel: float,
    scatter_axes: str | None,
    shape: tuple[int, ...],
    ngroups: int,
    legendre_order: int,
) -> str:
    location = _scatter_location(index, scatter_axes, shape, ngroups, legendre_order)
    if dataset_name != "scatter_matrix":
        location = f"g={index[0] + 1}" if index else "scalar"
    return (
        f"{name}: {dataset_name} {location} "
        f"mean={mean:.6e} std_dev={std_dev:.6e} rel={rel:.6e}"
    )


def _scatter_location(
    index: tuple[int, ...],
    axes: str | None,
    shape: tuple[int, ...],
    ngroups: int,
    legendre_order: int,
) -> str:
    if len(index) == 2:
        return f"moment=0 from={index[0] + 1} to={index[1] + 1}"
    if len(index) != 3:
        return f"index={index}"
    moment_axis = _scatter_moment_axis(
        axes,
        shape,
        ngroups=ngroups,
        legendre_order=legendre_order,
    )
    if moment_axis == 0:
        return f"moment={index[0]} from={index[1] + 1} to={index[2] + 1}"
    if moment_axis == 2:
        return f"moment={index[2]} from={index[0] + 1} to={index[1] + 1}"
    return f"index={index}"
