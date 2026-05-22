"""Resolved execution plan for the fixed-OpenMC SPH loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .multicompo import DEFAULT_ROOT_NAME
from .sph_loop_config import (
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


@dataclass(frozen=True)
class SphLoopPlan:
    config_path: Path
    base_dir: Path
    input_h5: Path
    loop_dir: Path
    reference_flux: str
    iterations: int
    normalized_acceptance: dict[str, Any]
    sph_change_tolerance: float | None
    flux_ratio_tolerance: float | None
    convergence_enabled: bool
    min_iterations: int
    fail_on_nonconvergence: bool
    output_format: str
    root_name: str
    h_factor_default: float | None
    damping: float
    clip_min: float | None
    clip_max: float | None
    sph_kind: str
    sph_real: bool
    sph_applied: bool
    source_label: str
    map_h5: Path | None
    scalar_flux_ids: dict[str, int] | None
    scalar_flux_column: int
    list_offset: int
    summary_path: Path
    audit_csv: Path
    audit_text: Path
    bundle_dir: Path | None
    bundle_manifest: Path | None
    solver: dict[str, Any]
    postprocessor: dict[str, Any] | None
    run_final_solve: bool


def build_sph_loop_plan(
    config_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    summary_json: str | Path | None = None,
    bundle_dir: str | Path | None = None,
    bundle_manifest_name: str = "manifest.json",
) -> SphLoopPlan:
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
    sph_change_tolerance = optional_float(
        normalized_convergence.get("sph_change_tolerance")
    )
    flux_ratio_tolerance = optional_float(
        normalized_convergence.get("flux_ratio_tolerance")
    )
    convergence_enabled = (
        sph_change_tolerance is not None or flux_ratio_tolerance is not None
    )
    min_iterations = int(normalized_convergence.get("min_iterations", 1))
    if min_iterations < 1:
        raise ValueError("convergence.min_iterations must be >= 1")
    if min_iterations > iterations:
        raise ValueError("convergence.min_iterations must be <= iterations")
    fail_on_nonconvergence = bool(
        normalized_convergence.get("fail_on_nonconvergence", False)
    )

    output_format = str(config.get("format", "macrolib"))
    if output_format not in {"macrolib", "multicompo"}:
        raise ValueError("format must be 'macrolib' or 'multicompo'")

    map_h5 = (
        None
        if config.get("map_h5") is None
        else resolve_path(config["map_h5"], base_dir)
    )
    scalar_flux_ids = parse_scalar_flux_ids(config.get("scalar_flux_map"))
    if map_h5 is not None and scalar_flux_ids is not None:
        raise ValueError("map_h5 and scalar_flux_map are mutually exclusive")

    summary_path = (
        loop_dir / "sph_loop_summary.json"
        if summary_json is None
        else resolve_path(summary_json, base_dir)
    )
    resolved_bundle_dir = (
        None if bundle_dir is None else resolve_path(bundle_dir, base_dir)
    )
    bundle_manifest = (
        None
        if resolved_bundle_dir is None
        else resolved_bundle_dir / bundle_manifest_name
    )

    return SphLoopPlan(
        config_path=config_file,
        base_dir=base_dir,
        input_h5=input_h5,
        loop_dir=loop_dir,
        reference_flux=reference_flux,
        iterations=iterations,
        normalized_acceptance=normalized_acceptance,
        sph_change_tolerance=sph_change_tolerance,
        flux_ratio_tolerance=flux_ratio_tolerance,
        convergence_enabled=convergence_enabled,
        min_iterations=min_iterations,
        fail_on_nonconvergence=fail_on_nonconvergence,
        output_format=output_format,
        root_name=str(config.get("root_name", DEFAULT_ROOT_NAME)),
        h_factor_default=optional_float(config.get("h_factor_default")),
        damping=float(config.get("damping", 1.0)),
        clip_min=optional_float(config.get("clip_min")),
        clip_max=optional_float(config.get("clip_max")),
        sph_kind=str(config.get("sph_kind", "sph-loop")),
        sph_real=bool(config.get("sph_real", True)),
        sph_applied=bool(config.get("sph_applied", False)),
        source_label=str(config.get("source_label", "DONJON low-order SPH loop")),
        map_h5=map_h5,
        scalar_flux_ids=scalar_flux_ids,
        scalar_flux_column=int(config.get("kn_column", 1)) - 1,
        list_offset=int(config.get("list_offset", 0)),
        summary_path=summary_path,
        audit_csv=summary_path.with_name("sph_loop_audit.csv"),
        audit_text=summary_path.with_name("sph_loop_audit.txt"),
        bundle_dir=resolved_bundle_dir,
        bundle_manifest=bundle_manifest,
        solver=solver_config(config),
        postprocessor=optional_command_config(config.get("postprocess"), "postprocess"),
        run_final_solve=bool(config.get("final_solve", False)),
    )
