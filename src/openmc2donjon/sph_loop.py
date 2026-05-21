"""Production SPH loop driver around a user-supplied DONJON solve command."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any

import numpy as np

from . import __version__
from .bundle import ArtifactSpec, bundle_artifacts
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .sph_augment import load_sph_source
from .sph_workflow import SphIterationWorkflowReport, run_sph_iteration_workflow


CONFIG_SCHEMA = "openmc2donjon.sph-loop-config.v1"
SCHEMA = "openmc2donjon.sph-loop.v1"
PASS_DECISION = "openmc2donjon_sph_loop_passed"
ACCEPTANCE_PASS_DECISION = "openmc2donjon_sph_loop_acceptance_passed"
ACCEPTANCE_FAIL_DECISION = "openmc2donjon_sph_loop_acceptance_failed"


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


@dataclass(frozen=True)
class SphLoopConvergenceReport:
    iteration: int
    sph_max_abs_change: float
    sph_max_rel_change: float
    flux_ratio_max_residual: float
    converged: bool


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
    converged: bool | None
    solve_result: Path | None
    ascii_output: Path | None
    postprocess_output: Path | None


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
    convergence_enabled: bool
    converged: bool
    stop_reason: str
    sph_change_tolerance: float | None
    flux_ratio_tolerance: float | None
    min_iterations: int
    solves: tuple[SphLoopSolveReport, ...]
    workflows: tuple[SphIterationWorkflowReport, ...]
    convergence: tuple[SphLoopConvergenceReport, ...]
    postprocesses: tuple[SphLoopPostprocessReport, ...]
    final_solve: SphLoopSolveReport | None
    audit_rows: tuple[SphLoopAuditRow, ...]
    acceptance: SphLoopAcceptanceReport


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

    config_file = Path(config_path)
    config = _load_config(config_file)
    base_dir = config_file.parent

    input_h5 = _resolve_path(config["input_h5"], base_dir)
    loop_dir = (
        _resolve_path(output_dir, Path.cwd())
        if output_dir is not None
        else _resolve_path(config["output_dir"], base_dir)
    )
    reference_flux = _resolve_source(str(config["reference_flux"]), base_dir)
    iterations = int(config.get("iterations", 1))
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    convergence_config = _convergence_config(config)
    acceptance_config = _acceptance_config(config)
    sph_change_tolerance = _optional_float(convergence_config.get("sph_change_tolerance"))
    flux_ratio_tolerance = _optional_float(convergence_config.get("flux_ratio_tolerance"))
    convergence_enabled = (
        sph_change_tolerance is not None or flux_ratio_tolerance is not None
    )
    min_iterations = int(convergence_config.get("min_iterations", 1))
    if min_iterations < 1:
        raise ValueError("convergence.min_iterations must be >= 1")
    if min_iterations > iterations:
        raise ValueError("convergence.min_iterations must be <= iterations")
    fail_on_nonconvergence = bool(convergence_config.get("fail_on_nonconvergence", False))

    output_format = str(config.get("format", "macrolib"))
    if output_format not in {"macrolib", "multicompo"}:
        raise ValueError("format must be 'macrolib' or 'multicompo'")

    root_name = str(config.get("root_name", DEFAULT_ROOT_NAME))
    h_factor_default = _optional_float(config.get("h_factor_default"))
    damping = float(config.get("damping", 1.0))
    clip_min = _optional_float(config.get("clip_min"))
    clip_max = _optional_float(config.get("clip_max"))
    sph_kind = str(config.get("sph_kind", "sph-loop"))
    sph_real = bool(config.get("sph_real", True))
    sph_applied = bool(config.get("sph_applied", False))
    source_label = str(config.get("source_label", "DONJON low-order SPH loop"))
    map_h5 = (
        None
        if config.get("map_h5") is None
        else _resolve_path(config["map_h5"], base_dir)
    )
    scalar_flux_ids = _parse_scalar_flux_ids(config.get("scalar_flux_map"))
    scalar_flux_column = int(config.get("kn_column", 1)) - 1
    list_offset = int(config.get("list_offset", 0))
    if map_h5 is not None and scalar_flux_ids is not None:
        raise ValueError("map_h5 and scalar_flux_map are mutually exclusive")

    loop_dir.mkdir(parents=True, exist_ok=True)
    summary_path = (
        loop_dir / "sph_loop_summary.json"
        if summary_json is None
        else _resolve_path(summary_json, base_dir)
    )
    audit_csv = summary_path.with_name("sph_loop_audit.csv")
    audit_text = summary_path.with_name("sph_loop_audit.txt")
    resolved_bundle_dir = (
        None if bundle_dir is None else _resolve_path(bundle_dir, base_dir)
    )
    bundle_manifest = (
        None
        if resolved_bundle_dir is None
        else resolved_bundle_dir / bundle_manifest_name
    )

    initial_ascii = _write_initial_ascii(
        input_h5,
        loop_dir,
        output_format=output_format,
        root_name=root_name,
        h_factor_default=h_factor_default,
        force=force,
    )

    solver = _solver_config(config)
    postprocessor = _optional_command_config(config.get("postprocess"), "postprocess")
    run_final_solve = bool(config.get("final_solve", False))
    solves: list[SphLoopSolveReport] = []
    workflows: list[SphIterationWorkflowReport] = []
    convergence_reports: list[SphLoopConvergenceReport] = []
    postprocesses: list[SphLoopPostprocessReport] = []
    current_ascii = initial_ascii
    previous_sph: Path | None = None
    stop_reason = "max_iterations"

    for iteration in range(iterations):
        sph_before_iteration = previous_sph
        solve_report = _run_solver(
            solver,
            base_dir=base_dir,
            loop_dir=loop_dir,
            iteration=iteration,
            input_h5=input_h5,
            ascii_input=current_ascii,
            previous_sph=previous_sph,
            force=force,
        )
        solves.append(solve_report)

        workflow_dir = loop_dir / f"iter{iteration + 1:02d}_sph"
        workflow = run_sph_iteration_workflow(
            input_h5,
            workflow_dir,
            reference_flux=reference_flux,
            flux_dump=solve_report.result,
            map_h5=map_h5,
            scalar_flux_ids=scalar_flux_ids,
            scalar_flux_column=scalar_flux_column,
            list_offset=list_offset,
            previous_sph=previous_sph,
            damping=damping,
            clip_min=clip_min,
            clip_max=clip_max,
            output_format=output_format,
            root_name=root_name,
            h_factor_default=h_factor_default,
            sph_kind=f"{sph_kind}-iter{iteration + 1}",
            sph_real=sph_real,
            sph_applied=sph_applied,
            source_label=f"{source_label}: iteration {iteration + 1}",
            force=force,
        )
        workflows.append(workflow)
        current_ascii = workflow.ascii_output
        convergence_report = _build_convergence_report(
            workflow,
            input_h5=input_h5,
            previous_sph=sph_before_iteration,
            iteration=iteration + 1,
            sph_change_tolerance=sph_change_tolerance,
            flux_ratio_tolerance=flux_ratio_tolerance,
            min_iterations=min_iterations,
        )
        convergence_reports.append(convergence_report)
        previous_sph = workflow.sph_sidecar
        if postprocessor is not None:
            postprocess = _run_postprocessor(
                postprocessor,
                base_dir=base_dir,
                loop_dir=loop_dir,
                iteration=iteration,
                input_h5=input_h5,
                solve_result=solve_report.result,
                workflow=workflow,
                previous_sph=previous_sph,
                output_format=output_format,
                force=force,
            )
            postprocesses.append(postprocess)
            current_ascii = postprocess.output
        if convergence_enabled and convergence_report.converged:
            stop_reason = "converged"
            break

    final_solve = None
    if run_final_solve:
        final_iteration = len(workflows)
        final_solve = _run_solver(
            solver,
            base_dir=base_dir,
            loop_dir=loop_dir,
            iteration=final_iteration,
            input_h5=input_h5,
            ascii_input=current_ascii,
            previous_sph=previous_sph,
            force=force,
        )
        solves.append(final_solve)

    converged = bool(convergence_reports and convergence_reports[-1].converged)
    audit_rows = _build_audit_rows(
        solves=tuple(solves),
        workflows=tuple(workflows),
        convergence=tuple(convergence_reports),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
        final_ascii=current_ascii,
    )
    acceptance = _build_acceptance_report(
        acceptance_config,
        audit_rows=audit_rows,
        convergence=tuple(convergence_reports),
        completed_iterations=len(workflows),
        converged=converged,
        final_solve=final_solve,
    )
    report = SphLoopReport(
        config_path=config_file,
        input_h5=input_h5,
        output_dir=loop_dir,
        reference_flux=reference_flux,
        iterations=iterations,
        completed_iterations=len(workflows),
        output_format=output_format,
        initial_ascii=initial_ascii,
        final_ascii=current_ascii,
        final_sph_sidecar=previous_sph,
        summary_json=summary_path,
        audit_csv=audit_csv,
        audit_text=audit_text,
        bundle_manifest=bundle_manifest,
        convergence_enabled=convergence_enabled,
        converged=converged,
        stop_reason=stop_reason,
        sph_change_tolerance=sph_change_tolerance,
        flux_ratio_tolerance=flux_ratio_tolerance,
        min_iterations=min_iterations,
        solves=tuple(solves),
        workflows=tuple(workflows),
        convergence=tuple(convergence_reports),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
        audit_rows=audit_rows,
        acceptance=acceptance,
    )
    write_audit_csv(audit_csv, report.audit_rows)
    write_audit_text(audit_text, report.audit_rows)
    write_summary(summary_path, report)
    if resolved_bundle_dir is not None:
        _write_bundle(
            report,
            output_dir=resolved_bundle_dir,
            manifest_name=bundle_manifest_name,
            force=force,
        )
    print_report(report)
    if (
        convergence_enabled
        and fail_on_nonconvergence
        and not report.converged
    ):
        raise RuntimeError(
            "SPH loop did not converge within "
            f"{report.iterations} iteration(s); see {summary_path}"
        )
    if report.acceptance.enabled and report.acceptance.fail_on_violation:
        if not report.acceptance.passed:
            raise RuntimeError(
                "SPH loop acceptance criteria failed; see "
                f"{summary_path} and {audit_csv}"
            )
    return report


def print_report(report: SphLoopReport) -> None:
    print("OpenMC-to-DONJON SPH loop")
    print(f"  schema: {SCHEMA}")
    print(f"  config: {report.config_path}")
    print(f"  input: {report.input_h5}")
    print(f"  output_dir: {report.output_dir}")
    print(f"  iterations: {report.completed_iterations}/{report.iterations}")
    print(f"  reference_flux: {report.reference_flux}")
    print(f"  initial_ascii: {report.initial_ascii}")
    print(f"  final_ascii: {report.final_ascii}")
    print(f"  audit_csv: {report.audit_csv}")
    print(f"  audit_text: {report.audit_text}")
    if report.bundle_manifest is not None:
        print(f"  bundle_manifest: {report.bundle_manifest}")
    if report.final_sph_sidecar is not None:
        print(f"  final_sph_sidecar: {report.final_sph_sidecar}")
    for solve in report.solves:
        print(
            f"  solve[{solve.iteration}]: rc={solve.returncode} "
            f"result={solve.result}"
        )
    for postprocess in report.postprocesses:
        print(
            f"  postprocess[{postprocess.iteration}]: rc={postprocess.returncode} "
            f"output={postprocess.output}"
        )
    if report.convergence_enabled:
        print("  convergence:")
        for item in report.convergence:
            print(
                f"    iter{item.iteration}: "
                f"sph_rel={item.sph_max_rel_change:.6e} "
                f"flux_res={item.flux_ratio_max_residual:.6e} "
                f"converged={item.converged}"
            )
        print(f"  stop_reason: {report.stop_reason}")
    if report.acceptance.enabled:
        print("  acceptance:")
        print(f"    decision={report.acceptance.decision}")
        for item in report.acceptance.checks:
            status = "PASS" if item.passed else "FAIL"
            print(f"    {status} {item.name}: {item.message}")
    print()
    print("SPH loop decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SphLoopReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "config_path": str(report.config_path),
        "input_h5": str(report.input_h5),
        "output_dir": str(report.output_dir),
        "reference_flux": report.reference_flux,
        "iterations": report.iterations,
        "completed_iterations": report.completed_iterations,
        "output_format": report.output_format,
        "initial_ascii": str(report.initial_ascii),
        "final_ascii": str(report.final_ascii),
        "audit_csv": str(report.audit_csv),
        "audit_text": str(report.audit_text),
        "bundle_manifest": (
            None if report.bundle_manifest is None else str(report.bundle_manifest)
        ),
        "acceptance_enabled": report.acceptance.enabled,
        "acceptance_passed": report.acceptance.passed,
        "acceptance_decision": report.acceptance.decision,
        "final_sph_sidecar": (
            None if report.final_sph_sidecar is None else str(report.final_sph_sidecar)
        ),
        "convergence_enabled": report.convergence_enabled,
        "converged": report.converged,
        "stop_reason": report.stop_reason,
        "sph_change_tolerance": report.sph_change_tolerance,
        "flux_ratio_tolerance": report.flux_ratio_tolerance,
        "min_iterations": report.min_iterations,
        "solves": [
            {
                "iteration": solve.iteration,
                "command": list(solve.command),
                "cwd": str(solve.cwd),
                "ascii_input": str(solve.ascii_input),
                "result": str(solve.result),
                "stdout": str(solve.stdout),
                "stderr": str(solve.stderr),
                "returncode": solve.returncode,
            }
            for solve in report.solves
        ],
        "convergence": [
            {
                "iteration": item.iteration,
                "sph_max_abs_change": item.sph_max_abs_change,
                "sph_max_rel_change": item.sph_max_rel_change,
                "flux_ratio_max_residual": item.flux_ratio_max_residual,
                "converged": item.converged,
            }
            for item in report.convergence
        ],
        "final_solve": (
            None
            if report.final_solve is None
            else {
                "iteration": report.final_solve.iteration,
                "result": str(report.final_solve.result),
                "returncode": report.final_solve.returncode,
            }
        ),
        "workflows": [
            {
                "iteration": index + 1,
                "summary_json": str(workflow.summary_json),
                "donjon_volume_flux_h5": str(workflow.donjon_volume_flux_h5),
                "sph_sidecar": str(workflow.sph_sidecar),
                "augmented_h5": str(workflow.augmented_h5),
                "ascii_output": str(workflow.ascii_output),
                "sph_minimum": workflow.sph_minimum,
                "sph_maximum": workflow.sph_maximum,
            }
            for index, workflow in enumerate(report.workflows)
        ],
        "postprocesses": [
            {
                "iteration": postprocess.iteration,
                "command": list(postprocess.command),
                "cwd": str(postprocess.cwd),
                "workflow_ascii": str(postprocess.workflow_ascii),
                "output": str(postprocess.output),
                "sph_sidecar": str(postprocess.sph_sidecar),
                "stdout": str(postprocess.stdout),
                "stderr": str(postprocess.stderr),
                "returncode": postprocess.returncode,
            }
            for postprocess in report.postprocesses
        ],
        "audit_rows": [
            {
                "stage": row.stage,
                "iteration": row.iteration,
                "keff": row.keff,
                "sph_minimum": row.sph_minimum,
                "sph_maximum": row.sph_maximum,
                "sph_max_abs_change": row.sph_max_abs_change,
                "sph_max_rel_change": row.sph_max_rel_change,
                "flux_ratio_max_residual": row.flux_ratio_max_residual,
                "converged": row.converged,
                "solve_result": None if row.solve_result is None else str(row.solve_result),
                "ascii_output": None if row.ascii_output is None else str(row.ascii_output),
                "postprocess_output": (
                    None
                    if row.postprocess_output is None
                    else str(row.postprocess_output)
                ),
            }
            for row in report.audit_rows
        ],
        "acceptance": {
            "enabled": report.acceptance.enabled,
            "passed": report.acceptance.passed,
            "fail_on_violation": report.acceptance.fail_on_violation,
            "decision": report.acceptance.decision,
            "checks": [
                {
                    "name": item.name,
                    "actual": item.actual,
                    "limit": item.limit,
                    "units": item.units,
                    "passed": item.passed,
                    "message": item.message,
                }
                for item in report.acceptance.checks
            ],
        },
        "openmc_xs_policy": "fixed base MGXS; DONJON solves consume updated ASCII SPH handoffs",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_bundle(
    report: SphLoopReport,
    *,
    output_dir: Path,
    manifest_name: str,
    force: bool,
) -> None:
    artifacts = [
        ArtifactSpec(label="sph-loop-config", source=report.config_path),
        ArtifactSpec(label="sph-input-h5", source=report.input_h5),
        ArtifactSpec(label="sph-loop-final-ascii", source=report.final_ascii),
        ArtifactSpec(label="sph-loop-summary", source=report.summary_json),
        ArtifactSpec(label="sph-loop-audit-csv", source=report.audit_csv),
        ArtifactSpec(label="sph-loop-audit-text", source=report.audit_text),
    ]
    if report.final_sph_sidecar is not None:
        artifacts.insert(
            3,
            ArtifactSpec(
                label="sph-loop-final-sph-sidecar",
                source=report.final_sph_sidecar,
            ),
        )
    bundle_artifacts(
        output_dir=output_dir,
        artifacts=artifacts,
        manifest_name=manifest_name,
        force=force,
    )


def write_audit_csv(path: Path, rows: tuple[SphLoopAuditRow, ...]) -> None:
    fieldnames = [
        "stage",
        "iteration",
        "keff",
        "sph_minimum",
        "sph_maximum",
        "sph_max_abs_change",
        "sph_max_rel_change",
        "flux_ratio_max_residual",
        "converged",
        "solve_result",
        "ascii_output",
        "postprocess_output",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "stage": row.stage,
                    "iteration": row.iteration,
                    "keff": _format_optional_float(row.keff),
                    "sph_minimum": _format_optional_float(row.sph_minimum),
                    "sph_maximum": _format_optional_float(row.sph_maximum),
                    "sph_max_abs_change": _format_optional_float(
                        row.sph_max_abs_change
                    ),
                    "sph_max_rel_change": _format_optional_float(
                        row.sph_max_rel_change
                    ),
                    "flux_ratio_max_residual": _format_optional_float(
                        row.flux_ratio_max_residual
                    ),
                    "converged": "" if row.converged is None else str(row.converged),
                    "solve_result": "" if row.solve_result is None else str(row.solve_result),
                    "ascii_output": "" if row.ascii_output is None else str(row.ascii_output),
                    "postprocess_output": (
                        "" if row.postprocess_output is None else str(row.postprocess_output)
                    ),
                }
            )


def write_audit_text(path: Path, rows: tuple[SphLoopAuditRow, ...]) -> None:
    lines = [
        "OpenMC-to-DONJON SPH loop audit",
        (
            "stage      iter  keff          sph_min       sph_max       "
            "sph_rel       flux_res      converged"
        ),
    ]
    for row in rows:
        converged = "" if row.converged is None else str(row.converged)
        lines.append(
            f"{row.stage:<10} {row.iteration:>4d}  "
            f"{_format_optional_float(row.keff):<12} "
            f"{_format_optional_float(row.sph_minimum):<12} "
            f"{_format_optional_float(row.sph_maximum):<12} "
            f"{_format_optional_float(row.sph_max_rel_change):<12} "
            f"{_format_optional_float(row.flux_ratio_max_residual):<12} "
            f"{converged:<9}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_audit_rows(
    *,
    solves: tuple[SphLoopSolveReport, ...],
    workflows: tuple[SphIterationWorkflowReport, ...],
    convergence: tuple[SphLoopConvergenceReport, ...],
    postprocesses: tuple[SphLoopPostprocessReport, ...],
    final_solve: SphLoopSolveReport | None,
    final_ascii: Path,
) -> tuple[SphLoopAuditRow, ...]:
    solve_by_iteration = {solve.iteration: solve for solve in solves}
    postprocess_by_iteration = {item.iteration: item for item in postprocesses}
    rows: list[SphLoopAuditRow] = []
    for index, workflow in enumerate(workflows, start=1):
        solve = solve_by_iteration.get(index - 1)
        convergence_report = convergence[index - 1] if index - 1 < len(convergence) else None
        postprocess = postprocess_by_iteration.get(index)
        rows.append(
            SphLoopAuditRow(
                stage="iteration",
                iteration=index,
                keff=None if solve is None else _extract_solve_keff(solve),
                sph_minimum=workflow.sph_minimum,
                sph_maximum=workflow.sph_maximum,
                sph_max_abs_change=(
                    None if convergence_report is None else convergence_report.sph_max_abs_change
                ),
                sph_max_rel_change=(
                    None if convergence_report is None else convergence_report.sph_max_rel_change
                ),
                flux_ratio_max_residual=(
                    None
                    if convergence_report is None
                    else convergence_report.flux_ratio_max_residual
                ),
                converged=None if convergence_report is None else convergence_report.converged,
                solve_result=None if solve is None else solve.result,
                ascii_output=workflow.ascii_output,
                postprocess_output=None if postprocess is None else postprocess.output,
            )
        )
    if final_solve is not None:
        rows.append(
            SphLoopAuditRow(
                stage="final",
                iteration=final_solve.iteration,
                keff=_extract_solve_keff(final_solve),
                sph_minimum=None,
                sph_maximum=None,
                sph_max_abs_change=None,
                sph_max_rel_change=None,
                flux_ratio_max_residual=None,
                converged=None,
                solve_result=final_solve.result,
                ascii_output=final_ascii,
                postprocess_output=None,
            )
        )
    return tuple(rows)


def _extract_solve_keff(solve: SphLoopSolveReport) -> float | None:
    for path in (solve.stdout, solve.result, solve.stderr):
        value = _extract_keff(path)
        if value is not None:
            return value
    return None


def _extract_keff(path: Path) -> float | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = (
        r"EFFECTIVE MULTIPLICATION FACTOR\s*=\s*([0-9.+\-Ee]+)",
        r"K-EFFECTIVE\s+([0-9.+\-Ee]+)",
    )
    matches: list[str] = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            break
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12g}"


def _build_acceptance_report(
    config: dict[str, Any],
    *,
    audit_rows: tuple[SphLoopAuditRow, ...],
    convergence: tuple[SphLoopConvergenceReport, ...],
    completed_iterations: int,
    converged: bool,
    final_solve: SphLoopSolveReport | None,
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
    rows: tuple[SphLoopAuditRow, ...],
) -> SphLoopAuditRow | None:
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


def _final_keff_delta_pcm(rows: tuple[SphLoopAuditRow, ...]) -> float | None:
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


def _build_convergence_report(
    workflow: SphIterationWorkflowReport,
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
    flux_residual = _flux_ratio_max_residual(workflow)
    checks: list[bool] = []
    if sph_change_tolerance is not None:
        checks.append(float(np.max(rel_change)) <= sph_change_tolerance)
    if flux_ratio_tolerance is not None:
        checks.append(flux_residual <= flux_ratio_tolerance)
    converged = bool(checks and all(checks) and iteration >= min_iterations)
    return SphLoopConvergenceReport(
        iteration=iteration,
        sph_max_abs_change=float(np.max(abs_change)),
        sph_max_rel_change=float(np.max(rel_change)),
        flux_ratio_max_residual=flux_residual,
        converged=converged,
    )


def _flux_ratio_max_residual(workflow: SphIterationWorkflowReport) -> float:
    summary_path = workflow.output_dir / "next_sph_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    raw_min = float(payload["raw_update_minimum"])
    raw_max = float(payload["raw_update_maximum"])
    return max(abs(raw_min - 1.0), abs(raw_max - 1.0))


def _load_sph_matrix(path: Path, *, input_h5: Path) -> np.ndarray:
    mixture_names, energy_groups = _read_input_metadata(input_h5)
    loaded = load_sph_source(path, mixture_names=mixture_names, energy_groups=energy_groups)
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


def _load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("SPH loop config must be a JSON object")
    for key in ("input_h5", "output_dir", "reference_flux", "solver"):
        if key not in config:
            raise ValueError(f"SPH loop config is missing required key {key!r}")
    schema = config.get("schema")
    if schema is not None and schema != CONFIG_SCHEMA:
        raise ValueError(f"unsupported SPH loop config schema {schema!r}")
    return config


def _convergence_config(config: dict[str, Any]) -> dict[str, Any]:
    nested = config.get("convergence", {})
    if nested is None:
        nested = {}
    if not isinstance(nested, dict):
        raise ValueError("convergence must be a JSON object")
    out = dict(nested)
    for key in (
        "sph_change_tolerance",
        "flux_ratio_tolerance",
        "min_iterations",
        "fail_on_nonconvergence",
    ):
        if key in config and key not in out:
            out[key] = config[key]
    for key in ("sph_change_tolerance", "flux_ratio_tolerance"):
        value = _optional_float(out.get(key))
        if value is not None and value < 0.0:
            raise ValueError(f"convergence.{key} must be >= 0")
        out[key] = value
    return out


def _acceptance_config(config: dict[str, Any]) -> dict[str, Any]:
    nested = config.get("acceptance", {})
    if nested is None:
        nested = {}
    if not isinstance(nested, dict):
        raise ValueError("acceptance must be a JSON object")
    allowed = {
        "fail_on_violation",
        "min_completed_iterations",
        "require_final_solve",
        "require_converged",
        "max_sph_abs_change",
        "max_sph_rel_change",
        "max_flux_ratio_residual",
        "sph_minimum_floor",
        "sph_maximum_ceiling",
        "max_keff_step_pcm",
        "max_final_keff_delta_pcm",
    }
    unknown = sorted(set(nested) - allowed)
    if unknown:
        raise ValueError(f"unknown acceptance key(s): {', '.join(unknown)}")

    out = dict(nested)
    for key in (
        "max_sph_abs_change",
        "max_sph_rel_change",
        "max_flux_ratio_residual",
        "sph_minimum_floor",
        "sph_maximum_ceiling",
        "max_keff_step_pcm",
        "max_final_keff_delta_pcm",
    ):
        if key in out and out[key] is not None:
            value = float(out[key])
            if value < 0.0:
                raise ValueError(f"acceptance.{key} must be >= 0")
            out[key] = value
    if "min_completed_iterations" in out and out["min_completed_iterations"] is not None:
        value = int(out["min_completed_iterations"])
        if value < 1:
            raise ValueError("acceptance.min_completed_iterations must be >= 1")
        out["min_completed_iterations"] = value
    for key in ("require_final_solve", "require_converged", "fail_on_violation"):
        if key in out and out[key] is not None:
            out[key] = bool(out[key])
    return {key: value for key, value in out.items() if value is not None}


def _solver_config(config: dict[str, Any]) -> dict[str, Any]:
    return _command_config(config.get("solver"), "solver")


def _optional_command_config(value: object, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return _command_config(value, name)


def _command_config(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    if "command" not in value:
        raise ValueError(f"{name}.command is required")
    command = value["command"]
    if not isinstance(command, (list, str)):
        raise ValueError(f"{name}.command must be a list of strings or a command string")
    if isinstance(command, list) and not all(isinstance(part, str) for part in command):
        raise ValueError(f"{name}.command list entries must be strings")
    return value


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
    _require_absent(output, force=force)
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


def _run_solver(
    solver: dict[str, Any],
    *,
    base_dir: Path,
    loop_dir: Path,
    iteration: int,
    input_h5: Path,
    ascii_input: Path,
    previous_sph: Path | None,
    force: bool,
) -> SphLoopSolveReport:
    solve_dir = loop_dir / f"iter{iteration:02d}_solve"
    solve_dir.mkdir(parents=True, exist_ok=True)
    workflow_dir = loop_dir / f"iter{iteration + 1:02d}_sph"
    result = _solver_result_path(
        solver,
        solve_dir=solve_dir,
        workflow_dir=workflow_dir,
        loop_dir=loop_dir,
        iteration=iteration,
        input_h5=input_h5,
        ascii_input=ascii_input,
        previous_sph=previous_sph,
    )
    stdout = solve_dir / "solver.stdout.txt"
    stderr = solve_dir / "solver.stderr.txt"
    for path in (result, stdout, stderr):
        _require_absent(path, force=force)

    context = _template_context(
        iteration=iteration,
        loop_dir=loop_dir,
        solve_dir=solve_dir,
        input_h5=input_h5,
        ascii_input=ascii_input,
        result=result,
        previous_sph=previous_sph,
    )
    command = _format_command(solver["command"], context)
    cwd = _solver_cwd(solver, base_dir, context, solve_dir)
    env = _solver_env(solver, context)

    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=out,
            stderr=err,
            text=True,
            check=False,
        )

    if completed.returncode != 0:
        raise RuntimeError(
            f"solver command failed for iteration {iteration} with exit code "
            f"{completed.returncode}; see {stderr}"
        )
    if not result.exists():
        raise FileNotFoundError(
            f"solver command for iteration {iteration} did not create result {result}"
        )

    return SphLoopSolveReport(
        iteration=iteration,
        command=tuple(command),
        cwd=cwd,
        ascii_input=ascii_input,
        result=result,
        stdout=stdout,
        stderr=stderr,
        returncode=completed.returncode,
    )


def _run_postprocessor(
    postprocessor: dict[str, Any],
    *,
    base_dir: Path,
    loop_dir: Path,
    iteration: int,
    input_h5: Path,
    solve_result: Path,
    workflow: SphIterationWorkflowReport,
    previous_sph: Path | None,
    output_format: str,
    force: bool,
) -> SphLoopPostprocessReport:
    output = _postprocess_output_path(
        postprocessor,
        workflow_dir=workflow.output_dir,
        loop_dir=loop_dir,
        iteration=iteration,
        input_h5=input_h5,
        solve_result=solve_result,
        workflow=workflow,
        previous_sph=previous_sph,
        output_format=output_format,
    )
    stdout = workflow.output_dir / "postprocess.stdout.txt"
    stderr = workflow.output_dir / "postprocess.stderr.txt"
    for path in (output, stdout, stderr):
        _require_absent(path, force=force)

    context = _postprocess_context(
        iteration=iteration,
        loop_dir=loop_dir,
        input_h5=input_h5,
        solve_result=solve_result,
        workflow=workflow,
        previous_sph=previous_sph,
        output=output,
    )
    command = _format_command(postprocessor["command"], context)
    cwd = _solver_cwd(postprocessor, base_dir, context, workflow.output_dir)
    env = _solver_env(postprocessor, context)

    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=out,
            stderr=err,
            text=True,
            check=False,
        )

    if completed.returncode != 0:
        raise RuntimeError(
            f"postprocess command failed for iteration {iteration + 1} with "
            f"exit code {completed.returncode}; see {stderr}"
        )
    if not output.exists():
        raise FileNotFoundError(
            f"postprocess command for iteration {iteration + 1} did not create {output}"
        )

    return SphLoopPostprocessReport(
        iteration=iteration + 1,
        command=tuple(command),
        cwd=cwd,
        workflow_ascii=workflow.ascii_output,
        output=output,
        sph_sidecar=workflow.sph_sidecar,
        stdout=stdout,
        stderr=stderr,
        returncode=completed.returncode,
    )


def _postprocess_output_path(
    postprocessor: dict[str, Any],
    *,
    workflow_dir: Path,
    loop_dir: Path,
    iteration: int,
    input_h5: Path,
    solve_result: Path,
    workflow: SphIterationWorkflowReport,
    previous_sph: Path | None,
    output_format: str,
) -> Path:
    suffix = "macrolib.txt" if output_format == "macrolib" else "mcompo.txt"
    template = str(postprocessor.get("output", f"out.postprocessed.{suffix}"))
    context = _postprocess_context(
        iteration=iteration,
        loop_dir=loop_dir,
        input_h5=input_h5,
        solve_result=solve_result,
        workflow=workflow,
        previous_sph=previous_sph,
        output=workflow_dir / f"out.postprocessed.{suffix}",
    )
    rendered = _format_template(template, context)
    path = Path(rendered)
    if not path.is_absolute():
        path = workflow_dir / path
    return path


def _postprocess_context(
    *,
    iteration: int,
    loop_dir: Path,
    input_h5: Path,
    solve_result: Path,
    workflow: SphIterationWorkflowReport,
    previous_sph: Path | None,
    output: Path,
) -> dict[str, str]:
    return {
        "iteration": str(iteration),
        "iteration1": str(iteration + 1),
        "loop_dir": str(loop_dir),
        "workflow_dir": str(workflow.output_dir),
        "input_h5": str(input_h5),
        "solve_result": str(solve_result),
        "workflow_ascii": str(workflow.ascii_output),
        "ascii_input": str(workflow.ascii_output),
        "output": str(output),
        "sph_sidecar": str(workflow.sph_sidecar),
        "augmented_h5": str(workflow.augmented_h5),
        "previous_sph": "" if previous_sph is None else str(previous_sph),
    }


def _solver_result_path(
    solver: dict[str, Any],
    *,
    solve_dir: Path,
    workflow_dir: Path,
    loop_dir: Path,
    iteration: int,
    input_h5: Path,
    ascii_input: Path,
    previous_sph: Path | None,
) -> Path:
    context = {
        "iteration": str(iteration),
        "iteration1": str(iteration + 1),
        "loop_dir": str(loop_dir),
        "solve_dir": str(solve_dir),
        "workflow_dir": str(workflow_dir),
        "input_h5": str(input_h5),
        "ascii_input": str(ascii_input),
        "previous_sph": "" if previous_sph is None else str(previous_sph),
    }
    template = str(solver.get("result", "donjon_flux.result"))
    rendered = _format_template(template, context)
    path = Path(rendered)
    if not path.is_absolute():
        path = solve_dir / path
    return path


def _solver_cwd(
    solver: dict[str, Any],
    base_dir: Path,
    context: dict[str, str],
    default: Path,
) -> Path:
    if "cwd" not in solver:
        return default
    rendered = _format_template(str(solver["cwd"]), context)
    path = Path(rendered)
    if not path.is_absolute():
        path = base_dir / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _solver_env(solver: dict[str, Any], context: dict[str, str]) -> dict[str, str] | None:
    if "env" not in solver:
        return None
    raw_env = solver["env"]
    if not isinstance(raw_env, dict):
        raise ValueError("solver.env must be a JSON object")
    env = dict(os.environ)
    for key, value in raw_env.items():
        env[str(key)] = _format_template(str(value), context)
    return env


def _template_context(
    *,
    iteration: int,
    loop_dir: Path,
    solve_dir: Path,
    input_h5: Path,
    ascii_input: Path,
    result: Path,
    previous_sph: Path | None,
) -> dict[str, str]:
    return {
        "iteration": str(iteration),
        "iteration1": str(iteration + 1),
        "loop_dir": str(loop_dir),
        "solve_dir": str(solve_dir),
        "workflow_dir": str(loop_dir / f"iter{iteration + 1:02d}_sph"),
        "input_h5": str(input_h5),
        "ascii_input": str(ascii_input),
        "result": str(result),
        "previous_sph": "" if previous_sph is None else str(previous_sph),
    }


def _format_command(command: list[str] | str, context: dict[str, str]) -> list[str]:
    if isinstance(command, str):
        return shlex.split(_format_template(command, context))
    return [_format_template(part, context) for part in command]


def _format_template(template: str, context: dict[str, str]) -> str:
    try:
        return template.format(**context)
    except KeyError as exc:
        raise ValueError(f"unknown solver template field {exc.args[0]!r}") from exc


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _resolve_source(value: str, base_dir: Path) -> str:
    if "::" not in value:
        return str(_resolve_path(value, base_dir))
    path, dataset = value.split("::", maxsplit=1)
    return f"{_resolve_path(path, base_dir)}::{dataset}"


def _parse_scalar_flux_ids(value: object) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("scalar_flux_map must be a JSON object")
    return {str(name): int(index) for name, index in value.items()}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _require_absent(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {path}")
