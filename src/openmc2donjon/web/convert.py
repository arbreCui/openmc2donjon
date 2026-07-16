"""Direct-conversion API routes for the localhost web UI.

The web surface intentionally calls the converter library functions
directly instead of wrapping a shell command. The response still
includes the equivalent CLI command so users can take the exact same
workflow back to a terminal or batch script.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shlex
import tempfile
from typing import Any

from ..macrolib import convert_mgxs_hdf5_to_macrolib
from ..mgxs_input_contract import run_preflight
from ..multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from ..pygan_writer import convert_mgxs_hdf5_with_pygan
from ..physical_sph_contract import physical_sph_issues
from ..production_policy import (
    effective_production_thresholds,
    production_preflight_policy_payload,
)
from .files import _mock_file_status, record_mock_written_file
from .filesystem import FilesystemScope
from .text_preview import _is_mock_openmc_sph_path, _mock_ascii_preview_text


CONVERT_SCHEMA = "openmc2donjon.convert.v1"


def register_convert_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope | None = None,
) -> None:
    """Register direct-conversion endpoints on a FastAPI app."""

    from fastapi import Body, HTTPException

    scope = filesystem_scope or FilesystemScope()
    convert_body = Body(...)

    @app.post("/api/convert")
    def api_convert(payload: dict[str, Any] = convert_body) -> dict[str, Any]:
        request = _normalize_convert_request(payload, HTTPException)
        if mock_mode:
            return _mock_convert_response(request)

        input_path = _validate_hdf5_path(
            str(request["input_path"]),
            HTTPException,
            scope,
        )
        if bool(request["require_physical_sph"]):
            sph_issues = physical_sph_issues(input_path)
            if sph_issues:
                raise HTTPException(
                    status_code=422,
                    detail="physical SPH gate failed: " + "; ".join(sph_issues),
                )
        output_path = _resolve_convert_output_path(
            request["output_path"],
            input_path=input_path,
            output_format=str(request["format"]),
            http_exception=HTTPException,
            filesystem_scope=scope,
        )
        _validate_convert_output_path(
            input_path,
            output_path,
            overwrite=bool(request["overwrite"]),
            dry_run=bool(request["dry_run"]),
            http_exception=HTTPException,
        )
        summary_path = _convert_summary_path(output_path)
        _validate_convert_summary_path(summary_path, output_path, HTTPException)

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
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"conversion failed: {exc}",
                ) from exc
            converted = True
            output_size = output_path.stat().st_size

        response = _convert_response(
            request,
            input_path=input_path,
            output_path=output_path,
            summary_path=summary_path,
            summary_written=False,
            preflight=preflight,
            preflight_ok=preflight_ok,
            converted=converted,
            output_size=output_size,
        )
        if converted:
            response["summary_written"] = True
            try:
                _write_convert_summary(summary_path, response)
            except OSError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"conversion summary write failed: {exc}",
                ) from exc
        return response


def _validate_hdf5_path(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> Path:
    """Resolve a user-supplied path and confirm it is a readable HDF5 file."""

    import h5py

    real = filesystem_scope.resolve(raw, http_exception)
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
    writer_backend = str(payload.get("writer_backend", "ascii"))
    if writer_backend not in {"ascii", "pygan"}:
        raise http_exception(
            status_code=422,
            detail="writer_backend must be 'ascii' or 'pygan'",
        )
    output_raw = payload.get("output_path")
    if output_raw is not None and not isinstance(output_raw, str):
        raise http_exception(status_code=422, detail="output_path must be a string")
    mixtures = _optional_mixture_list(payload.get("mixtures"), http_exception)
    request = {
        "input_path": input_path,
        "output_path": output_raw.strip() if isinstance(output_raw, str) else None,
        "format": output_format,
        "writer_backend": writer_backend,
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
        "require_physical_sph": _optional_bool(
            payload,
            "require_physical_sph",
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
        "scatter_row_balance_fail": _optional_nullable_float(
            payload,
            "scatter_row_balance_fail",
            http_exception,
        ),
        "transport_p1_fail": _optional_nullable_float(
            payload,
            "transport_p1_fail",
            http_exception,
        ),
        "chi_sum_tolerance": _optional_nullable_float(
            payload,
            "chi_sum_tolerance",
            http_exception,
        ),
        "uncertainty_warn": _optional_float(
            payload,
            "uncertainty_warn",
            default=5.0e-2,
            http_exception=http_exception,
        ),
        "uncertainty_fail": _optional_nullable_float(
            payload,
            "uncertainty_fail",
            http_exception,
        ),
        "uncertainty_production_fail": _optional_nullable_float(
            payload,
            "uncertainty_production_fail",
            http_exception,
        ),
        "uncertainty_mean_abs_floor": _optional_float(
            payload,
            "uncertainty_mean_abs_floor",
            default=1.0e-12,
            http_exception=http_exception,
        ),
        "no_uncertainty_check": _optional_bool(
            payload,
            "no_uncertainty_check",
            default=False,
            http_exception=http_exception,
        ),
        "require_std_dev_coverage": _optional_bool(
            payload,
            "require_std_dev_coverage",
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
        "project_root": _optional_nullable_string(payload, "project_root", http_exception),
        "component_id": _optional_nullable_string(payload, "component_id", http_exception),
    }
    if request["production"] and request["no_uncertainty_check"]:
        raise http_exception(
            status_code=422,
            detail=(
                "production cannot disable uncertainty checks; the canonical "
                "production policy requires uncertainty checks and complete "
                "std-dev coverage"
            ),
        )
    if request["production"] and request["h_factor_default"] is not None:
        raise http_exception(
            status_code=422,
            detail=(
                "production cannot use h_factor_default; export the physical "
                "group-wise H-FACTOR / kappa-fission data in the input HDF5"
            ),
        )
    return request


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


def _optional_float(
    payload: dict[str, Any],
    key: str,
    *,
    default: float,
    http_exception: Any,
) -> float:
    if key not in payload:
        return default
    value = _optional_nullable_float(payload, key, http_exception)
    if value is None:
        raise http_exception(status_code=422, detail=f"{key} must be a number")
    return value


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
    filesystem_scope: FilesystemScope,
) -> Path:
    if raw:
        return filesystem_scope.resolve(raw, http_exception)
    extension = ".macrolib.txt" if output_format == "macrolib" else ".mcompo.txt"
    try:
        return filesystem_scope.enforce(input_path.with_suffix(extension), http_exception)
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


def _convert_summary_path(output_path: Path) -> Path:
    # A project writes several component CPOs into the same directory.  The
    # receipt must be output-specific or each conversion would overwrite the
    # preceding component's provenance.
    return output_path.with_name(f"{output_path.name}.convert.json")


def _validate_convert_summary_path(
    summary_path: Path,
    output_path: Path,
    http_exception: Any,
) -> None:
    if summary_path == output_path:
        raise http_exception(
            status_code=400,
            detail="output filename must not be convert_summary.json",
        )
    if summary_path.exists() and not summary_path.is_file():
        raise http_exception(
            status_code=400,
            detail=f"conversion summary path exists but is not a file: {summary_path}",
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
                scatter_row_balance_fail=request["scatter_row_balance_fail"],
                transport_p1_fail=request["transport_p1_fail"],
                chi_sum_tolerance=request["chi_sum_tolerance"],
                uncertainty_warn=(
                    None
                    if request["no_uncertainty_check"]
                    else request["uncertainty_warn"]
                ),
                uncertainty_fail=(
                    None
                    if request["no_uncertainty_check"]
                    else request["uncertainty_fail"]
                ),
                uncertainty_production_fail=(
                    None
                    if request["no_uncertainty_check"]
                    else request["uncertainty_production_fail"]
                ),
                uncertainty_mean_abs_floor=request["uncertainty_mean_abs_floor"],
                require_std_dev_coverage=(
                    False
                    if request["no_uncertainty_check"]
                    else bool(request["require_std_dev_coverage"])
                ),
                summary_json=summary_path,
            )
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return payload, bool(ok)


def _run_converter(
    input_path: Path,
    output_path: Path,
    request: dict[str, Any],
) -> None:
    if request["writer_backend"] == "pygan":
        convert_mgxs_hdf5_with_pygan(
            input_path,
            output_path,
            output_format=str(request["format"]),
            root_name=str(request["root_name"]),
            comment=request["comment"],
            burnup=request["burnup"],
            h_factor_default=request["h_factor_default"],
            mixture_names=request["mixtures"],
        )
    elif request["format"] == "macrolib":
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
    summary_path: Path,
    summary_written: bool,
    preflight: dict[str, Any] | None,
    preflight_ok: bool,
    converted: bool,
    output_size: int | None,
) -> dict[str, Any]:
    dry_run = bool(request["dry_run"])
    production_requested = bool(request["production"])
    preflight_executed = bool(request["check"]) or production_requested
    ok = bool(preflight_ok and (dry_run or converted))
    command = _convert_cli_command(request, input_path, output_path)
    preflight_inputs = (
        preflight.get("inputs") if isinstance(preflight, dict) else None
    )
    first_input = (
        preflight_inputs[0]
        if isinstance(preflight_inputs, list)
        and preflight_inputs
        and isinstance(preflight_inputs[0], dict)
        else {}
    )
    return {
        "schema": CONVERT_SCHEMA,
        "ok": ok,
        "dry_run": dry_run,
        "converted": converted,
        "format": request["format"],
        "writer_backend": request["writer_backend"],
        "root_name": request["root_name"],
        "comment": request["comment"],
        "burnup": request["burnup"],
        "h_factor_default": request["h_factor_default"],
        "mixtures": request["mixtures"],
        "project_root": request["project_root"],
        "component_id": request["component_id"],
        "physical_sph_required": bool(request["require_physical_sph"]),
        "production_requested": production_requested,
        "preflight_policy": production_preflight_policy_payload(
            production_requested=production_requested,
            preflight_executed=preflight_executed,
            thresholds=_web_production_thresholds(request),
        ),
        "input_path": str(input_path),
        "input_sha256": _file_sha256(input_path),
        "openmc_provenance": first_input.get("openmc_provenance"),
        "output_path": str(output_path),
        "output_sha256": _file_sha256(output_path) if converted else None,
        "summary_path": str(summary_path),
        "summary_written": summary_written,
        "output_exists": output_path.exists(),
        "output_size": output_size,
        "preflight_ok": preflight_ok,
        "preflight": preflight,
        "cli_command": command,
        "cli_command_text": " ".join(shlex.quote(part) for part in command),
    }


def _web_production_thresholds(request: dict[str, Any]) -> dict[str, float] | None:
    if not request["production"]:
        return None
    return effective_production_thresholds(
        scatter_row_balance_fail=request["scatter_row_balance_fail"],
        transport_p1_fail=request["transport_p1_fail"],
        chi_sum_tolerance=request["chi_sum_tolerance"],
        uncertainty_warn=request["uncertainty_warn"],
        uncertainty_fail=request["uncertainty_fail"],
        uncertainty_production_fail=request["uncertainty_production_fail"],
        uncertainty_mean_abs_floor=request["uncertainty_mean_abs_floor"],
    )


def _convert_cli_command(
    request: dict[str, Any],
    input_path: Path,
    output_path: Path,
) -> list[str]:
    summary_path = _convert_summary_path(output_path)
    command = [
        "openmc2donjon",
        str(input_path),
        "--format",
        str(request["format"]),
        "-o",
        str(output_path),
    ]
    if request["writer_backend"] == "pygan":
        command.extend(["--writer-backend", "pygan"])
    if request["format"] == "multicompo" and request["root_name"] != DEFAULT_ROOT_NAME:
        command.extend(["--root-name", str(request["root_name"])])
    if request["dry_run"]:
        command.append("--dry-run")
    if request["overwrite"]:
        command.append("--overwrite")
    if not request["dry_run"]:
        command.extend(["--summary-json", str(summary_path)])
    if request["comment"] is not None:
        command.extend(["--comment", str(request["comment"])])
    if request["check"]:
        command.append("--check")
    if request["production"]:
        command.append("--production")
    if request["require_physical_sph"]:
        command.append("--require-physical-sph")
    preflight_requested = bool(request["check"]) or bool(request["production"])
    if preflight_requested and request["warn_unknown_energy_mesh"]:
        command.append("--warn-unknown-energy-mesh")
    if preflight_requested and request["require_known_energy_mesh"]:
        command.append("--require-known-energy-mesh")
    if preflight_requested:
        for key in (
            "scatter_row_balance_fail",
            "transport_p1_fail",
            "chi_sum_tolerance",
            "uncertainty_fail",
            "uncertainty_production_fail",
        ):
            value = request[key]
            if value is not None:
                command.extend([f"--{key.replace('_', '-')}", str(value)])
        if request["uncertainty_warn"] != 5.0e-2:
            command.extend(["--uncertainty-warn", str(request["uncertainty_warn"])])
        if request["uncertainty_mean_abs_floor"] != 1.0e-12:
            command.extend(
                [
                    "--uncertainty-mean-abs-floor",
                    str(request["uncertainty_mean_abs_floor"]),
                ]
            )
        if request["no_uncertainty_check"]:
            command.append("--no-uncertainty-check")
        if request["require_std_dev_coverage"]:
            command.append("--require-std-dev-coverage")
    if request["h_factor_default"] is not None:
        command.extend(["--h-factor-default", str(request["h_factor_default"])])
    if request["burnup"] is not None:
        command.extend(["--burnup", str(request["burnup"])])
    for mixture in request["mixtures"] or []:
        command.extend(["--mixture", str(mixture)])
    return command


def _mock_convert_response(request: dict[str, Any]) -> dict[str, Any]:
    """Return a realistic direct-conversion payload in mock mode.

    Mock conversions "write" into the in-memory mock filesystem: the
    default output path is derived from the input path exactly like
    live mode, non-dry runs register the output (and summary) with the
    mock file browser / file-status probe, and the reported size equals
    the text ``/api/text-preview`` serves for the same path — so the
    UI's existence probes can never contradict this response.
    """

    input_path = Path(str(request["input_path"]))
    extension = ".macrolib.txt" if request["format"] == "macrolib" else ".mcompo.txt"
    output_path = Path(request["output_path"] or input_path.with_suffix(extension))
    summary_path = _convert_summary_path(output_path)
    dry_run = bool(request["dry_run"])
    if not dry_run:
        text = _mock_ascii_preview_text(str(output_path))
        record_mock_written_file(str(output_path), len(text.encode("utf-8")))
    status = _mock_file_status(str(output_path))
    preflight_input = _mock_preflight_input(str(input_path))
    thresholds = _web_production_thresholds(request)
    if thresholds is not None:
        _apply_mock_production_thresholds(preflight_input, thresholds)
    preflight = {
        "schema": "openmc2donjon.mgxs-input-contract.v1",
        "decision": "mgxs_input_contract_passed",
        "output_issue": None,
        "inputs": [preflight_input],
    }
    response = _convert_response(
        request,
        input_path=input_path,
        output_path=output_path,
        summary_path=summary_path,
        summary_written=not dry_run,
        preflight=preflight,
        preflight_ok=True,
        converted=not dry_run,
        output_size=status["size"],
    )
    response["output_exists"] = bool(status["exists"] and status["kind"] == "file")
    if not dry_run:
        # Same bytes ``_write_convert_summary`` would produce for this
        # response, so the summary's probed size is honest too.
        summary_text = json.dumps(response, indent=2, sort_keys=True) + "\n"
        record_mock_written_file(
            str(summary_path), len(summary_text.encode("utf-8"))
        )
    return response


def _apply_mock_production_thresholds(
    preflight_input: dict[str, Any],
    thresholds: dict[str, float],
) -> None:
    preflight_input["scatter_row_balance"]["fail_threshold"] = thresholds[
        "scatter_row_balance_fail"
    ]
    physics = preflight_input["physics_checks"]
    physics["chi_sum_tolerance"] = thresholds["chi_sum_tolerance"]
    physics["transport_p1_fail_threshold"] = thresholds["transport_p1_fail"]
    uncertainty = preflight_input["uncertainty"]
    uncertainty.update(
        {
            "checked": True,
            "warn_threshold": thresholds["uncertainty_warn"],
            "fail_threshold": thresholds["uncertainty_fail"],
            "production_fail_threshold": thresholds[
                "uncertainty_production_fail"
            ],
            "mean_abs_floor": thresholds["uncertainty_mean_abs_floor"],
            "require_coverage": True,
        }
    )


def _write_convert_summary(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mock_preflight_input(path: str) -> dict[str, Any]:
    if _is_mock_openmc_sph_path(path):
        return _mock_openmc_sph_preflight_input(path)
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


def _mock_openmc_sph_preflight_input(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "ok": True,
        "energy_groups": 33,
        "legendre_order": 3,
        "energy_group_structure": "33-group OpenMC SPH minicase",
        "energy_bounds_sha256": "mock-openmc-sph-33g",
        "energy_mesh_id": None,
        "energy_mesh_name": "OpenMC SPH 33-group minicase",
        "energy_mesh_tolerance": 1.0e-6,
        "mixtures": 2,
        "calculations": 2,
        "state_points": 1,
        "fissionable_mixtures": 1,
        "adf_mixtures": 0,
        "adf_faces": [],
        "sph_calculations": 2,
        "scatter_row_balance": {
            "checked": True,
            "max_rel": 1.8e-3,
            "max_abs": 9.0e-5,
            "worst": "mixture=CS_FUEL group=12",
        },
        "physics_checks": {
            "chi_checked": 1,
            "chi_sum_max_abs_error": 1.0e-12,
            "nu_ratio_warning_count": 0,
            "transport_p1_checked": 2,
        },
        "uncertainty": {
            "checked": True,
            "expected_datasets": 24,
            "datasets": 24,
            "missing_datasets": 0,
            "max_rel": 4.13e-2,
        },
        "issues": [],
        "warnings": [],
    }
