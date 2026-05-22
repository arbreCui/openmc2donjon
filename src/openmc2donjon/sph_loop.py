"""Production SPH loop driver around a user-supplied DONJON solve command."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .sph_augment import load_sph_source
from .sph_loop_config import (
    CONFIG_SCHEMA,
    acceptance_config,
    convergence_config,
    load_config,
    optional_command_config,
    optional_float,
    parse_scalar_flux_ids,
    resolve_path,
    resolve_source,
    solver_config,
)
from .sph_loop_acceptance import build_acceptance_report
from .sph_loop_report import (
    PASS_DECISION,
    SCHEMA,
    SphLoopAuditRow,
    SphLoopConvergenceReport,
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

    config_file = Path(config_path)
    config = load_config(config_file)
    base_dir = config_file.parent

    input_h5 = resolve_path(config["input_h5"], base_dir)
    loop_dir = (
        resolve_path(output_dir, Path.cwd())
        if output_dir is not None
        else resolve_path(config["output_dir"], base_dir)
    )
    reference_flux = resolve_source(str(config["reference_flux"]), base_dir)
    iterations = int(config.get("iterations", 1))
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    normalized_convergence = convergence_config(config)
    normalized_acceptance = acceptance_config(config)
    sph_change_tolerance = optional_float(normalized_convergence.get("sph_change_tolerance"))
    flux_ratio_tolerance = optional_float(normalized_convergence.get("flux_ratio_tolerance"))
    convergence_enabled = (
        sph_change_tolerance is not None or flux_ratio_tolerance is not None
    )
    min_iterations = int(normalized_convergence.get("min_iterations", 1))
    if min_iterations < 1:
        raise ValueError("convergence.min_iterations must be >= 1")
    if min_iterations > iterations:
        raise ValueError("convergence.min_iterations must be <= iterations")
    fail_on_nonconvergence = bool(normalized_convergence.get("fail_on_nonconvergence", False))

    output_format = str(config.get("format", "macrolib"))
    if output_format not in {"macrolib", "multicompo"}:
        raise ValueError("format must be 'macrolib' or 'multicompo'")

    root_name = str(config.get("root_name", DEFAULT_ROOT_NAME))
    h_factor_default = optional_float(config.get("h_factor_default"))
    damping = float(config.get("damping", 1.0))
    clip_min = optional_float(config.get("clip_min"))
    clip_max = optional_float(config.get("clip_max"))
    sph_kind = str(config.get("sph_kind", "sph-loop"))
    sph_real = bool(config.get("sph_real", True))
    sph_applied = bool(config.get("sph_applied", False))
    source_label = str(config.get("source_label", "DONJON low-order SPH loop"))
    map_h5 = (
        None
        if config.get("map_h5") is None
        else resolve_path(config["map_h5"], base_dir)
    )
    scalar_flux_ids = parse_scalar_flux_ids(config.get("scalar_flux_map"))
    scalar_flux_column = int(config.get("kn_column", 1)) - 1
    list_offset = int(config.get("list_offset", 0))
    if map_h5 is not None and scalar_flux_ids is not None:
        raise ValueError("map_h5 and scalar_flux_map are mutually exclusive")

    loop_dir.mkdir(parents=True, exist_ok=True)
    summary_path = (
        loop_dir / "sph_loop_summary.json"
        if summary_json is None
        else resolve_path(summary_json, base_dir)
    )
    audit_csv = summary_path.with_name("sph_loop_audit.csv")
    audit_text = summary_path.with_name("sph_loop_audit.txt")
    resolved_bundle_dir = (
        None if bundle_dir is None else resolve_path(bundle_dir, base_dir)
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

    solver = solver_config(config)
    postprocessor = optional_command_config(config.get("postprocess"), "postprocess")
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
        solve_report = run_solver(
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
            postprocess = run_postprocessor(
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
        final_solve = run_solver(
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
    audit_rows = build_audit_rows(
        solves=tuple(solves),
        workflows=tuple(workflows),
        convergence=tuple(convergence_reports),
        postprocesses=tuple(postprocesses),
        final_solve=final_solve,
        final_ascii=current_ascii,
    )
    acceptance = build_acceptance_report(
        normalized_acceptance,
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
        write_bundle(
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
