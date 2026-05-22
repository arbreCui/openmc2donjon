"""Execution phase for the fixed-OpenMC SPH loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sph_loop_convergence import (
    SphLoopConvergenceReport,
    build_convergence_report,
)
from .sph_loop_plan import SphLoopPlan
from .sph_loop_preflight import SphLoopFluxMapPreflightReport
from .sph_loop_records import SphLoopPostprocessReport, SphLoopSolveReport
from .sph_loop_runner import run_postprocessor, run_solver
from .sph_workflow import SphIterationWorkflowReport, run_sph_iteration_workflow


@dataclass(frozen=True)
class SphLoopExecution:
    solves: tuple[SphLoopSolveReport, ...]
    workflows: tuple[SphIterationWorkflowReport, ...]
    convergence: tuple[SphLoopConvergenceReport, ...]
    postprocesses: tuple[SphLoopPostprocessReport, ...]
    final_solve: SphLoopSolveReport | None
    final_ascii: Path
    final_sph_sidecar: Path | None
    stop_reason: str


@dataclass(frozen=True)
class _IterationExecution:
    solve: SphLoopSolveReport
    workflow: SphIterationWorkflowReport
    convergence: SphLoopConvergenceReport
    postprocess: SphLoopPostprocessReport | None
    next_ascii: Path
    next_sph: Path


def execute_loop(
    plan: SphLoopPlan,
    *,
    initial_ascii: Path,
    preflight: SphLoopFluxMapPreflightReport,
    force: bool,
) -> SphLoopExecution:
    solves: list[SphLoopSolveReport] = []
    workflows: list[SphIterationWorkflowReport] = []
    convergence: list[SphLoopConvergenceReport] = []
    postprocesses: list[SphLoopPostprocessReport] = []
    current_ascii = initial_ascii
    current_sph: Path | None = None
    stop_reason = "max_iterations"

    for iteration in range(plan.iterations):
        step = _run_iteration(
            plan,
            iteration=iteration,
            current_ascii=current_ascii,
            previous_sph=current_sph,
            preflight=preflight,
            force=force,
        )
        solves.append(step.solve)
        workflows.append(step.workflow)
        convergence.append(step.convergence)
        if step.postprocess is not None:
            postprocesses.append(step.postprocess)
        current_ascii = step.next_ascii
        current_sph = step.next_sph
        if plan.convergence_enabled and step.convergence.converged:
            stop_reason = "converged"
            break

    final_solve = None
    if plan.run_final_solve:
        final_solve = _run_solve(
            plan,
            iteration=len(workflows),
            ascii_input=current_ascii,
            previous_sph=current_sph,
            preflight=preflight,
            force=force,
        )
        solves.append(final_solve)

    return SphLoopExecution(
        solves=tuple(solves),
        workflows=tuple(workflows),
        convergence=tuple(convergence),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
        final_ascii=current_ascii,
        final_sph_sidecar=current_sph,
        stop_reason=stop_reason,
    )


def _run_iteration(
    plan: SphLoopPlan,
    *,
    iteration: int,
    current_ascii: Path,
    previous_sph: Path | None,
    preflight: SphLoopFluxMapPreflightReport,
    force: bool,
) -> _IterationExecution:
    solve = _run_solve(
        plan,
        iteration=iteration,
        ascii_input=current_ascii,
        previous_sph=previous_sph,
        preflight=preflight,
        force=force,
    )
    workflow = _run_workflow(
        plan,
        iteration=iteration,
        solve=solve,
        previous_sph=previous_sph,
        force=force,
    )
    convergence = build_convergence_report(
        workflow,
        input_h5=plan.input_h5,
        previous_sph=previous_sph,
        iteration=iteration + 1,
        sph_change_tolerance=plan.sph_change_tolerance,
        flux_ratio_tolerance=plan.flux_ratio_tolerance,
        min_iterations=plan.min_iterations,
    )
    postprocess = _run_postprocess(
        plan,
        iteration=iteration,
        solve=solve,
        workflow=workflow,
        current_sph=workflow.sph_sidecar,
        force=force,
    )
    return _IterationExecution(
        solve=solve,
        workflow=workflow,
        convergence=convergence,
        postprocess=postprocess,
        next_ascii=workflow.ascii_output if postprocess is None else postprocess.output,
        next_sph=workflow.sph_sidecar,
    )


def _run_solve(
    plan: SphLoopPlan,
    *,
    iteration: int,
    ascii_input: Path,
    previous_sph: Path | None,
    preflight: SphLoopFluxMapPreflightReport,
    force: bool,
) -> SphLoopSolveReport:
    return run_solver(
        plan.solver,
        base_dir=plan.base_dir,
        loop_dir=plan.loop_dir,
        iteration=iteration,
        input_h5=plan.input_h5,
        ascii_input=ascii_input,
        previous_sph=previous_sph,
        energy_groups=preflight.energy_groups,
        list_offset=plan.list_offset,
        force=force,
    )


def _run_workflow(
    plan: SphLoopPlan,
    *,
    iteration: int,
    solve: SphLoopSolveReport,
    previous_sph: Path | None,
    force: bool,
) -> SphIterationWorkflowReport:
    return run_sph_iteration_workflow(
        plan.input_h5,
        plan.loop_dir / f"iter{iteration + 1:02d}_sph",
        reference_flux=plan.reference_flux,
        flux_dump=solve.result,
        map_h5=plan.map_h5,
        scalar_flux_ids=plan.scalar_flux_ids,
        scalar_flux_column=plan.scalar_flux_column,
        list_offset=plan.list_offset,
        previous_sph=previous_sph,
        damping=plan.damping,
        clip_min=plan.clip_min,
        clip_max=plan.clip_max,
        output_format=plan.output_format,
        root_name=plan.root_name,
        h_factor_default=plan.h_factor_default,
        sph_kind=f"{plan.sph_kind}-iter{iteration + 1}",
        sph_real=plan.sph_real,
        sph_applied=plan.sph_applied,
        source_label=f"{plan.source_label}: iteration {iteration + 1}",
        force=force,
    )


def _run_postprocess(
    plan: SphLoopPlan,
    *,
    iteration: int,
    solve: SphLoopSolveReport,
    workflow: SphIterationWorkflowReport,
    current_sph: Path,
    force: bool,
) -> SphLoopPostprocessReport | None:
    if plan.postprocessor is None:
        return None
    return run_postprocessor(
        plan.postprocessor,
        base_dir=plan.base_dir,
        loop_dir=plan.loop_dir,
        iteration=iteration,
        input_h5=plan.input_h5,
        solve_result=solve.result,
        workflow=workflow,
        previous_sph=current_sph,
        output_format=plan.output_format,
        force=force,
    )
