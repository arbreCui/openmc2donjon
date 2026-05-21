"""Configuration parsing helpers for the fixed-OpenMC SPH loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIG_SCHEMA = "openmc2donjon.sph-loop-config.v1"


def load_config(path: Path) -> dict[str, Any]:
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


def convergence_config(config: dict[str, Any]) -> dict[str, Any]:
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
        value = optional_float(out.get(key))
        if value is not None and value < 0.0:
            raise ValueError(f"convergence.{key} must be >= 0")
        out[key] = value
    return out


def acceptance_config(config: dict[str, Any]) -> dict[str, Any]:
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


def solver_config(config: dict[str, Any]) -> dict[str, Any]:
    return command_config(config.get("solver"), "solver")


def optional_command_config(value: object, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return command_config(value, name)


def command_config(value: object, name: str) -> dict[str, Any]:
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


def resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def resolve_source(value: str, base_dir: Path) -> str:
    if "::" not in value:
        return str(resolve_path(value, base_dir))
    path, dataset = value.split("::", maxsplit=1)
    return f"{resolve_path(path, base_dir)}::{dataset}"


def parse_scalar_flux_ids(value: object) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("scalar_flux_map must be a JSON object")
    return {str(name): int(index) for name, index in value.items()}


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
