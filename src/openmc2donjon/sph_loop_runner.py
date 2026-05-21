"""Command rendering and subprocess execution for SPH loop solves."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
from typing import Any

from .sph_loop_report import SphLoopPostprocessReport, SphLoopSolveReport
from .sph_workflow import SphIterationWorkflowReport


def run_solver(
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
        require_absent(path, force=force)

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


def run_postprocessor(
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
        require_absent(path, force=force)

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


def require_absent(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {path}")


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
