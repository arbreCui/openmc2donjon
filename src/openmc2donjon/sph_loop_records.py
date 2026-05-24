"""Immutable records shared by the SPH loop modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .hdf5_metadata import Hdf5DatasetMetadata
from .sph_loop_acceptance import SphLoopAcceptanceReport
from .sph_loop_convergence import SphLoopConvergenceReport
from .sph_loop_preflight import SphLoopFluxMapPreflightReport
from .sph_workflow import SphIterationWorkflowReport


@dataclass(frozen=True)
class SphLoopSolveReport:
    iteration: int
    command: tuple[str, ...]
    cwd: Path
    ascii_input: Path
    result: Path
    stdout: Path
    stderr: Path
    returncode: int
    result_bytes: int
    flux_vector_count: int
    flux_unknown_count: int
    keff: float | None


@dataclass(frozen=True)
class SphLoopPostprocessReport:
    iteration: int
    command: tuple[str, ...]
    cwd: Path
    workflow_ascii: Path
    output: Path
    sph_sidecar: Path
    stdout: Path
    stderr: Path
    returncode: int
    output_bytes: int
    block_count: int


@dataclass(frozen=True)
class SphLoopAuditRow:
    stage: str
    iteration: int
    keff: float | None
    sph_minimum: float | None
    sph_maximum: float | None
    sph_max_abs_change: float | None
    sph_max_rel_change: float | None
    flux_ratio_max_residual: float | None
    worst_residual_mixture: str | None
    worst_residual_group: int | None
    worst_residual_raw_update: float | None
    worst_residual: float | None
    worst_residual_bins: tuple[dict[str, object], ...]
    converged: bool | None
    solve_result: Path | None
    ascii_output: Path | None
    postprocess_output: Path | None


@dataclass(frozen=True)
class SphLoopWorkflowMetadata:
    iteration: int
    donjon_volume_flux: Hdf5DatasetMetadata
    sph_sidecar: Hdf5DatasetMetadata


@dataclass(frozen=True)
class SphLoopArtifactMetadata:
    reference_flux: Hdf5DatasetMetadata
    workflows: tuple[SphLoopWorkflowMetadata, ...]
    final_sph_sidecar: Hdf5DatasetMetadata | None


@dataclass(frozen=True)
class SphLoopReport:
    config_path: Path
    input_h5: Path
    output_dir: Path
    reference_flux: str
    iterations: int
    completed_iterations: int
    output_format: str
    initial_ascii: Path
    final_ascii: Path
    final_sph_sidecar: Path | None
    summary_json: Path
    audit_csv: Path
    audit_text: Path
    bundle_manifest: Path | None
    run_script: Path | None
    convergence_enabled: bool
    converged: bool
    stop_reason: str
    sph_change_tolerance: float | None
    flux_ratio_tolerance: float | None
    min_iterations: int
    fail_on_nonconvergence: bool
    flux_map_preflight: SphLoopFluxMapPreflightReport
    solves: tuple[SphLoopSolveReport, ...]
    workflows: tuple[SphIterationWorkflowReport, ...]
    convergence: tuple[SphLoopConvergenceReport, ...]
    postprocesses: tuple[SphLoopPostprocessReport, ...]
    final_solve: SphLoopSolveReport | None
    audit_rows: tuple[SphLoopAuditRow, ...]
    acceptance: SphLoopAcceptanceReport
    artifact_metadata: SphLoopArtifactMetadata
