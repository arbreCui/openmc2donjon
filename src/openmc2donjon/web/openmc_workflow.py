"""OpenMC recipe/statepoint workflow planning endpoints for the web UI."""

from __future__ import annotations

from pathlib import Path
import shlex
from typing import Any


OPENMC_WORKFLOW_SCHEMA = "openmc2donjon.openmc-workflow-plan.v1"

_FORMATS = {"multicompo", "macrolib"}
_WORKFLOWS = {"one-step", "two-step"}
_EQUIVALENCE = {"direct", "adf", "sph", "flux-ratio-adf"}


def register_openmc_workflow_routes(app: Any, *, mock_mode: bool) -> None:
    """Register OpenMC workflow planning endpoints on a FastAPI app."""

    from fastapi import Body, HTTPException

    request_body = Body(...)

    @app.post("/api/openmc-workflow/plan")
    def api_openmc_workflow_plan(payload: dict[str, Any] = request_body) -> dict[str, Any]:
        request = _normalize_request(payload, HTTPException)
        return _build_plan(request, mock_mode=mock_mode)


def _normalize_request(payload: dict[str, Any], http_exception: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise http_exception(status_code=422, detail="request body must be an object")
    workflow = _choice(payload.get("workflow", "one-step"), _WORKFLOWS, "workflow", http_exception)
    output_format = _choice(payload.get("format", "multicompo"), _FORMATS, "format", http_exception)
    equivalence = _choice(
        payload.get("equivalence", "direct"),
        _EQUIVALENCE,
        "equivalence",
        http_exception,
    )
    return {
        "workflow": workflow,
        "recipe_path": _string(payload.get("recipe_path", "")),
        "statepoint_path": _string(payload.get("statepoint_path", "")),
        "load_statepoint": _bool(payload.get("load_statepoint", True)),
        "format": output_format,
        "output_path": _string(payload.get("output_path", "")),
        "run_dir": _string(payload.get("run_dir", "")),
        "keep_hdf5_path": _string(payload.get("keep_hdf5_path", "")),
        "check": _bool(payload.get("check", True)),
        "production": _bool(payload.get("production", False)),
        "strict_dry_run": _bool(payload.get("strict_dry_run", False)),
        "h_factor_default": _optional_number(payload.get("h_factor_default"), http_exception),
        "require_known_energy_mesh": _bool(payload.get("require_known_energy_mesh", False)),
        "warn_unknown_energy_mesh": _bool(payload.get("warn_unknown_energy_mesh", True)),
        "equivalence": equivalence,
        "adf_source": _string(payload.get("adf_source", "")),
        "sph_source": _string(payload.get("sph_source", "")),
        "build_flux_ratio_adf": equivalence == "flux-ratio-adf"
        or _bool(payload.get("build_flux_ratio_adf", False)),
    }


def _build_plan(request: dict[str, Any], *, mock_mode: bool) -> dict[str, Any]:
    checks = _readiness_checks(request, mock_mode=mock_mode)
    artifacts = _artifacts(request)
    commands = _commands(request)
    return {
        "schema": OPENMC_WORKFLOW_SCHEMA,
        "ok": all(check["status"] != "fail" for check in checks),
        "mock_mode": mock_mode,
        "workflow": request["workflow"],
        "workflow_label": _workflow_label(str(request["workflow"])),
        "equivalence": request["equivalence"],
        "steps": _steps(request),
        "artifacts": artifacts,
        "checks": checks,
        "commands": commands,
        "primary_command_text": commands[0]["text"] if commands else "",
        "next_actions": _next_actions(request),
    }


def _readiness_checks(request: dict[str, Any], *, mock_mode: bool) -> list[dict[str, Any]]:
    recipe = str(request["recipe_path"]).strip()
    statepoint = str(request["statepoint_path"]).strip()
    load_statepoint = bool(request["load_statepoint"])
    run_dir = str(request["run_dir"]).strip()
    output = str(request["output_path"]).strip() or _default_output(str(request["format"]))
    hdf5 = str(request["keep_hdf5_path"]).strip() or _default_hdf5(request)
    checks = [
        _path_check(
            "recipe",
            recipe,
            required=True,
            must_exist=not mock_mode,
            expected_suffix=".py",
        ),
        _path_check(
            "statepoint",
            statepoint,
            required=load_statepoint,
            must_exist=(not mock_mode and load_statepoint),
            expected_suffix=".h5",
        ),
        _parent_check("ASCII output directory", output, must_exist=not mock_mode),
        _parent_check("HDF5 handoff directory", hdf5, must_exist=not mock_mode),
    ]
    if run_dir:
        checks.append(_directory_parent_check("run directory parent", run_dir, must_exist=not mock_mode))
    else:
        checks.append(
            {
                "name": "run directory",
                "status": "warn",
                "message": "No managed run directory selected; artifacts will be less organized.",
            }
        )
    if request["equivalence"] == "adf":
        checks.append(
            _path_check(
                "ADF sidecar",
                str(request["adf_source"]),
                required=True,
                must_exist=not mock_mode,
                expected_suffix=".h5",
            )
        )
    if request["equivalence"] == "sph":
        checks.append(
            _path_check(
                "SPH sidecar",
                str(request["sph_source"]),
                required=True,
                must_exist=not mock_mode,
                expected_suffix=".h5",
            )
        )
    if request["equivalence"] == "flux-ratio-adf" and not run_dir:
        checks.append(
            {
                "name": "flux-ratio ADF run directory",
                "status": "fail",
                "message": "Flux-ratio ADF construction requires a managed run directory.",
            }
        )
    if request["workflow"] == "two-step" and request["equivalence"] == "flux-ratio-adf":
        checks.append(
            {
                "name": "two-step flux-ratio ADF",
                "status": "fail",
                "message": "Flux-ratio ADF construction is planned through the one-step workflow.",
            }
        )
    return checks


def _path_check(
    name: str,
    raw: str,
    *,
    required: bool,
    must_exist: bool,
    expected_suffix: str | None = None,
) -> dict[str, Any]:
    path = raw.strip()
    if not path:
        return {
            "name": name,
            "status": "fail" if required else "skipped",
            "message": "Required path is missing." if required else "Not used by this plan.",
        }
    suffix_ok = expected_suffix is None or path.endswith(expected_suffix)
    if not suffix_ok:
        return {
            "name": name,
            "status": "warn",
            "message": f"Path does not end with {expected_suffix}; verify it is intentional.",
        }
    if must_exist and not Path(path).expanduser().exists():
        return {
            "name": name,
            "status": "fail",
            "message": f"Path not found: {path}",
        }
    return {
        "name": name,
        "status": "pass",
        "message": "Ready.",
    }


def _parent_check(name: str, raw: str, *, must_exist: bool) -> dict[str, Any]:
    path = raw.strip()
    if not path:
        return {"name": name, "status": "fail", "message": "Path is missing."}
    parent = Path(path).expanduser().parent
    if must_exist and not parent.exists():
        return {
            "name": name,
            "status": "fail",
            "message": f"Directory not found: {parent}",
        }
    return {"name": name, "status": "pass", "message": "Ready."}


def _directory_parent_check(name: str, raw: str, *, must_exist: bool) -> dict[str, Any]:
    parent = Path(raw).expanduser().parent
    if must_exist and not parent.exists():
        return {
            "name": name,
            "status": "fail",
            "message": f"Directory not found: {parent}",
        }
    return {"name": name, "status": "pass", "message": "Ready."}


def _steps(request: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = str(request["workflow"])
    steps = [
        {
            "id": "recipe",
            "title": "Recipe dry run",
            "summary": "Inspect the OpenMC mgxs.Library recipe and selected domains.",
        },
        {
            "id": "export",
            "title": "Export MGXS HDF5",
            "summary": "Build the openmc2donjon HDF5 handoff from the recipe/statepoint.",
        },
    ]
    if request["equivalence"] == "adf":
        steps.append(
            {
                "id": "adf",
                "title": "Inject ADF/DF",
                "summary": "Attach discontinuity factors from an ADF sidecar.",
            }
        )
    elif request["equivalence"] == "sph":
        steps.append(
            {
                "id": "sph",
                "title": "Inject SPH",
                "summary": "Attach NSPH factors from an SPH sidecar.",
            }
        )
    elif request["equivalence"] == "flux-ratio-adf":
        steps.append(
            {
                "id": "flux-ratio-adf",
                "title": "Build flux-ratio ADF",
                "summary": "Use OpenMC surface flux and low-order driver data to build ADF/DF.",
            }
        )
    if bool(request["check"]) or bool(request["production"]):
        steps.append(
            {
                "id": "preflight",
                "title": "Production preflight" if bool(request["production"]) else "Preflight checks",
                "summary": (
                    "Run production contract, mesh, physics, uncertainty, and equivalence gates."
                    if bool(request["production"])
                    else "Run HDF5 contract and selected physics consistency checks."
                ),
            }
        )
    convert_summary = "Run the one-step conversion."
    if workflow == "two-step":
        convert_summary = (
            "Run conversion on the augmented HDF5 handoff."
            if request["equivalence"] in {"adf", "sph"}
            else "Run direct conversion on the exported HDF5 handoff."
        )
    steps.append(
        {
            "id": "convert",
            "title": "Convert to DONJON ASCII",
            "summary": convert_summary,
        }
    )
    if str(request["run_dir"]).strip():
        steps.append(
            {
                "id": "bundle",
                "title": "Bundle artifacts",
                "summary": "Write managed summaries, manifest, and validation payloads.",
            }
        )
    return steps


def _artifacts(request: dict[str, Any]) -> list[dict[str, Any]]:
    output = str(request["output_path"]).strip() or _default_output(str(request["format"]))
    hdf5 = str(request["keep_hdf5_path"]).strip() or _default_hdf5(request)
    run_dir = str(request["run_dir"]).strip()
    artifacts = [
        {"label": "MGXS HDF5 handoff", "path": hdf5, "kind": "hdf5", "will_write": True},
        {"label": "DONJON ASCII output", "path": output, "kind": "ascii", "will_write": True},
    ]
    if request["workflow"] == "two-step" and request["equivalence"] in {"adf", "sph"}:
        kind = str(request["equivalence"])
        artifacts.insert(
            1,
            {
                "label": f"{kind.upper()}-augmented HDF5 handoff",
                "path": _augmented_hdf5(request, kind),
                "kind": "hdf5",
                "will_write": True,
            },
        )
    if run_dir:
        artifacts.extend(
            [
                {
                    "label": "Pipeline summary",
                    "path": f"{run_dir.rstrip('/')}/openmc2donjon_from_openmc_summary.json",
                    "kind": "json",
                    "will_write": True,
                },
                {
                    "label": "Bundle manifest",
                    "path": f"{run_dir.rstrip('/')}/manifest.json",
                    "kind": "json",
                    "will_write": True,
                },
            ]
        )
    return artifacts


def _commands(request: dict[str, Any]) -> list[dict[str, Any]]:
    if request["workflow"] == "two-step":
        commands = [_command_payload("Export MGXS HDF5", _export_command(request))]
        conversion_input = _default_hdf5(request)
        if request["equivalence"] == "adf":
            conversion_input = _augmented_hdf5(request, "adf")
            commands.append(
                _command_payload(
                    "Inject ADF/DF",
                    _augment_adf_command(request, output_hdf5=conversion_input),
                )
            )
        elif request["equivalence"] == "sph":
            conversion_input = _augmented_hdf5(request, "sph")
            commands.append(
                _command_payload(
                    "Inject SPH",
                    _augment_sph_command(request, output_hdf5=conversion_input),
                )
            )
        commands.append(
            _command_payload(
                "Convert HDF5 to ASCII",
                _direct_convert_command(request, input_hdf5=conversion_input),
            )
        )
        return commands
    return [_command_payload("One-step OpenMC handoff", _from_openmc_command(request))]


def _from_openmc_command(request: dict[str, Any]) -> list[str]:
    command = ["openmc2donjon-from-openmc", "--recipe", str(request["recipe_path"])]
    if request["load_statepoint"]:
        command.extend(["--statepoint", str(request["statepoint_path"])])
    else:
        command.append("--no-load-statepoint")
    command.extend(["--format", str(request["format"])])
    output = str(request["output_path"]).strip()
    if output:
        command.extend(["-o", output])
    keep_hdf5 = str(request["keep_hdf5_path"]).strip()
    if keep_hdf5:
        command.extend(["--keep-hdf5", keep_hdf5])
    _append_common_flags(command, request)
    return command


def _export_command(request: dict[str, Any]) -> list[str]:
    command = ["openmc2donjon-export", "--recipe", str(request["recipe_path"])]
    if request["load_statepoint"]:
        command.extend(["--statepoint", str(request["statepoint_path"])])
    else:
        command.append("--no-load-statepoint")
    command.extend(["-o", _default_hdf5(request)])
    return command


def _augment_adf_command(request: dict[str, Any], *, output_hdf5: str) -> list[str]:
    return [
        "openmc2donjon",
        "augment-adf",
        _default_hdf5(request),
        "--adf-source",
        str(request["adf_source"]),
        "-o",
        output_hdf5,
    ]


def _augment_sph_command(request: dict[str, Any], *, output_hdf5: str) -> list[str]:
    return [
        "openmc2donjon",
        "augment-sph",
        _default_hdf5(request),
        "--sph-source",
        str(request["sph_source"]),
        "-o",
        output_hdf5,
    ]


def _direct_convert_command(request: dict[str, Any], *, input_hdf5: str | None = None) -> list[str]:
    command = [
        "openmc2donjon",
        input_hdf5 or _default_hdf5(request),
        "--format",
        str(request["format"]),
        "-o",
        str(request["output_path"]).strip() or _default_output(str(request["format"])),
    ]
    _append_direct_conversion_flags(command, request)
    return command


def _append_common_flags(command: list[str], request: dict[str, Any]) -> None:
    run_dir = str(request["run_dir"]).strip()
    if run_dir:
        command.extend(["--run-dir", run_dir])
    if request["check"]:
        command.append("--check")
    if request["production"]:
        command.append("--production")
    _append_common_conversion_flags(command, request)
    if request["equivalence"] == "adf":
        command.extend(["--adf-source", str(request["adf_source"])])
    elif request["equivalence"] == "sph":
        command.extend(["--sph-source", str(request["sph_source"])])
    elif request["equivalence"] == "flux-ratio-adf":
        command.append("--build-flux-ratio-adf")
    if request["strict_dry_run"]:
        command.append("--strict-dry-run")


def _append_direct_conversion_flags(command: list[str], request: dict[str, Any]) -> None:
    if request["check"]:
        command.append("--check")
    if request["production"]:
        command.append("--production")
    _append_common_conversion_flags(command, request)


def _append_common_conversion_flags(command: list[str], request: dict[str, Any]) -> None:
    if request["production"] or request["check"]:
        if request["warn_unknown_energy_mesh"]:
            command.append("--warn-unknown-energy-mesh")
        if request["require_known_energy_mesh"]:
            command.append("--require-known-energy-mesh")
    if request["h_factor_default"] is not None:
        command.extend(["--h-factor-default", str(request["h_factor_default"])])


def _command_payload(label: str, command: list[str]) -> dict[str, Any]:
    return {
        "label": label,
        "argv": command,
        "text": " ".join(shlex.quote(part) for part in command),
    }


def _next_actions(request: dict[str, Any]) -> list[str]:
    actions = [
        "Run the recipe dry-run first if the recipe/statepoint pairing has not been checked.",
        "After export, inspect the HDF5 handoff before handing the ASCII to DONJON.",
    ]
    if request["workflow"] == "one-step":
        actions.append("Use the generated run directory as the production handoff bundle.")
    if request["equivalence"] == "direct":
        actions.append("Direct mode has no ADF/SPH correction; expect homogenization bias.")
    elif request["workflow"] == "two-step" and request["equivalence"] in {"adf", "sph"}:
        actions.append("Inspect the augmented HDF5 before conversion; it is the object DONJON will see.")
    elif request["workflow"] == "two-step" and request["equivalence"] == "flux-ratio-adf":
        actions.append(
            "Switch to one-step for flux-ratio ADF, or build an ADF sidecar first "
            "and use two-step ADF."
        )
    return actions


def _workflow_label(workflow: str) -> str:
    return "One-step export + convert" if workflow == "one-step" else "Two-step export then convert"


def _default_output(output_format: str) -> str:
    return "out.macrolib.txt" if output_format == "macrolib" else "out.mcompo.txt"


def _default_hdf5(request: dict[str, Any]) -> str:
    keep = str(request["keep_hdf5_path"]).strip()
    if keep:
        return keep
    run_dir = str(request["run_dir"]).strip().rstrip("/")
    if run_dir:
        return f"{run_dir}/mgxs_library.h5"
    return "mgxs_library.h5"


def _augmented_hdf5(request: dict[str, Any], kind: str) -> str:
    base = _default_hdf5(request)
    path = Path(base)
    suffix = "".join(path.suffixes)
    stem = path.name[: -len(suffix)] if suffix else path.name
    name = f"{stem}_{kind}{suffix or '.h5'}"
    if str(path.parent) in ("", "."):
        return name
    return str(path.parent / name)


def _choice(value: Any, allowed: set[str], name: str, http_exception: Any) -> str:
    text = str(value)
    if text not in allowed:
        raise http_exception(
            status_code=422,
            detail=f"{name} must be one of: {', '.join(sorted(allowed))}",
        )
    return text


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _optional_number(value: Any, http_exception: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise http_exception(status_code=422, detail="h_factor_default must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise http_exception(status_code=422, detail="h_factor_default must be numeric") from exc
