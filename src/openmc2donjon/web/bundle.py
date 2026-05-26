"""Read-only bundle inspection routes for the localhost web UI."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from .. import __version__
from ..bundle import SCHEMA as BUNDLE_SCHEMA
from ..bundle import VALIDATION_PASS_DECISION, validate_bundle


BUNDLE_INSPECT_SCHEMA = "openmc2donjon.bundle-inspect.v1"
_MOCK_BUNDLE_MANIFEST = "/mock/home/openmc-runs/c5g7/bundle/manifest.json"
_MOCK_BUNDLE_DIR = "/mock/home/openmc-runs/c5g7/bundle"


def register_bundle_routes(app: Any, *, mock_mode: bool) -> None:
    """Register read-only bundle manifest inspection endpoints."""

    from fastapi import HTTPException, Query

    @app.get("/api/bundle/inspect")
    def api_bundle_inspect(manifest: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _mock_bundle_inspection(manifest, HTTPException)
        manifest_path = _validate_manifest_path(manifest, HTTPException)
        try:
            return inspect_bundle_manifest(manifest_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"bundle manifest inspect failed: {exc}",
            ) from exc


def inspect_bundle_manifest(manifest_path: Path) -> dict[str, Any]:
    """Inspect and validate a bundle manifest without writing any files."""

    manifest_payload = _read_json_object(manifest_path)
    # ``validate_bundle`` is the authoritative checker, but it prints a
    # CLI report by design. Capture that result stream so the web server
    # stays diagnostic-only on stderr.
    with contextlib.redirect_stdout(io.StringIO()):
        report = validate_bundle(manifest_path)

    artifacts = manifest_payload.get("artifacts")
    raw_artifacts = artifacts if isinstance(artifacts, list) else []
    artifact_payloads = []
    for index, artifact in enumerate(report.artifacts):
        raw = raw_artifacts[index] if index < len(raw_artifacts) else {}
        if not isinstance(raw, dict):
            raw = {}
        artifact_payloads.append(
            {
                "label": artifact.label,
                "path": str(artifact.path),
                "bundled_path": _string_or_none(raw.get("bundled_path")),
                "ok": artifact.ok,
                "messages": list(artifact.messages),
                "size_bytes": _int_or_none(raw.get("size_bytes")),
                "sha256": _string_or_none(raw.get("sha256")),
                "summary_schema": artifact.summary_schema,
                "summary_decision": artifact.summary_decision,
                "acceptance_decision": artifact.acceptance_decision,
            }
        )

    donjon_defaults = _donjon_defaults_from_artifacts(manifest_path, raw_artifacts)
    return {
        "schema": BUNDLE_INSPECT_SCHEMA,
        "manifest_path": str(report.manifest_path),
        "manifest_schema": report.schema,
        "output_dir": _string_or_none(manifest_payload.get("output_dir")),
        "package_version": _string_or_none(manifest_payload.get("package_version")),
        "created_at_utc": _string_or_none(manifest_payload.get("created_at_utc")),
        "ok": report.ok,
        "decision": report.decision,
        "artifact_count": report.artifact_count,
        "messages": list(report.messages),
        "artifacts": artifact_payloads,
        "donjon_defaults": donjon_defaults,
    }


def _validate_manifest_path(raw: str, http_exception: Any) -> Path:
    real = Path(raw).expanduser().resolve()
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    return real


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("bundle manifest JSON root must be an object")
    return payload


def _mock_bundle_inspection(raw: str, http_exception: Any) -> dict[str, Any]:
    resolved = raw.rstrip("/")
    if resolved != _MOCK_BUNDLE_MANIFEST:
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    return {
        "schema": BUNDLE_INSPECT_SCHEMA,
        "manifest_path": _MOCK_BUNDLE_MANIFEST,
        "manifest_schema": BUNDLE_SCHEMA,
        "output_dir": _MOCK_BUNDLE_DIR,
        "package_version": __version__,
        "created_at_utc": "2026-05-26T00:00:00Z",
        "ok": True,
        "decision": VALIDATION_PASS_DECISION,
        "artifact_count": 3,
        "messages": [],
        "artifacts": [
            _mock_artifact("mgxs", "handoff.h5", 832_000),
            _mock_artifact("mcompo", "out.mcompo.txt", 184_320),
            _mock_artifact("conversion-summary", "convert_summary.json", 8_192),
        ],
        "donjon_defaults": {
            "format": "multicompo",
            "ascii_path": f"{_MOCK_BUNDLE_DIR}/out.mcompo.txt",
            "mixture_count": 9,
        },
    }


def _mock_artifact(label: str, bundled_path: str, size_bytes: int) -> dict[str, Any]:
    return {
        "label": label,
        "path": f"{_MOCK_BUNDLE_DIR}/{bundled_path}",
        "bundled_path": bundled_path,
        "ok": True,
        "messages": [],
        "size_bytes": size_bytes,
        "sha256": "0" * 64,
        "summary_schema": None,
        "summary_decision": None,
        "acceptance_decision": None,
    }


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _donjon_defaults_from_artifacts(
    manifest_path: Path,
    artifacts: list[Any],
) -> dict[str, Any] | None:
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        payload = _read_optional_json_artifact(_artifact_path(manifest_path, artifact))
        if not _is_convert_summary(payload):
            continue
        return {
            "format": _donjon_format(payload.get("format")),
            "ascii_path": _string_or_none(payload.get("output_path")),
            "mixture_count": _summary_mixture_count(payload),
        }
    return None


def _artifact_path(manifest_path: Path, artifact: dict[str, Any]) -> Path:
    bundled = artifact.get("bundled_path")
    if isinstance(bundled, str) and bundled:
        return manifest_path.parent / bundled
    raw = artifact.get("path")
    if isinstance(raw, str) and raw:
        return Path(raw)
    return manifest_path.parent / str(artifact.get("label") or "artifact")


def _read_optional_json_artifact(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _is_convert_summary(payload: dict[str, Any] | None) -> bool:
    return payload is not None and payload.get("schema") == "openmc2donjon.convert.v1"


def _donjon_format(value: Any) -> str | None:
    if value in {"multicompo", "macrolib"}:
        return str(value)
    return None


def _summary_mixture_count(payload: dict[str, Any]) -> int | None:
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        return None
    inputs = preflight.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return None
    first = inputs[0]
    if not isinstance(first, dict):
        return None
    mixtures = first.get("mixtures")
    if isinstance(mixtures, int) and not isinstance(mixtures, bool) and mixtures > 0:
        return mixtures
    return None
