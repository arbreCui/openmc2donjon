"""Build JSON configs for the generic DONJON SPH loop driver."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path
import sys
from typing import Any

from .sph_loop import CONFIG_SCHEMA


DEFAULT_CASE_DIR = "openmc2donjon/case_runs/openmc2donjon_sph_loop"
DEFAULT_CASE_ID_PREFIX = "openmc2donjon_sph_loop"
DEFAULT_STAGE_PREFIX = "odj_sph_loop"
DEFAULT_DRIVER_MODULE = "openmc2donjon.donjon_deck_runner"
DEFAULT_APPLY_TEMPLATE = "apply_nsph_mac.x2m.in"


def default_apply_template_path() -> Path:
    """Return the installed generic DONJON DSPH/MAC apply template path."""

    return Path(str(resources.files("openmc2donjon.templates") / DEFAULT_APPLY_TEMPLATE))


def build_donjon_sph_loop_config(
    *,
    input_h5: str | Path,
    output_dir: str | Path,
    solve_template: str | Path,
    flux_map: str | Path,
    reference_flux: str | Path | None = None,
    output_format: str = "macrolib",
    final_solve: bool = True,
    iterations: int = 2,
    damping: float = 0.5,
    clip_min: float | None = 0.5,
    clip_max: float | None = 3.0,
    sph_change_tolerance: float | None = None,
    flux_ratio_tolerance: float | None = None,
    min_iterations: int = 1,
    fail_on_nonconvergence: bool = False,
    donjon_root: str | Path = "/Users/wen/dragon-5.1/Donjon",
    apply_template: str | Path | None = None,
    driver: str | Path | None = None,
    python_bin: str | Path | None = None,
    case_id_prefix: str = DEFAULT_CASE_ID_PREFIX,
    stage_prefix: str = DEFAULT_STAGE_PREFIX,
    case_dir: str = DEFAULT_CASE_DIR,
    sph_kind: str = "donjon-sph-loop",
    sph_real: bool = False,
    sph_applied: bool = False,
    source_label: str = "Generic DONJON SPH loop",
    postprocess_output: str = "corrected.macrolib.txt",
    root_name: str | None = None,
    h_factor_default: float | None = None,
) -> dict[str, Any]:
    """Return a ``run-sph-loop`` config using the packaged DONJON runner.

    The user supplies the case-specific low-order DONJON solve template.  The
    packaged runner stages ASCII macrolibs, renders the solve/apply decks, runs
    ``rdonjon``, and hands the resulting ``L_FLUX`` dump back to
    ``run-sph-loop``.
    """

    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    if min_iterations < 1:
        raise ValueError("min_iterations must be >= 1")
    if min_iterations > iterations:
        raise ValueError("min_iterations must be <= iterations")
    if sph_change_tolerance is not None and sph_change_tolerance < 0.0:
        raise ValueError("sph_change_tolerance must be >= 0")
    if flux_ratio_tolerance is not None and flux_ratio_tolerance < 0.0:
        raise ValueError("flux_ratio_tolerance must be >= 0")
    if output_format not in {"macrolib", "multicompo"}:
        raise ValueError("output_format must be 'macrolib' or 'multicompo'")

    flux_map_path = Path(flux_map)
    reference = _reference_flux(reference_flux, flux_map_path)
    apply_path = default_apply_template_path() if apply_template is None else Path(apply_template)
    py = str(python_bin if python_bin is not None else sys.executable)
    driver_prefix = [py, str(driver)] if driver is not None else [py, "-m", DEFAULT_DRIVER_MODULE]

    config: dict[str, Any] = {
        "schema": CONFIG_SCHEMA,
        "input_h5": str(input_h5),
        "output_dir": str(output_dir),
        "reference_flux": reference,
        "map_h5": str(flux_map_path),
        "iterations": iterations,
        "format": output_format,
        "final_solve": final_solve,
        "damping": damping,
        "clip_min": clip_min,
        "clip_max": clip_max,
        "convergence": {
            "sph_change_tolerance": sph_change_tolerance,
            "flux_ratio_tolerance": flux_ratio_tolerance,
            "min_iterations": min_iterations,
            "fail_on_nonconvergence": bool(fail_on_nonconvergence),
        },
        "sph_kind": sph_kind,
        "sph_real": sph_real,
        "sph_applied": sph_applied,
        "source_label": source_label,
        "solver": {
            "command": [
                *driver_prefix,
                "solve",
                "--donjon-root",
                str(donjon_root),
                "--deck-template",
                str(solve_template),
                "--macrolib",
                "{ascii_input}",
                "--result",
                "{result}",
                "--iteration",
                "{iteration}",
                "--case-id",
                f"{case_id_prefix}_solve_iter{{iteration}}",
                "--case-dir",
                case_dir,
                "--work-dir",
                f"/tmp/{stage_prefix}_solve_iter{{iteration}}",
            ],
            "result": "donjon_flux.result",
        },
        "postprocess": {
            "command": [
                *driver_prefix,
                "apply",
                "--donjon-root",
                str(donjon_root),
                "--deck-template",
                str(apply_path),
                "--macrolib",
                "{workflow_ascii}",
                "--output",
                "{output}",
                "--iteration",
                "{iteration1}",
                "--case-id",
                f"{case_id_prefix}_apply_iter{{iteration1}}",
                "--case-dir",
                case_dir,
                "--work-dir",
                f"/tmp/{stage_prefix}_apply_iter{{iteration1}}",
            ],
            "output": postprocess_output,
        },
    }
    if root_name is not None:
        config["root_name"] = root_name
    if h_factor_default is not None:
        config["h_factor_default"] = h_factor_default
    return config


def write_donjon_sph_loop_config(
    output: str | Path,
    *,
    input_h5: str | Path,
    output_dir: str | Path,
    solve_template: str | Path,
    flux_map: str | Path,
    reference_flux: str | Path | None = None,
    output_format: str = "macrolib",
    final_solve: bool = True,
    iterations: int = 2,
    damping: float = 0.5,
    clip_min: float | None = 0.5,
    clip_max: float | None = 3.0,
    sph_change_tolerance: float | None = None,
    flux_ratio_tolerance: float | None = None,
    min_iterations: int = 1,
    fail_on_nonconvergence: bool = False,
    donjon_root: str | Path = "/Users/wen/dragon-5.1/Donjon",
    apply_template: str | Path | None = None,
    driver: str | Path | None = None,
    python_bin: str | Path | None = None,
    case_id_prefix: str = DEFAULT_CASE_ID_PREFIX,
    stage_prefix: str = DEFAULT_STAGE_PREFIX,
    case_dir: str = DEFAULT_CASE_DIR,
    sph_kind: str = "donjon-sph-loop",
    sph_real: bool = False,
    sph_applied: bool = False,
    source_label: str = "Generic DONJON SPH loop",
    postprocess_output: str = "corrected.macrolib.txt",
    root_name: str | None = None,
    h_factor_default: float | None = None,
) -> Path:
    """Write a ``run-sph-loop`` JSON config and return its path."""

    path = Path(output)
    config = build_donjon_sph_loop_config(
        input_h5=input_h5,
        output_dir=output_dir,
        solve_template=solve_template,
        flux_map=flux_map,
        reference_flux=reference_flux,
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
        donjon_root=donjon_root,
        apply_template=apply_template,
        driver=driver,
        python_bin=python_bin,
        case_id_prefix=case_id_prefix,
        stage_prefix=stage_prefix,
        case_dir=case_dir,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        source_label=source_label,
        postprocess_output=postprocess_output,
        root_name=root_name,
        h_factor_default=h_factor_default,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _reference_flux(reference_flux: str | Path | None, flux_map: Path) -> str:
    if reference_flux is None:
        return f"{flux_map}::openmc_volume_flux"
    value = str(reference_flux)
    if "::" in value:
        return value
    return f"{value}::openmc_volume_flux"
