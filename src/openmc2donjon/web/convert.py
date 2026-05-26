"""Direct-conversion API routes for the localhost web UI.

The web surface intentionally calls the converter library functions
directly instead of wrapping a shell command. The response still
includes the equivalent CLI command so users can take the exact same
workflow back to a terminal or batch script.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shlex
import tempfile
from typing import Any

from ..macrolib import convert_mgxs_hdf5_to_macrolib
from ..mgxs_input_contract import run_preflight
from ..multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5


CONVERT_SCHEMA = "openmc2donjon.convert.v1"


def register_convert_routes(app: Any, *, mock_mode: bool) -> None:
    """Register direct-conversion endpoints on a FastAPI app."""

    from fastapi import Body, HTTPException

    convert_body = Body(...)

    @app.post("/api/convert")
    def api_convert(payload: dict[str, Any] = convert_body) -> dict[str, Any]:
        request = _normalize_convert_request(payload, HTTPException)
        if mock_mode:
            return _mock_convert_response(request)

        input_path = _validate_hdf5_path(str(request["input_path"]), HTTPException)
        output_path = _resolve_convert_output_path(
            request["output_path"],
            input_path=input_path,
            output_format=str(request["format"]),
            http_exception=HTTPException,
        )
        _validate_convert_output_path(
            input_path,
            output_path,
            overwrite=bool(request["overwrite"]),
            dry_run=bool(request["dry_run"]),
            http_exception=HTTPException,
        )

        preflight = None
        preflight_ok = True
        if bool(request["check"]) or bool(request["production"]):
            preflight, preflight_ok = _run_convert_preflight(
                input_path,
                output_path,
                request,
            )

        converted = False
        output_size = output_path.stat().st_size if output_path.exists() else None
        if preflight_ok and not bool(request["dry_run"]):
            try:
                _run_converter(input_path, output_path, request)
            except (OSError, ValueError, KeyError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"conversion failed: {exc}",
                ) from exc
            converted = True
            output_size = output_path.stat().st_size

        return _convert_response(
            request,
            input_path=input_path,
            output_path=output_path,
            preflight=preflight,
            preflight_ok=preflight_ok,
            converted=converted,
            output_size=output_size,
        )


def _validate_hdf5_path(raw: str, http_exception: Any) -> Path:
    """Resolve a user-supplied path and confirm it is a readable HDF5 file."""

    import h5py

    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    try:
        is_hdf5 = h5py.is_hdf5(str(real))
    except OSError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read path: {exc}"
        ) from exc
    if not is_hdf5:
        raise http_exception(status_code=400, detail=f"not an HDF5 file: {raw}")
    return real


def _normalize_convert_request(
    payload: dict[str, Any],
    http_exception: Any,
) -> dict[str, Any]:
    """Validate and normalize the web direct-conversion request."""

    if not isinstance(payload, dict):
        raise http_exception(status_code=422, detail="request body must be an object")
    input_path = _required_string(payload, "input_path", http_exception)
    output_format = str(payload.get("format", "multicompo"))
    if output_format not in {"multicompo", "macrolib"}:
        raise http_exception(
            status_code=422,
            detail="format must be 'multicompo' or 'macrolib'",
        )
    output_raw = payload.get("output_path")
    if output_raw is not None and not isinstance(output_raw, str):
        raise http_exception(status_code=422, detail="output_path must be a string")
    mixtures = _optional_mixture_list(payload.get("mixtures"), http_exception)
    return {
        "input_path": input_path,
        "output_path": output_raw.strip() if isinstance(output_raw, str) else None,
        "format": output_format,
        "dry_run": _optional_bool(
            payload,
            "dry_run",
            default=True,
            http_exception=http_exception,
        ),
        "overwrite": _optional_bool(
            payload,
            "overwrite",
            default=False,
            http_exception=http_exception,
        ),
        "check": _optional_bool(
            payload,
            "check",
            default=True,
            http_exception=http_exception,
        ),
        "production": _optional_bool(
            payload,
            "production",
            default=False,
            http_exception=http_exception,
        ),
        "warn_unknown_energy_mesh": _optional_bool(
            payload,
            "warn_unknown_energy_mesh",
            default=True,
            http_exception=http_exception,
        ),
        "require_known_energy_mesh": _optional_bool(
            payload,
            "require_known_energy_mesh",
            default=False,
            http_exception=http_exception,
        ),
        "root_name": _optional_string(payload, "root_name", default=DEFAULT_ROOT_NAME),
        "comment": _optional_nullable_string(payload, "comment", http_exception),
        "burnup": _optional_nullable_float(payload, "burnup", http_exception),
        "h_factor_default": _optional_nullable_float(
            payload,
            "h_factor_default",
            http_exception,
        ),
        "mixtures": mixtures,
    }


def _required_string(payload: dict[str, Any], key: str, http_exception: Any) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise http_exception(status_code=422, detail=f"{key} must be a non-empty string")
    return value.strip()


def _optional_string(payload: dict[str, Any], key: str, *, default: str) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip()


def _optional_nullable_string(
    payload: dict[str, Any],
    key: str,
    http_exception: Any,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise http_exception(status_code=422, detail=f"{key} must be a string or null")
    stripped = value.strip()
    return stripped or None


def _optional_bool(
    payload: dict[str, Any],
    key: str,
    *,
    default: bool,
    http_exception: Any,
) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise http_exception(status_code=422, detail=f"{key} must be a boolean")
    return bool(value)


def _optional_nullable_float(
    payload: dict[str, Any],
    key: str,
    http_exception: Any,
) -> float | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise http_exception(status_code=422, detail=f"{key} must be a number or null")
    return float(value)


def _optional_mixture_list(value: Any, http_exception: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    ):
        return [item.strip() for item in value]
    raise http_exception(
        status_code=422,
        detail="mixtures must be a list of non-empty strings",
    )


def _resolve_convert_output_path(
    raw: str | None,
    *,
    input_path: Path,
    output_format: str,
    http_exception: Any,
) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    extension = ".macrolib.txt" if output_format == "macrolib" else ".mcompo.txt"
    try:
        return input_path.with_suffix(extension)
    except ValueError as exc:
        raise http_exception(
            status_code=422,
            detail=f"cannot derive output path from {input_path}",
        ) from exc


def _validate_convert_output_path(
    input_path: Path,
    output_path: Path,
    *,
    overwrite: bool,
    dry_run: bool,
    http_exception: Any,
) -> None:
    if output_path == input_path:
        raise http_exception(status_code=400, detail="output path must differ from input")
    parent = output_path.parent
    if not parent.exists():
        raise http_exception(
            status_code=404,
            detail=f"output directory not found: {parent}",
        )
    if not parent.is_dir():
        raise http_exception(
            status_code=400,
            detail=f"output parent is not a directory: {parent}",
        )
    if output_path.exists() and not output_path.is_file():
        raise http_exception(
            status_code=400,
            detail=f"output path exists but is not a file: {output_path}",
        )
    if output_path.exists() and not overwrite and not dry_run:
        raise http_exception(
            status_code=409,
            detail=f"output already exists; enable overwrite to replace it: {output_path}",
        )


def _run_convert_preflight(
    input_path: Path,
    output_path: Path,
    request: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    with tempfile.TemporaryDirectory() as tmp:
        summary_path = Path(tmp) / "preflight.json"
        # ``run_preflight`` is the CLI implementation and prints a
        # human report by design. The web endpoint returns structured
        # JSON instead, so capture the stdout stream here.
        with contextlib.redirect_stdout(io.StringIO()):
            ok = run_preflight(
                [input_path],
                output_format=str(request["format"]),
                output_path=output_path,
                production=bool(request["production"]),
                require_known_energy_mesh=bool(request["require_known_energy_mesh"]),
                warn_unknown_energy_mesh=bool(request["warn_unknown_energy_mesh"]),
                summary_json=summary_path,
            )
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return payload, bool(ok)


def _run_converter(
    input_path: Path,
    output_path: Path,
    request: dict[str, Any],
) -> None:
    if request["format"] == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            input_path,
            output_path,
            h_factor_default=request["h_factor_default"],
            mixture_names=request["mixtures"],
        )
    else:
        convert_mgxs_hdf5(
            input_path,
            output_path,
            root_name=str(request["root_name"]),
            comment=request["comment"],
            burnup=request["burnup"],
            h_factor_default=request["h_factor_default"],
            mixture_names=request["mixtures"],
        )


def _convert_response(
    request: dict[str, Any],
    *,
    input_path: Path,
    output_path: Path,
    preflight: dict[str, Any] | None,
    preflight_ok: bool,
    converted: bool,
    output_size: int | None,
) -> dict[str, Any]:
    dry_run = bool(request["dry_run"])
    ok = bool(preflight_ok and (dry_run or converted))
    command = _convert_cli_command(request, input_path, output_path)
    return {
        "schema": CONVERT_SCHEMA,
        "ok": ok,
        "dry_run": dry_run,
        "converted": converted,
        "format": request["format"],
        "input_path": str(input_path),
        "output_path": str(output_path),
        "output_exists": output_path.exists(),
        "output_size": output_size,
        "preflight_ok": preflight_ok,
        "preflight": preflight,
        "cli_command": command,
        "cli_command_text": " ".join(shlex.quote(part) for part in command),
    }


def _convert_cli_command(
    request: dict[str, Any],
    input_path: Path,
    output_path: Path,
) -> list[str]:
    command = [
        "openmc2donjon",
        str(input_path),
        "--format",
        str(request["format"]),
        "-o",
        str(output_path),
    ]
    if request["format"] == "multicompo" and request["root_name"] != DEFAULT_ROOT_NAME:
        command.extend(["--root-name", str(request["root_name"])])
    if request["dry_run"]:
        command.append("--dry-run")
    if request["overwrite"]:
        command.append("--overwrite")
    if request["comment"] is not None:
        command.extend(["--comment", str(request["comment"])])
    if request["check"]:
        command.append("--check")
    if request["production"]:
        command.append("--production")
    preflight_requested = bool(request["check"]) or bool(request["production"])
    if preflight_requested and request["warn_unknown_energy_mesh"]:
        command.append("--warn-unknown-energy-mesh")
    if preflight_requested and request["require_known_energy_mesh"]:
        command.append("--require-known-energy-mesh")
    if request["h_factor_default"] is not None:
        command.extend(["--h-factor-default", str(request["h_factor_default"])])
    if request["burnup"] is not None:
        command.extend(["--burnup", str(request["burnup"])])
    for mixture in request["mixtures"] or []:
        command.extend(["--mixture", str(mixture)])
    return command


def _mock_convert_response(request: dict[str, Any]) -> dict[str, Any]:
    """Return a realistic direct-conversion payload in mock mode."""

    input_path = Path(str(request["input_path"]))
    output_path = Path(
        request["output_path"]
        or (
            "/mock/home/openmc-runs/c5g7/handoff.macrolib.txt"
            if request["format"] == "macrolib"
            else "/mock/home/openmc-runs/c5g7/handoff.mcompo.txt"
        )
    )
    preflight = {
        "schema": "openmc2donjon.mgxs-input-contract.v1",
        "decision": "mgxs_input_contract_passed",
        "output_issue": None,
        "inputs": [_mock_preflight_input(str(input_path))],
    }
    dry_run = bool(request["dry_run"])
    response = _convert_response(
        request,
        input_path=input_path,
        output_path=output_path,
        preflight=preflight,
        preflight_ok=True,
        converted=not dry_run,
        output_size=None if dry_run else 184_320,
    )
    response["output_exists"] = not dry_run
    return response


def _mock_preflight_input(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "ok": True,
        "energy_groups": 7,
        "legendre_order": 1,
        "energy_group_structure": "CASMO-7",
        "energy_bounds_sha256": "mock",
        "energy_mesh_id": "casmo_7",
        "energy_mesh_name": "CASMO-7",
        "energy_mesh_tolerance": 1.0e-6,
        "mixtures": 9,
        "calculations": 9,
        "state_points": 1,
        "fissionable_mixtures": 4,
        "adf_mixtures": 9,
        "adf_faces": ["XMIN", "XMAX", "YMIN", "YMAX"],
        "sph_calculations": 9,
        "scatter_row_balance": {
            "checked": True,
            "max_rel": 2.1e-3,
            "max_abs": 1.2e-4,
            "worst": "mixture=M3_MOX_70 group=4",
        },
        "physics_checks": {
            "chi_checked": 4,
            "chi_sum_max_abs_error": 1.0e-12,
            "nu_ratio_warning_count": 0,
            "transport_p1_checked": 0,
        },
        "uncertainty": {
            "checked": True,
            "expected_datasets": 72,
            "datasets": 72,
            "missing_datasets": 0,
            "max_rel": 1.9e-2,
        },
        "issues": [],
        "warnings": [],
    }
