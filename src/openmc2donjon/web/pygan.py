"""PyGan diagnostics and writer-comparison routes for the localhost web UI."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from ..multicompo import DEFAULT_ROOT_NAME
from ..pygan_backend import probe_pygan
from ..writer_compare import (
    WriterComparisonReport,
    compare_writer_backends,
)
from .filesystem import FilesystemScope


PYGAN_COMPARE_WEB_SCHEMA = "openmc2donjon.web-pygan-compare.v1"


def register_pygan_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope | None = None,
) -> None:
    """Register read-only PyGan diagnostics and compare-writer endpoints."""

    from fastapi import Body, HTTPException

    scope = filesystem_scope or FilesystemScope()
    compare_body = Body(...)

    @app.get("/api/pygan/doctor")
    @app.get("/api/pygan-doctor")
    def api_pygan_doctor() -> dict[str, Any]:
        payload = probe_pygan().as_dict()
        payload["schema"] = "openmc2donjon.pygan-doctor.v1"
        payload["mock_mode"] = mock_mode
        return payload

    @app.post("/api/pygan/compare-writers")
    def api_pygan_compare_writers(payload: dict[str, Any] = compare_body) -> dict[str, Any]:
        request = _normalize_compare_request(payload, HTTPException)
        if mock_mode:
            return _compare_response(
                _mock_compare_report(request),
                request=request,
                mock_mode=True,
            )
        request = _apply_filesystem_scope(request, HTTPException, scope)
        try:
            report = compare_writer_backends(
                request["input_h5"],
                output_format=request["format"],
                root_name=request["root_name"],
                comment=request["comment"],
                burnup=request["burnup"],
                h_factor_default=request["h_factor_default"],
                mixture_names=request["mixtures"],
                rtol=request["rtol"],
                atol=request["atol"],
                summary_json=request["summary_json"],
                keep_dir=request["keep_dir"],
            )
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"writer comparison failed: {exc}",
            ) from exc
        return _compare_response(report, request=request, mock_mode=False)


def _normalize_compare_request(payload: dict[str, Any], http_exception: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise http_exception(status_code=422, detail="request body must be an object")
    output_format = str(payload.get("format", "multicompo"))
    if output_format not in {"multicompo", "macrolib"}:
        raise http_exception(status_code=422, detail="format must be 'multicompo' or 'macrolib'")
    return {
        "input_h5": _required_string(payload, "input_h5", http_exception),
        "format": output_format,
        "root_name": _optional_string(payload, "root_name", default=DEFAULT_ROOT_NAME),
        "comment": _optional_nullable_string(payload, "comment", http_exception),
        "burnup": _optional_nullable_float(payload, "burnup", http_exception),
        "h_factor_default": _optional_nullable_float(payload, "h_factor_default", http_exception),
        "mixtures": _optional_mixture_list(payload.get("mixtures"), http_exception),
        "rtol": _optional_float(payload, "rtol", default=1.0e-6, http_exception=http_exception),
        "atol": _optional_float(payload, "atol", default=1.0e-8, http_exception=http_exception),
        "summary_json": _optional_path_string(payload, "summary_json", http_exception),
        "keep_dir": _optional_path_string(payload, "keep_dir", http_exception),
    }


def _compare_response(
    report: WriterComparisonReport,
    *,
    request: dict[str, Any],
    mock_mode: bool,
) -> dict[str, Any]:
    payload = report.as_dict()
    payload["web_schema"] = PYGAN_COMPARE_WEB_SCHEMA
    payload["mock_mode"] = mock_mode
    payload["cli_command"] = _compare_cli_command(request)
    payload["cli_command_text"] = " ".join(shlex.quote(part) for part in payload["cli_command"])
    payload["summary_json"] = request["summary_json"]
    payload["keep_dir"] = request["keep_dir"]
    return payload


def _mock_compare_report(request: dict[str, Any]) -> WriterComparisonReport:
    return WriterComparisonReport(
        input_h5=str(Path(request["input_h5"])),
        output_format=request["format"],
        ok=True,
        rtol=request["rtol"],
        atol=request["atol"],
        compared_payloads=312,
        compared_real_payloads=86,
        max_abs_diff=2.4e-12,
        max_rel_diff=4.1e-11,
        issues=(),
    )


def _compare_cli_command(request: dict[str, Any]) -> list[str]:
    command = [
        "openmc2donjon",
        "compare-writers",
        request["input_h5"],
        "--format",
        request["format"],
    ]
    _append_optional(command, "--root-name", request["root_name"], skip_value=DEFAULT_ROOT_NAME)
    _append_optional(command, "--comment", request["comment"])
    _append_optional(command, "--burnup", request["burnup"])
    _append_optional(command, "--h-factor-default", request["h_factor_default"])
    for mixture in request["mixtures"] or []:
        command.extend(["--mixture", str(mixture)])
    _append_optional(command, "--rtol", request["rtol"], skip_value=1.0e-6)
    _append_optional(command, "--atol", request["atol"], skip_value=1.0e-8)
    _append_optional(command, "--summary-json", request["summary_json"])
    _append_optional(command, "--keep-dir", request["keep_dir"])
    return [str(part) for part in command]


def _append_optional(
    command: list[Any],
    flag: str,
    value: object,
    *,
    skip_value: object | None = None,
) -> None:
    if value is None or value == "":
        return
    if skip_value is not None and value == skip_value:
        return
    command.extend([flag, value])


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


def _optional_nullable_string(payload: dict[str, Any], key: str, http_exception: Any) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise http_exception(status_code=422, detail=f"{key} must be a string or null")
    stripped = value.strip()
    return stripped or None


def _optional_path_string(payload: dict[str, Any], key: str, http_exception: Any) -> str | None:
    raw = _optional_nullable_string(payload, key, http_exception)
    return str(Path(raw).expanduser()) if raw else None


def _optional_float(payload: dict[str, Any], key: str, *, default: float, http_exception: Any) -> float:
    value = payload.get(key, default)
    if value == "":
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise http_exception(status_code=422, detail=f"{key} must be a number")
    return float(value)


def _optional_nullable_float(payload: dict[str, Any], key: str, http_exception: Any) -> float | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise http_exception(status_code=422, detail=f"{key} must be a number or null")
    return float(value)


def _optional_mixture_list(value: Any, http_exception: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return [item.strip() for item in value]
    raise http_exception(status_code=422, detail="mixtures must be a list of non-empty strings or null")


def _apply_filesystem_scope(
    request: dict[str, Any],
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any]:
    if filesystem_scope.root is None:
        return request
    scoped = dict(request)
    scoped["input_h5"] = str(filesystem_scope.resolve(str(scoped["input_h5"]), http_exception))
    for key in ("summary_json", "keep_dir"):
        value = scoped.get(key)
        if value is not None:
            scoped[key] = str(filesystem_scope.resolve(str(value), http_exception))
    return scoped
