"""Production SPH loop driver around a user-supplied DONJON solve command."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any

from . import __version__
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .sph_workflow import SphIterationWorkflowReport, run_sph_iteration_workflow


CONFIG_SCHEMA = "openmc2donjon.sph-loop-config.v1"
SCHEMA = "openmc2donjon.sph-loop.v1"
PASS_DECISION = "openmc2donjon_sph_loop_passed"


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
class SphLoopReport:
    config_path: Path
    input_h5: Path
    output_dir: Path
    reference_flux: str
    iterations: int
    output_format: str
    initial_ascii: Path
    final_ascii: Path
    final_sph_sidecar: Path | None
    summary_json: Path
    solves: tuple[SphLoopSolveReport, ...]
    workflows: tuple[SphIterationWorkflowReport, ...]
    postprocesses: tuple[SphLoopPostprocessReport, ...]
    final_solve: SphLoopSolveReport | None


def run_sph_loop(
    config_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    force: bool = False,
    summary_json: str | Path | None = None,
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
    postprocesses: list[SphLoopPostprocessReport] = []
    current_ascii = initial_ascii
    previous_sph: Path | None = None

    for iteration in range(iterations):
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

    final_solve = None
    if run_final_solve:
        final_solve = _run_solver(
            solver,
            base_dir=base_dir,
            loop_dir=loop_dir,
            iteration=iterations,
            input_h5=input_h5,
            ascii_input=current_ascii,
            previous_sph=previous_sph,
            force=force,
        )
        solves.append(final_solve)

    report = SphLoopReport(
        config_path=config_file,
        input_h5=input_h5,
        output_dir=loop_dir,
        reference_flux=reference_flux,
        iterations=iterations,
        output_format=output_format,
        initial_ascii=initial_ascii,
        final_ascii=current_ascii,
        final_sph_sidecar=previous_sph,
        summary_json=summary_path,
        solves=tuple(solves),
        workflows=tuple(workflows),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
    )
    print_report(report)
    write_summary(summary_path, report)
    return report


def print_report(report: SphLoopReport) -> None:
    print("OpenMC-to-DONJON SPH loop")
    print(f"  schema: {SCHEMA}")
    print(f"  config: {report.config_path}")
    print(f"  input: {report.input_h5}")
    print(f"  output_dir: {report.output_dir}")
    print(f"  iterations: {report.iterations}")
    print(f"  reference_flux: {report.reference_flux}")
    print(f"  initial_ascii: {report.initial_ascii}")
    print(f"  final_ascii: {report.final_ascii}")
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
        "output_format": report.output_format,
        "initial_ascii": str(report.initial_ascii),
        "final_ascii": str(report.final_ascii),
        "final_sph_sidecar": (
            None if report.final_sph_sidecar is None else str(report.final_sph_sidecar)
        ),
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
        "openmc_xs_policy": "fixed base MGXS; DONJON solves consume updated ASCII SPH handoffs",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
