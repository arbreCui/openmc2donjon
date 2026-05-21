"""Reporting, audit, and acceptance helpers for the SPH loop driver."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from . import __version__
from .bundle import ArtifactSpec, bundle_artifacts
from .sph_workflow import SphIterationWorkflowReport


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


def write_bundle(
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


def build_audit_rows(
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


def build_acceptance_report(
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
