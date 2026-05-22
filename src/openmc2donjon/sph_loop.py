"""Production SPH loop driver around a user-supplied DONJON solve command."""

from __future__ import annotations

from pathlib import Path

from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import convert_mgxs_hdf5
from .sph_loop_config import CONFIG_SCHEMA
from .sph_loop_acceptance import build_acceptance_report
from .sph_loop_execution import SphLoopExecution, execute_loop
from .sph_loop_plan import SphLoopPlan, build_sph_loop_plan
from .sph_loop_preflight import (
    SphLoopFluxMapPreflightReport,
    build_flux_map_preflight_report,
    format_failure as format_preflight_failure,
)
from .sph_loop_report import (
    PASS_DECISION,
    SCHEMA,
    SphLoopReport,
    build_audit_rows,
    print_report,
    write_audit_csv,
    write_audit_text,
    write_bundle,
    write_summary,
)
from .sph_loop_runner import require_absent


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
    preflight = _run_preflight(plan)
    initial_ascii = _write_initial_ascii_for_plan(plan, force=force)
    execution = execute_loop(
        plan,
        initial_ascii=initial_ascii,
        preflight=preflight,
        force=force,
    )
    report = _build_report(plan, initial_ascii, preflight, execution)
    _write_report_outputs(
        report,
        bundle_dir=plan.bundle_dir,
        bundle_manifest_name=bundle_manifest_name,
        force=force,
    )
    _enforce_outcome(plan, report)
    return report


def _run_preflight(plan: SphLoopPlan) -> SphLoopFluxMapPreflightReport:
    plan.loop_dir.mkdir(parents=True, exist_ok=True)
    preflight = build_flux_map_preflight_report(
        input_h5=plan.input_h5,
        reference_flux=plan.reference_flux,
        map_h5=plan.map_h5,
        scalar_flux_ids=plan.scalar_flux_ids,
        scalar_flux_column=plan.scalar_flux_column,
    )
    if not preflight.passed:
        raise ValueError(format_preflight_failure(preflight))
    return preflight


def _write_initial_ascii_for_plan(plan: SphLoopPlan, *, force: bool) -> Path:
    return _write_initial_ascii(
        plan.input_h5,
        plan.loop_dir,
        output_format=plan.output_format,
        root_name=plan.root_name,
        h_factor_default=plan.h_factor_default,
        force=force,
    )


def _build_report(
    plan: SphLoopPlan,
    initial_ascii: Path,
    preflight: SphLoopFluxMapPreflightReport,
    execution: SphLoopExecution,
) -> SphLoopReport:
    converged = bool(execution.convergence and execution.convergence[-1].converged)
    audit_rows = build_audit_rows(
        solves=execution.solves,
        workflows=execution.workflows,
        convergence=execution.convergence,
        postprocesses=execution.postprocesses,
        final_solve=execution.final_solve,
        final_ascii=execution.final_ascii,
    )
    acceptance = build_acceptance_report(
        plan.normalized_acceptance,
        audit_rows=audit_rows,
        convergence=execution.convergence,
        completed_iterations=len(execution.workflows),
        converged=converged,
        final_solve=execution.final_solve,
    )
    return SphLoopReport(
        config_path=plan.config_path,
        input_h5=plan.input_h5,
        output_dir=plan.loop_dir,
        reference_flux=plan.reference_flux,
        iterations=plan.iterations,
        completed_iterations=len(execution.workflows),
        output_format=plan.output_format,
        initial_ascii=initial_ascii,
        final_ascii=execution.final_ascii,
        final_sph_sidecar=execution.final_sph_sidecar,
        summary_json=plan.summary_path,
        audit_csv=plan.audit_csv,
        audit_text=plan.audit_text,
        bundle_manifest=plan.bundle_manifest,
        convergence_enabled=plan.convergence_enabled,
        converged=converged,
        stop_reason=execution.stop_reason,
        sph_change_tolerance=plan.sph_change_tolerance,
        flux_ratio_tolerance=plan.flux_ratio_tolerance,
        min_iterations=plan.min_iterations,
        flux_map_preflight=preflight,
        solves=execution.solves,
        workflows=execution.workflows,
        convergence=execution.convergence,
        postprocesses=execution.postprocesses,
        final_solve=execution.final_solve,
        audit_rows=audit_rows,
        acceptance=acceptance,
    )


def _write_report_outputs(
    report: SphLoopReport,
    *,
    bundle_dir: Path | None,
    bundle_manifest_name: str,
    force: bool,
) -> None:
    write_audit_csv(report.audit_csv, report.audit_rows)
    write_audit_text(
        report.audit_text,
        report.audit_rows,
        flux_map_preflight=report.flux_map_preflight,
    )
    write_summary(report.summary_json, report)
    if bundle_dir is not None:
        write_bundle(
            report,
            output_dir=bundle_dir,
            manifest_name=bundle_manifest_name,
            force=force,
        )
    print_report(report)


def _enforce_outcome(plan: SphLoopPlan, report: SphLoopReport) -> None:
    if plan.convergence_enabled and plan.fail_on_nonconvergence and not report.converged:
        raise RuntimeError(
            "SPH loop did not converge within "
            f"{report.iterations} iteration(s); see {plan.summary_path}"
        )
    if not report.acceptance.enabled or not report.acceptance.fail_on_violation:
        return
    if report.acceptance.passed:
        return
    failed = ", ".join(
        check.name for check in report.acceptance.checks if not check.passed
    )
    failed_suffix = f": {failed}" if failed else ""
    raise RuntimeError(
        f"SPH loop acceptance criteria failed{failed_suffix}; see "
        f"{plan.summary_path} and {plan.audit_csv}"
    )


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
