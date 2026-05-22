"""Prepare a fixed-OpenMC SPH loop handoff from an OpenMC recipe."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from . import __version__
from .bundle import ArtifactSpec, bundle_artifacts
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .openmc_statepoint import export_openmc_statepoint_recipe
from .sph_loop_scaffold import SphLoopScaffoldReport, create_sph_loop_scaffold


SCHEMA = "openmc2donjon.openmc-sph-loop-handoff.v1"
PASS_DECISION = "openmc2donjon_openmc_sph_loop_handoff_passed"


@dataclass(frozen=True)
class OpenMCSphLoopHandoffReport:
    recipe: Path
    statepoint: Path | None
    solve_template: Path
    run_dir: Path
    mgxs_h5: Path
    ascii_output: Path
    scaffold: SphLoopScaffoldReport
    output_format: str
    checked: bool
    check_summary_json: Path | None
    summary_json: Path
    scaffold_summary_json: Path
    bundle_manifest: Path | None


def prepare_openmc_sph_loop_handoff(
    *,
    recipe: str | Path,
    run_dir: str | Path,
    solve_template: str | Path,
    statepoint: str | Path | None = None,
    no_load_statepoint: bool = False,
    scatter_mgxs_type: str | None = None,
    output_format: str = "macrolib",
    output: str | Path | None = None,
    root_name: str = DEFAULT_ROOT_NAME,
    h_factor_default: float | None = None,
    check: bool = True,
    check_summary_json: str | Path | None = None,
    require_volume: bool = True,
    require_transport_dataset: bool = True,
    scatter_row_balance_warn: float | None = None,
    scatter_row_balance_fail: float | None = None,
    reference_flux: str | Path | None = None,
    reference_flux_dataset: str = "openmc_volume_flux",
    scaffold_dir: str | Path | None = None,
    run_script_output: str | Path | None = None,
    scalar_flux_ids: dict[str, int] | None = None,
    sequential_scalar_flux_map: bool = False,
    donjon_root: str | Path = "/Users/wen/dragon-5.1/Donjon",
    apply_template: str | Path | None = None,
    python_bin: str | Path | None = None,
    iterations: int = 2,
    damping: float = 0.5,
    clip_min: float | None = 0.5,
    clip_max: float | None = 3.0,
    sph_change_tolerance: float | None = None,
    flux_ratio_tolerance: float | None = None,
    min_iterations: int = 1,
    fail_on_nonconvergence: bool = False,
    acceptance: dict[str, Any] | None = None,
    case_id_prefix: str = "openmc_sph_loop",
    stage_prefix: str = "odj_openmc_sph_loop",
    case_dir: str = "openmc2donjon/case_runs/openmc_sph_loop",
    sph_kind: str = "openmc-sph-loop",
    sph_real: bool = False,
    sph_applied: bool = False,
    source_label: str = "OpenMC SPH loop handoff",
    postprocess_output: str = "corrected.macrolib.txt",
    final_solve: bool = True,
    force: bool = False,
    summary_json: str | Path | None = None,
    scaffold_summary_json: str | Path | None = None,
    bundle_dir: str | Path | None = None,
    bundle_manifest_name: str = "manifest.json",
) -> OpenMCSphLoopHandoffReport:
    """Export OpenMC MGXS and write the corresponding SPH loop scaffold.

    This is a convenience orchestrator for the production handoff. It keeps the
    OpenMC base cross sections fixed: later SPH iterations update only the
    sidecar factors consumed by ``run-sph-loop``.
    """

    if output_format not in {"macrolib", "multicompo"}:
        raise ValueError("output_format must be 'macrolib' or 'multicompo'")
    if not no_load_statepoint and statepoint is None:
        raise ValueError("statepoint is required unless no_load_statepoint is true")

    run_root = Path(run_dir)
    _prepare_run_dir(run_root, force=force)
    mgxs_h5 = run_root / "mgxs_library.h5"
    ascii_output = (
        Path(output)
        if output is not None
        else run_root / _default_ascii_name(output_format)
    )
    check_summary = (
        Path(check_summary_json)
        if check_summary_json is not None
        else run_root / "check_summary.json"
    )
    summary_path = (
        Path(summary_json)
        if summary_json is not None
        else run_root / "openmc_sph_loop_handoff_summary.json"
    )
    scaffold_root = (
        Path(scaffold_dir) if scaffold_dir is not None else run_root / "sph_loop_inputs"
    )
    scaffold_summary = (
        Path(scaffold_summary_json)
        if scaffold_summary_json is not None
        else scaffold_root / "scaffold_summary.json"
    )
    bundle_root = None if bundle_dir is None else Path(bundle_dir)
    bundle_manifest = (
        None if bundle_root is None else bundle_root / bundle_manifest_name
    )

    _require_output_ok(mgxs_h5, force=force)
    _require_output_ok(ascii_output, force=force)
    recipe_summary = export_openmc_statepoint_recipe(
        recipe,
        mgxs_h5,
        statepoint_path=statepoint,
        load_statepoint=not no_load_statepoint,
        scatter_mgxs_type=scatter_mgxs_type,
        overwrite=force,
    )
    _run_optional_preflight(
        mgxs_h5,
        ascii_output,
        output_format=output_format,
        check=check,
        check_summary_json=check_summary,
        require_volume=require_volume,
        require_transport_dataset=require_transport_dataset,
        scatter_row_balance_warn=scatter_row_balance_warn,
        scatter_row_balance_fail=scatter_row_balance_fail,
    )
    _write_ascii(
        mgxs_h5,
        ascii_output,
        output_format=output_format,
        root_name=root_name,
        h_factor_default=h_factor_default,
    )

    scaffold_report = create_sph_loop_scaffold(
        mgxs_h5,
        scaffold_root,
        reference_flux=reference_flux or f"{mgxs_h5}::{reference_flux_dataset}",
        solve_template=solve_template,
        run_script_output=run_script_output,
        scalar_flux_ids=scalar_flux_ids,
        sequential_scalar_flux_map=sequential_scalar_flux_map,
        output_format=output_format,
        final_solve=final_solve,
        iterations=iterations,
        damping=damping,
        clip_min=clip_min,
        clip_max=clip_max,
        sph_change_tolerance=sph_change_tolerance,
        flux_ratio_tolerance=flux_ratio_tolerance,
        min_iterations=min_iterations,
        fail_on_nonconvergence=fail_on_nonconvergence,
        acceptance=acceptance,
        donjon_root=donjon_root,
        apply_template=apply_template,
        python_bin=python_bin,
        case_id_prefix=case_id_prefix,
        stage_prefix=stage_prefix,
        case_dir=case_dir,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        source_label=source_label,
        postprocess_output=postprocess_output,
        root_name=root_name if output_format == "multicompo" else None,
        h_factor_default=h_factor_default,
        force=force,
        summary_json=scaffold_summary,
    )

    report = OpenMCSphLoopHandoffReport(
        recipe=recipe_summary.recipe_path,
        statepoint=recipe_summary.statepoint_path,
        solve_template=Path(solve_template),
        run_dir=run_root,
        mgxs_h5=mgxs_h5,
        ascii_output=ascii_output,
        scaffold=scaffold_report,
        output_format=output_format,
        checked=check,
        check_summary_json=check_summary if check else None,
        summary_json=summary_path,
        scaffold_summary_json=scaffold_summary,
        bundle_manifest=bundle_manifest,
    )
    write_summary(summary_path, report)
    if bundle_root is not None:
        write_bundle(
            report,
            output_dir=bundle_root,
            manifest_name=bundle_manifest_name,
            force=force,
        )
    print_report(report)
    return report


def print_report(report: OpenMCSphLoopHandoffReport) -> None:
    print("OpenMC-to-DONJON SPH loop handoff")
    print(f"  schema: {SCHEMA}")
    print(f"  recipe: {report.recipe}")
    if report.statepoint is not None:
        print(f"  statepoint: {report.statepoint}")
    print(f"  run_dir: {report.run_dir}")
    print(f"  mgxs_h5: {report.mgxs_h5}")
    print(f"  ascii_output: {report.ascii_output}")
    print(f"  scaffold_config: {report.scaffold.loop_config}")
    print(f"  run_script: {report.scaffold.run_script}")
    if report.bundle_manifest is not None:
        print(f"  bundle_manifest: {report.bundle_manifest}")
    print(
        f"  mixtures={len(report.scaffold.mixture_names)} "
        f"groups={report.scaffold.energy_groups} format={report.output_format}"
    )
    print()
    print("OpenMC SPH loop handoff decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: OpenMCSphLoopHandoffReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "recipe": str(report.recipe),
        "statepoint": None if report.statepoint is None else str(report.statepoint),
        "solve_template": str(report.solve_template),
        "run_dir": str(report.run_dir),
        "mgxs_h5": str(report.mgxs_h5),
        "ascii_output": str(report.ascii_output),
        "format": report.output_format,
        "checked": report.checked,
        "check_summary_json": (
            None if report.check_summary_json is None else str(report.check_summary_json)
        ),
        "scaffold_summary_json": str(report.scaffold_summary_json),
        "bundle_manifest": (
            None if report.bundle_manifest is None else str(report.bundle_manifest)
        ),
        "reference_flux_h5": str(report.scaffold.reference_flux_h5),
        "flux_map_h5": str(report.scaffold.flux_map_h5),
        "loop_config": str(report.scaffold.loop_config),
        "run_script": str(report.scaffold.run_script),
        "run_command": list(report.scaffold.run_command),
        "mixture_count": len(report.scaffold.mixture_names),
        "mixture_names": list(report.scaffold.mixture_names),
        "energy_groups": report.scaffold.energy_groups,
        "scalar_flux_ids": list(report.scaffold.scalar_flux_ids),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_bundle(
    report: OpenMCSphLoopHandoffReport,
    *,
    output_dir: Path,
    manifest_name: str,
    force: bool,
) -> None:
    artifacts = [
        ArtifactSpec(label="openmc-sph-loop-recipe", source=report.recipe),
        ArtifactSpec(label="openmc-sph-loop-solve-template", source=report.solve_template),
        ArtifactSpec(label="openmc-sph-loop-mgxs", source=report.mgxs_h5),
        ArtifactSpec(label="openmc-sph-loop-ascii", source=report.ascii_output),
        ArtifactSpec(
            label="openmc-sph-loop-reference-flux",
            source=report.scaffold.reference_flux_h5,
        ),
        ArtifactSpec(label="openmc-sph-loop-flux-map", source=report.scaffold.flux_map_h5),
        ArtifactSpec(label="openmc-sph-loop-config", source=report.scaffold.loop_config),
        ArtifactSpec(label="openmc-sph-loop-run-script", source=report.scaffold.run_script),
        ArtifactSpec(
            label="openmc-sph-loop-scaffold-summary",
            source=report.scaffold_summary_json,
        ),
        ArtifactSpec(label="openmc-sph-loop-summary", source=report.summary_json),
    ]
    if report.statepoint is not None:
        artifacts.insert(
            1,
            ArtifactSpec(label="openmc-sph-loop-statepoint", source=report.statepoint),
        )
    if report.check_summary_json is not None:
        artifacts.append(
            ArtifactSpec(
                label="openmc-sph-loop-check-summary",
                source=report.check_summary_json,
            )
        )
    bundle_artifacts(
        output_dir=output_dir,
        artifacts=artifacts,
        manifest_name=manifest_name,
        force=force,
    )


def _prepare_run_dir(path: Path, *, force: bool) -> None:
    if path.exists() and any(path.iterdir()) and not force:
        raise FileExistsError(f"run directory is not empty; use --force: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _require_output_ok(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {path}")


def _run_optional_preflight(
    input_h5: Path,
    output_path: Path,
    *,
    output_format: str,
    check: bool,
    check_summary_json: Path,
    require_volume: bool,
    require_transport_dataset: bool,
    scatter_row_balance_warn: float | None,
    scatter_row_balance_fail: float | None,
) -> None:
    if not check:
        return
    ok = run_preflight(
        [input_h5],
        output_format=output_format,
        output_path=output_path,
        require_volume=require_volume,
        require_transport_dataset=require_transport_dataset,
        scatter_row_balance_warn=scatter_row_balance_warn,
        scatter_row_balance_fail=scatter_row_balance_fail,
        summary_json=check_summary_json,
    )
    if not ok:
        raise RuntimeError("MGXS input contract preflight failed")


def _write_ascii(
    input_h5: Path,
    output_path: Path,
    *,
    output_format: str,
    root_name: str,
    h_factor_default: float | None,
) -> None:
    if output_format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            input_h5,
            output_path,
            h_factor_default=h_factor_default,
        )
    else:
        convert_mgxs_hdf5(
            input_h5,
            output_path,
            root_name=root_name,
            h_factor_default=h_factor_default,
        )


def _default_ascii_name(output_format: str) -> str:
    if output_format == "macrolib":
        return "out.macrolib.txt"
    return "out.mcompo.txt"
