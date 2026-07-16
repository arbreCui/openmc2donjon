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
from .files import _MOCK_TREE, _mock_list_dir, _resolve_mock_path
from .filesystem import FilesystemScope
from .text_preview import _is_mock_openmc_sph_path


BUNDLE_INSPECT_SCHEMA = "openmc2donjon.bundle-inspect.v1"
_MOCK_BUNDLE_MANIFEST = "/mock/home/openmc-runs/c5g7/bundle/manifest.json"
_MOCK_BUNDLE_DIR = "/mock/home/openmc-runs/c5g7/bundle"


class _ScopeViolation(Exception):
    def __init__(self, *args: object, **kwargs: object) -> None:
        detail = kwargs.get("detail")
        super().__init__(detail if isinstance(detail, str) else "path outside scope")


def register_bundle_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope | None = None,
) -> None:
    """Register read-only bundle manifest inspection endpoints."""

    from fastapi import HTTPException, Query

    scope = filesystem_scope or FilesystemScope()

    @app.get("/api/bundle/inspect")
    def api_bundle_inspect(manifest: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _mock_bundle_inspection(manifest, HTTPException)
        manifest_path = _validate_manifest_path(manifest, HTTPException, scope)
        _validate_manifest_artifact_paths(manifest_path, HTTPException, scope)
        try:
            return inspect_bundle_manifest(manifest_path, filesystem_scope=scope)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"bundle manifest inspect failed: {exc}",
            ) from exc


def inspect_bundle_manifest(
    manifest_path: Path,
    *,
    filesystem_scope: FilesystemScope | None = None,
) -> dict[str, Any]:
    """Inspect and validate a bundle manifest without writing any files."""

    scope = filesystem_scope or FilesystemScope()
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

    donjon_defaults = _donjon_defaults_from_artifacts(
        manifest_path,
        raw_artifacts,
        filesystem_scope=scope,
    )
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


def _validate_manifest_path(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> Path:
    real = filesystem_scope.resolve(raw, http_exception)
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    return real


def _validate_manifest_artifact_paths(
    manifest_path: Path,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> None:
    if filesystem_scope.root is None:
        return
    manifest_payload = _read_json_object(manifest_path)
    artifacts = manifest_payload.get("artifacts")
    if not isinstance(artifacts, list):
        return
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        filesystem_scope.enforce(_artifact_path(manifest_path, artifact), http_exception)


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("bundle manifest JSON root must be an object")
    return payload


def _mock_bundle_inspection(raw: str, http_exception: Any) -> dict[str, Any]:
    resolved = _resolve_mock_path(raw)
    if resolved == _MOCK_BUNDLE_MANIFEST:
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
                _mock_artifact(_MOCK_BUNDLE_DIR, "mgxs", "handoff.h5", 832_000),
                _mock_artifact(_MOCK_BUNDLE_DIR, "mcompo", "out.mcompo.txt", 184_320),
                _mock_artifact(
                    _MOCK_BUNDLE_DIR,
                    "conversion-summary",
                    "convert_summary.json",
                    8_192,
                ),
            ],
            "donjon_defaults": {
                "format": "multicompo",
                "ascii_path": f"{_MOCK_BUNDLE_DIR}/out.mcompo.txt",
                "mixture_count": 9,
                "summary_path": f"{_MOCK_BUNDLE_DIR}/convert_summary.json",
                "summary_schema": "openmc2donjon.convert.v1",
                "ok": True,
                "converted": True,
                "dry_run": False,
                "preflight_ok": True,
                "preflight_decision": "mgxs_input_contract_passed",
                "production_requested": True,
            },
        }
    # Any other <run_dir>/bundle/manifest.json is accepted as long as
    # the run directory exists in the mock tree; the manifest is
    # derived from that directory's contents (including artifacts
    # registered by mock convert) so the OpenMC-SPH minicase chain can
    # reach bundle validation instead of dead-ending on a 404.
    marker = "/bundle/manifest.json"
    if not resolved.endswith(marker) or resolved[: -len(marker)] not in _MOCK_TREE:
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    run_dir = resolved[: -len(marker)]
    return _mock_derived_bundle_inspection(run_dir, http_exception)


def _mock_derived_bundle_inspection(
    run_dir: str, http_exception: Any
) -> dict[str, Any]:
    bundle_dir = f"{run_dir}/bundle"
    listing = _mock_list_dir(run_dir, http_exception)
    files: list[tuple[str, int | None]] = [
        (entry["name"], entry["size"])
        for entry in listing["entries"]
        if entry["kind"] == "file"
    ]
    sizes = dict(files)

    h5_names = [name for name, _ in files if name.endswith(".h5")]
    mgxs_name = next(
        (name for name in h5_names if "mgxs" in name and "sph" in name),
        next((name for name in h5_names if "mgxs" in name), None),
    ) or (h5_names[0] if h5_names else None)
    ascii_name = next(
        (
            name
            for name, _ in files
            if name.endswith(".macrolib.txt") and "uncorrected" not in name
        ),
        next((name for name, _ in files if name.endswith(".mcompo.txt")), None),
    )
    ascii_format = None
    if ascii_name is not None:
        ascii_format = "macrolib" if ascii_name.endswith(".macrolib.txt") else "multicompo"
    summary_name = next(
        (name for name, _ in files if name == "convert_summary.json"), None
    )

    artifacts = []
    if mgxs_name is not None:
        artifacts.append(_mock_artifact(bundle_dir, "mgxs", mgxs_name, sizes[mgxs_name]))
    if ascii_name is not None:
        label = "macrolib" if ascii_format == "macrolib" else "mcompo"
        artifacts.append(_mock_artifact(bundle_dir, label, ascii_name, sizes[ascii_name]))
    if summary_name is not None:
        artifacts.append(
            _mock_artifact(
                bundle_dir, "conversion-summary", summary_name, sizes[summary_name]
            )
        )

    donjon_defaults = None
    if ascii_name is not None:
        donjon_defaults = {
            "format": ascii_format,
            "ascii_path": f"{bundle_dir}/{ascii_name}",
            "mixture_count": 2 if _is_mock_openmc_sph_path(run_dir) else 9,
            "summary_path": (
                f"{bundle_dir}/{summary_name}" if summary_name is not None else None
            ),
            "summary_schema": (
                "openmc2donjon.convert.v1" if summary_name is not None else None
            ),
            "ok": True,
            "converted": True,
            "dry_run": False,
            "preflight_ok": True,
            "preflight_decision": "mgxs_input_contract_passed",
            "production_requested": True,
        }
    return {
        "schema": BUNDLE_INSPECT_SCHEMA,
        "manifest_path": f"{bundle_dir}/manifest.json",
        "manifest_schema": BUNDLE_SCHEMA,
        "output_dir": bundle_dir,
        "package_version": __version__,
        "created_at_utc": "2026-05-26T00:00:00Z",
        "ok": True,
        "decision": VALIDATION_PASS_DECISION,
        "artifact_count": len(artifacts),
        "messages": [],
        "artifacts": artifacts,
        "donjon_defaults": donjon_defaults,
    }


def _mock_artifact(
    bundle_dir: str, label: str, bundled_path: str, size_bytes: int | None
) -> dict[str, Any]:
    return {
        "label": label,
        "path": f"{bundle_dir}/{bundled_path}",
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


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _donjon_defaults_from_artifacts(
    manifest_path: Path,
    artifacts: list[Any],
    *,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any] | None:
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_path = _artifact_path(manifest_path, artifact)
        payload = _read_optional_json_artifact(
            artifact_path,
            filesystem_scope=filesystem_scope,
        )
        if not _is_convert_summary(payload):
            continue
        return {
            "format": _donjon_format(payload.get("format")),
            "ascii_path": _string_or_none(payload.get("output_path")),
            "mixture_count": _summary_mixture_count(payload),
            "summary_path": str(artifact_path),
            "summary_schema": _string_or_none(payload.get("schema")),
            "ok": _bool_or_none(payload.get("ok")),
            "converted": _bool_or_none(payload.get("converted")),
            "dry_run": _bool_or_none(payload.get("dry_run")),
            "preflight_ok": _bool_or_none(payload.get("preflight_ok")),
            "preflight_decision": _preflight_decision(payload),
            "production_requested": _production_requested(payload),
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


def _read_optional_json_artifact(
    path: Path,
    *,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        real_path = filesystem_scope.enforce(path, _ScopeViolation)
    except _ScopeViolation:
        return None
    try:
        payload = json.loads(real_path.read_text(encoding="utf-8"))
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


def _preflight_decision(payload: dict[str, Any]) -> str | None:
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        return None
    return _string_or_none(preflight.get("decision"))


def _production_requested(payload: dict[str, Any]) -> bool | None:
    explicit = _bool_or_none(payload.get("production_requested"))
    if explicit is not None:
        return explicit
    command = payload.get("cli_command")
    if isinstance(command, list):
        return any(item == "--production" for item in command if isinstance(item, str))
    command_text = payload.get("cli_command_text")
    if isinstance(command_text, str):
        return "--production" in command_text.split()
    return None
