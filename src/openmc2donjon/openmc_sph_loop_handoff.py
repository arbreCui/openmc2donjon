"""Prepare a fixed-OpenMC SPH loop handoff from an OpenMC recipe."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
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
    production: bool = False,
    require_volume: bool = True,
    require_h_factor: bool = False,
    require_transport_dataset: bool = True,
    expected_energy_group_structure: str | None = None,
    expected_energy_bounds: str | Path | None = None,
    expected_energy_bounds_sha256: str | None = None,
    scatter_row_balance_warn: float | None = None,
    scatter_row_balance_fail: float | None = None,
    uncertainty_warn: float | None = 0.05,
    uncertainty_fail: float | None = None,
    uncertainty_production_fail: float | None = None,
    uncertainty_mean_abs_floor: float = 1.0e-12,
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
    flux_normalization: str | None = None,
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
    resolved_flux_normalization = (
        flux_normalization
        if flux_normalization is not None
        else ("auto" if production or require_h_factor else "none")
    )
    effective_require_h_factor = require_h_factor or (
        production and resolved_flux_normalization == "auto"
    )

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
        production=production,
        require_volume=require_volume,
        require_h_factor=effective_require_h_factor,
        require_transport_dataset=require_transport_dataset,
        expected_energy_group_structure=expected_energy_group_structure,
        expected_energy_bounds=(
            None if expected_energy_bounds is None else Path(expected_energy_bounds)
        ),
        expected_energy_bounds_sha256=expected_energy_bounds_sha256,
        scatter_row_balance_warn=scatter_row_balance_warn,
        scatter_row_balance_fail=scatter_row_balance_fail,
        uncertainty_warn=uncertainty_warn,
        uncertainty_fail=uncertainty_fail,
        uncertainty_production_fail=uncertainty_production_fail,
        uncertainty_mean_abs_floor=uncertainty_mean_abs_floor,
    )
    _write_ascii(
        mgxs_h5,
        ascii_output,
        output_format=output_format,
        root_name=root_name,
        h_factor_default=h_factor_default,
    )

    loop_acceptance = _effective_loop_acceptance(
        production=production,
        acceptance=acceptance,
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
        flux_normalization=resolved_flux_normalization,
        sph_change_tolerance=sph_change_tolerance,
        flux_ratio_tolerance=flux_ratio_tolerance,
        min_iterations=min_iterations,
        fail_on_nonconvergence=fail_on_nonconvergence,
        acceptance=loop_acceptance,
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
    local = _write_relocatable_bundle_files(report, output_dir, force=force)
    artifacts = [
        ArtifactSpec(label="openmc-sph-loop-recipe", source=local.recipe),
        ArtifactSpec(label="openmc-sph-loop-solve-template", source=local.solve_template),
        ArtifactSpec(label="openmc-sph-loop-mgxs", source=local.mgxs_h5),
        ArtifactSpec(label="openmc-sph-loop-ascii", source=local.ascii_output),
        ArtifactSpec(
            label="openmc-sph-loop-reference-flux",
            source=local.reference_flux_h5,
        ),
        ArtifactSpec(label="openmc-sph-loop-flux-map", source=local.flux_map_h5),
        ArtifactSpec(label="openmc-sph-loop-config", source=local.loop_config),
        ArtifactSpec(label="openmc-sph-loop-run-script", source=local.run_script),
        ArtifactSpec(
            label="openmc-sph-loop-scaffold-summary",
            source=report.scaffold_summary_json,
        ),
        ArtifactSpec(label="openmc-sph-loop-summary", source=report.summary_json),
    ]
    if local.apply_template is not None:
        artifacts.insert(
            2,
            ArtifactSpec(
                label="openmc-sph-loop-apply-template",
                source=local.apply_template,
            ),
        )
    if local.statepoint is not None:
        artifacts.insert(
            1,
            ArtifactSpec(label="openmc-sph-loop-statepoint", source=local.statepoint),
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


@dataclass(frozen=True)
class _BundleLocalFiles:
    recipe: Path
    statepoint: Path | None
    solve_template: Path
    apply_template: Path | None
    mgxs_h5: Path
    ascii_output: Path
    reference_flux_h5: Path
    flux_map_h5: Path
    loop_config: Path
    run_script: Path


def _write_relocatable_bundle_files(
    report: OpenMCSphLoopHandoffReport,
    output_dir: Path,
    *,
    force: bool,
) -> _BundleLocalFiles:
    output_dir.mkdir(parents=True, exist_ok=True)
    original_config = json.loads(report.scaffold.loop_config.read_text(encoding="utf-8"))
    apply_template_source = _command_option_path(
        original_config.get("postprocess", {}).get("command"),
        "--deck-template",
    )
    if apply_template_source is not None and not apply_template_source.is_absolute():
        apply_template_source = report.scaffold.loop_config.parent / apply_template_source
    local = _BundleLocalFiles(
        recipe=output_dir / _bundle_filename("recipe", report.recipe),
        statepoint=(
            None
            if report.statepoint is None
            else output_dir / _bundle_filename("statepoint", report.statepoint)
        ),
        solve_template=output_dir / _bundle_filename("solve_template", report.solve_template),
        apply_template=(
            None
            if apply_template_source is None
            else output_dir / _bundle_filename("apply_template", apply_template_source)
        ),
        mgxs_h5=output_dir / "mgxs_library.h5",
        ascii_output=output_dir / report.ascii_output.name,
        reference_flux_h5=output_dir / "reference_flux.h5",
        flux_map_h5=output_dir / "flux_map.h5",
        loop_config=output_dir / "loop_config.json",
        run_script=output_dir / "run_sph_loop.sh",
    )
    _copy_bundle_file(report.recipe, local.recipe, force=force)
    if report.statepoint is not None and local.statepoint is not None:
        _copy_bundle_file(report.statepoint, local.statepoint, force=force)
    _copy_bundle_file(report.solve_template, local.solve_template, force=force)
    if apply_template_source is not None and local.apply_template is not None:
        _copy_bundle_file(apply_template_source, local.apply_template, force=force)
    _copy_bundle_file(report.mgxs_h5, local.mgxs_h5, force=force)
    _copy_bundle_file(report.ascii_output, local.ascii_output, force=force)
    _copy_bundle_file(
        report.scaffold.reference_flux_h5,
        local.reference_flux_h5,
        force=force,
    )
    _copy_bundle_file(report.scaffold.flux_map_h5, local.flux_map_h5, force=force)
    _write_bundle_loop_config(original_config, local, force=force)
    _write_bundle_run_script(local.run_script, force=force)
    return local


def _write_bundle_loop_config(
    original_config: dict[str, Any],
    local: _BundleLocalFiles,
    *,
    force: bool,
) -> None:
    _require_output_ok(local.loop_config, force=force)
    config = dict(original_config)
    config["input_h5"] = local.mgxs_h5.name
    config["output_dir"] = "sph_loop"
    config["reference_flux"] = f"{local.reference_flux_h5.name}::openmc_volume_flux"
    config["map_h5"] = local.flux_map_h5.name
    config["run_script"] = local.run_script.name

    solver = dict(config.get("solver", {}))
    solver["command"] = _bundle_command(
        solver.get("command"),
        deck_template=local.solve_template.name,
    )
    config["solver"] = solver

    postprocess = config.get("postprocess")
    if isinstance(postprocess, dict):
        postprocess = dict(postprocess)
        postprocess["command"] = _bundle_command(
            postprocess.get("command"),
            deck_template=(
                None if local.apply_template is None else local.apply_template.name
            ),
        )
        config["postprocess"] = postprocess

    local.loop_config.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_bundle_run_script(path: Path, *, force: bool) -> None:
    _require_output_ok(path, force=force)
    text = """#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec "$PYTHON_BIN" -m openmc2donjon.cli run-sph-loop --config "$SCRIPT_DIR/loop_config.json" "$@"
"""
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _copy_bundle_file(source: Path, destination: Path, *, force: bool) -> None:
    _require_output_ok(destination, force=force)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)


def _bundle_filename(stem: str, source: Path) -> str:
    suffix = "".join(source.suffixes)
    return f"{stem}{suffix}" if suffix else stem


def _command_option_path(command: object, option: str) -> Path | None:
    if not isinstance(command, list):
        return None
    for index, value in enumerate(command[:-1]):
        if value == option:
            return Path(str(command[index + 1]))
    return None


def _bundle_command(command: object, *, deck_template: str | None) -> object:
    if not isinstance(command, list):
        return command
    relocated = [str(part) for part in command]
    if (
        len(relocated) >= 3
        and relocated[1] == "-m"
        and relocated[2] == "openmc2donjon.donjon_deck_runner"
    ):
        relocated[0] = "python3"
    if deck_template is not None:
        _replace_command_option(relocated, "--deck-template", deck_template)
    return relocated


def _replace_command_option(command: list[str], option: str, value: str) -> None:
    for index, item in enumerate(command[:-1]):
        if item == option:
            command[index + 1] = value
            return


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
    production: bool,
    require_volume: bool,
    require_h_factor: bool,
    require_transport_dataset: bool,
    expected_energy_group_structure: str | None,
    expected_energy_bounds: Path | None,
    expected_energy_bounds_sha256: str | None,
    scatter_row_balance_warn: float | None,
    scatter_row_balance_fail: float | None,
    uncertainty_warn: float | None,
    uncertainty_fail: float | None,
    uncertainty_production_fail: float | None,
    uncertainty_mean_abs_floor: float,
) -> None:
    if not check:
        return
    ok = run_preflight(
        [input_h5],
        output_format=output_format,
        output_path=output_path,
        production=production,
        require_volume=require_volume,
        require_h_factor=require_h_factor,
        require_transport_dataset=require_transport_dataset,
        expected_energy_group_structure=expected_energy_group_structure,
        expected_energy_bounds=expected_energy_bounds,
        expected_energy_bounds_sha256=expected_energy_bounds_sha256,
        scatter_row_balance_warn=scatter_row_balance_warn,
        scatter_row_balance_fail=scatter_row_balance_fail,
        uncertainty_warn=uncertainty_warn,
        uncertainty_fail=uncertainty_fail,
        uncertainty_production_fail=uncertainty_production_fail,
        uncertainty_mean_abs_floor=uncertainty_mean_abs_floor,
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


def _effective_loop_acceptance(
    *,
    production: bool,
    acceptance: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not production:
        return None if acceptance is None else dict(acceptance)
    if acceptance is None:
        return {"preset": "production"}
    out = dict(acceptance)
    out.setdefault("preset", "production")
    return out
