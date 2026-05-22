"""Convergence metrics for the fixed-OpenMC SPH loop."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

import numpy as np

from .sph_augment import load_sph_source
from .sph_workflow import SphIterationWorkflowReport


@dataclass(frozen=True)
class SphLoopConvergenceReport:
    iteration: int
    sph_max_abs_change: float
    sph_max_rel_change: float
    flux_ratio_max_residual: float
    clipped_count: int
    clipped_fraction: float
    converged: bool


@dataclass(frozen=True)
class _SphUpdateMetrics:
    flux_ratio_max_residual: float
    clipped_count: int
    clipped_fraction: float


class _WorkflowLike(Protocol):
    sph_sidecar: Path
    output_dir: Path


def build_convergence_report(
    workflow: SphIterationWorkflowReport | _WorkflowLike,
    *,
    input_h5: Path,
    previous_sph: Path | None,
    iteration: int,
    sph_change_tolerance: float | None,
    flux_ratio_tolerance: float | None,
    min_iterations: int,
) -> SphLoopConvergenceReport:
    current = _load_sph_matrix(workflow.sph_sidecar, input_h5=input_h5)
    previous = (
        np.ones_like(current)
        if previous_sph is None
        else _load_sph_matrix(previous_sph, input_h5=input_h5)
    )
    if previous.shape != current.shape:
        raise ValueError(
            "previous/current SPH shapes do not match: "
            f"{previous.shape} != {current.shape}"
        )
    abs_change = np.abs(current - previous)
    rel_change = abs_change / np.maximum(np.abs(previous), 1.0e-30)
    update_metrics = _read_sph_update_metrics(workflow, total_bins=int(current.size))
    checks: list[bool] = []
    if sph_change_tolerance is not None:
        checks.append(float(np.max(rel_change)) <= sph_change_tolerance)
    if flux_ratio_tolerance is not None:
        checks.append(update_metrics.flux_ratio_max_residual <= flux_ratio_tolerance)
    converged = bool(checks and all(checks) and iteration >= min_iterations)
    return SphLoopConvergenceReport(
        iteration=iteration,
        sph_max_abs_change=float(np.max(abs_change)),
        sph_max_rel_change=float(np.max(rel_change)),
        flux_ratio_max_residual=update_metrics.flux_ratio_max_residual,
        clipped_count=update_metrics.clipped_count,
        clipped_fraction=update_metrics.clipped_fraction,
        converged=converged,
    )


def _read_sph_update_metrics(
    workflow: SphIterationWorkflowReport | _WorkflowLike,
    *,
    total_bins: int,
) -> _SphUpdateMetrics:
    summary_path = workflow.output_dir / "next_sph_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    raw_min = float(payload["raw_update_minimum"])
    raw_max = float(payload["raw_update_maximum"])
    clipped_count = int(payload.get("clipped_count", 0))
    clipped_fraction = clipped_count / max(total_bins, 1)
    return _SphUpdateMetrics(
        flux_ratio_max_residual=max(abs(raw_min - 1.0), abs(raw_max - 1.0)),
        clipped_count=clipped_count,
        clipped_fraction=clipped_fraction,
    )


def _load_sph_matrix(path: Path, *, input_h5: Path) -> np.ndarray:
    mixture_names, energy_groups = _read_input_metadata(input_h5)
    loaded = load_sph_source(
        path,
        mixture_names=mixture_names,
        energy_groups=energy_groups,
    )
    return np.stack([loaded.sph[name] for name in mixture_names])


def _read_input_metadata(path: Path) -> tuple[tuple[str, ...], int]:
    import h5py

    with h5py.File(path, "r") as h5:
        if "mixtures" not in h5 or not hasattr(h5["mixtures"], "keys"):
            raise ValueError("input HDF5 must contain a /mixtures group")
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
