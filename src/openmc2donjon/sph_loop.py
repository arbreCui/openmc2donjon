"""Production SPH loop driver around a user-supplied DONJON solve command."""

from __future__ import annotations

from pathlib import Path

from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import convert_mgxs_hdf5
from .sph_loop_config import CONFIG_SCHEMA
from .sph_loop_acceptance import build_acceptance_report
from .sph_loop_convergence import (
    SphLoopConvergenceReport,
    build_convergence_report,
)
from .sph_loop_plan import build_sph_loop_plan
from .sph_loop_preflight import (
    build_flux_map_preflight_report,
    format_failure as format_preflight_failure,
)
from .sph_loop_report import (
    PASS_DECISION,
    SCHEMA,
    SphLoopPostprocessReport,
    SphLoopReport,
    SphLoopSolveReport,
    build_audit_rows,
    print_report,
    write_audit_csv,
    write_audit_text,
    write_bundle,
    write_summary,
)
from .sph_loop_runner import require_absent, run_postprocessor, run_solver
from .sph_workflow import SphIterationWorkflowReport, run_sph_iteration_workflow


def run_sph_loop(
    config_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    force: bool = False,
    summary_json: str | Path | None = None,
    bundle_dir: str | Path | None = None,
    bundle_manifest_name: str = "manifest.json",
) -> SphLoopReport:
    """Run a fixed-OpenMC SPH loop using a JSON configuration file.

    The loop keeps the OpenMC MGXS HDF5 immutable.  Each cycle runs the user
    supplied DONJON command with the current ASCII handoff, extracts the
    resulting low-order flux, computes the next SPH sidecar, and writes the
    next ASCII handoff for the following cycle.
    """

    plan = build_sph_loop_plan(
        config_path,
        output_dir=output_dir,
        summary_json=summary_json,
        bundle_dir=bundle_dir,
        bundle_manifest_name=bundle_manifest_name,
    )
    plan.loop_dir.mkdir(parents=True, exist_ok=True)
    flux_map_preflight = build_flux_map_preflight_report(
        input_h5=plan.input_h5,
        reference_flux=plan.reference_flux,
        map_h5=plan.map_h5,
        scalar_flux_ids=plan.scalar_flux_ids,
        scalar_flux_column=plan.scalar_flux_column,
    )
    if not flux_map_preflight.passed:
        raise ValueError(format_preflight_failure(flux_map_preflight))

    initial_ascii = _write_initial_ascii(
        plan.input_h5,
        plan.loop_dir,
        output_format=plan.output_format,
        root_name=plan.root_name,
        h_factor_default=plan.h_factor_default,
        force=force,
    )

    solves: list[SphLoopSolveReport] = []
    workflows: list[SphIterationWorkflowReport] = []
    convergence_reports: list[SphLoopConvergenceReport] = []
    postprocesses: list[SphLoopPostprocessReport] = []
    current_ascii = initial_ascii
    previous_sph: Path | None = None
    stop_reason = "max_iterations"

    for iteration in range(plan.iterations):
        sph_before_iteration = previous_sph
        solve_report = run_solver(
            plan.solver,
            base_dir=plan.base_dir,
            loop_dir=plan.loop_dir,
            iteration=iteration,
            input_h5=plan.input_h5,
            ascii_input=current_ascii,
            previous_sph=previous_sph,
            energy_groups=flux_map_preflight.energy_groups,
            list_offset=plan.list_offset,
            force=force,
        )
        solves.append(solve_report)

        workflow_dir = plan.loop_dir / f"iter{iteration + 1:02d}_sph"
        workflow = run_sph_iteration_workflow(
            plan.input_h5,
            workflow_dir,
            reference_flux=plan.reference_flux,
            flux_dump=solve_report.result,
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
        workflows.append(workflow)
        current_ascii = workflow.ascii_output
        convergence_report = build_convergence_report(
            workflow,
            input_h5=plan.input_h5,
            previous_sph=sph_before_iteration,
            iteration=iteration + 1,
            sph_change_tolerance=plan.sph_change_tolerance,
            flux_ratio_tolerance=plan.flux_ratio_tolerance,
            min_iterations=plan.min_iterations,
        )
        convergence_reports.append(convergence_report)
        previous_sph = workflow.sph_sidecar
        if plan.postprocessor is not None:
            postprocess = run_postprocessor(
                plan.postprocessor,
                base_dir=plan.base_dir,
                loop_dir=plan.loop_dir,
                iteration=iteration,
                input_h5=plan.input_h5,
                solve_result=solve_report.result,
                workflow=workflow,
                previous_sph=previous_sph,
                output_format=plan.output_format,
                force=force,
            )
            postprocesses.append(postprocess)
            current_ascii = postprocess.output
        if plan.convergence_enabled and convergence_report.converged:
            stop_reason = "converged"
            break

    final_solve = None
    if plan.run_final_solve:
        final_iteration = len(workflows)
        final_solve = run_solver(
            plan.solver,
            base_dir=plan.base_dir,
            loop_dir=plan.loop_dir,
            iteration=final_iteration,
            input_h5=plan.input_h5,
            ascii_input=current_ascii,
            previous_sph=previous_sph,
            energy_groups=flux_map_preflight.energy_groups,
            list_offset=plan.list_offset,
            force=force,
        )
        solves.append(final_solve)

    converged = bool(convergence_reports and convergence_reports[-1].converged)
    audit_rows = build_audit_rows(
        solves=tuple(solves),
        workflows=tuple(workflows),
        convergence=tuple(convergence_reports),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
        final_ascii=current_ascii,
    )
    acceptance = build_acceptance_report(
        plan.normalized_acceptance,
        audit_rows=audit_rows,
        convergence=tuple(convergence_reports),
        completed_iterations=len(workflows),
        converged=converged,
        final_solve=final_solve,
    )
    report = SphLoopReport(
        config_path=plan.config_path,
        input_h5=plan.input_h5,
        output_dir=plan.loop_dir,
        reference_flux=plan.reference_flux,
        iterations=plan.iterations,
        completed_iterations=len(workflows),
        output_format=plan.output_format,
        initial_ascii=initial_ascii,
        final_ascii=current_ascii,
        final_sph_sidecar=previous_sph,
        summary_json=plan.summary_path,
        audit_csv=plan.audit_csv,
        audit_text=plan.audit_text,
        bundle_manifest=plan.bundle_manifest,
        convergence_enabled=plan.convergence_enabled,
        converged=converged,
        stop_reason=stop_reason,
        sph_change_tolerance=plan.sph_change_tolerance,
        flux_ratio_tolerance=plan.flux_ratio_tolerance,
        min_iterations=plan.min_iterations,
        flux_map_preflight=flux_map_preflight,
        solves=tuple(solves),
        workflows=tuple(workflows),
        convergence=tuple(convergence_reports),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
        audit_rows=audit_rows,
        acceptance=acceptance,
    )
    write_audit_csv(plan.audit_csv, report.audit_rows)
    write_audit_text(
        plan.audit_text,
        report.audit_rows,
        flux_map_preflight=report.flux_map_preflight,
    )
    write_summary(plan.summary_path, report)
    if plan.bundle_dir is not None:
        write_bundle(
            report,
            output_dir=plan.bundle_dir,
            manifest_name=bundle_manifest_name,
            force=force,
        )
    print_report(report)
    if (
        plan.convergence_enabled
        and plan.fail_on_nonconvergence
        and not report.converged
    ):
        raise RuntimeError(
            "SPH loop did not converge within "
            f"{report.iterations} iteration(s); see {plan.summary_path}"
        )
    if report.acceptance.enabled and report.acceptance.fail_on_violation:
        if not report.acceptance.passed:
            failed = ", ".join(
                check.name for check in report.acceptance.checks if not check.passed
            )
            failed_suffix = f": {failed}" if failed else ""
            raise RuntimeError(
                f"SPH loop acceptance criteria failed{failed_suffix}; see "
                f"{plan.summary_path} and {plan.audit_csv}"
            )
    return report


def _write_initial_ascii(
    input_h5: Path,
    loop_dir: Path,
    *,
    output_format: str,
    root_name: str,
    h_factor_default: float | None,
    force: bool,
) -> Path:
    output_dir = loop_dir / "iter00_initial"
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "macrolib.txt" if output_format == "macrolib" else "mcompo.txt"
    output = output_dir / f"out.{suffix}"
    require_absent(output, force=force)
    if output_format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            input_h5,
            output,
            h_factor_default=h_factor_default,
        )
    else:
        convert_mgxs_hdf5(
            input_h5,
            output,
            root_name=root_name,
            comment=f"Initial SPH loop handoff from {input_h5.name}",
            h_factor_default=h_factor_default,
        )
    return output
