"""Collect production handoff artifacts into a manifest-backed directory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import __version__


SCHEMA = "openmc2donjon.bundle.v1"
MANIFEST_NAME = "manifest.json"
VALIDATION_SCHEMA = "openmc2donjon.bundle-validation.v1"
VALIDATION_PASS_DECISION = "openmc2donjon_bundle_validation_passed"
VALIDATION_FAIL_DECISION = "openmc2donjon_bundle_validation_failed"


@dataclass(frozen=True)
class ArtifactSpec:
    label: str
    source: Path


@dataclass(frozen=True)
class BundleArtifactValidation:
    label: str
    path: Path
    ok: bool
    messages: tuple[str, ...]
    summary_schema: str | None = None
    summary_decision: str | None = None
    acceptance_decision: str | None = None


@dataclass(frozen=True)
class BundleValidationReport:
    manifest_path: Path
    schema: str | None
    ok: bool
    decision: str
    artifact_count: int
    artifacts: tuple[BundleArtifactValidation, ...]
    messages: tuple[str, ...]


def parse_extra_artifact(raw: str) -> ArtifactSpec:
    """Parse ``LABEL=PATH`` from the CLI."""

    if "=" not in raw:
        raise ValueError("expected LABEL=PATH")
    label, path = raw.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError("artifact label is empty")
    if not path:
        raise ValueError("artifact path is empty")
    return ArtifactSpec(label=label, source=Path(path))


def bundle_artifacts(
    *,
    output_dir: Path,
    artifacts: list[ArtifactSpec],
    manifest_name: str = MANIFEST_NAME,
    force: bool = False,
) -> dict[str, Any]:
    """Copy artifacts into ``output_dir`` and write a machine-readable manifest."""

    if not artifacts:
        raise ValueError("at least one artifact is required")
    _validate_manifest_name(manifest_name)
    output_dir = output_dir.expanduser()
    manifest_path = output_dir / manifest_name
    _validate_sources(artifacts)
    destinations = _plan_destinations(output_dir, artifacts)
    _validate_overwrite(artifacts, destinations, manifest_path, force=force)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_artifacts: list[dict[str, Any]] = []
    for artifact, destination in zip(artifacts, destinations, strict=True):
        if artifact.source.resolve() != destination.resolve():
            shutil.copy2(artifact.source, destination)
        manifest_artifacts.append(_artifact_manifest(artifact, destination))

    manifest = {
        "schema": SCHEMA,
        "package_version": __version__,
        "created_at_utc": _utc_now(),
        "output_dir": str(output_dir),
        "artifact_count": len(manifest_artifacts),
        "artifacts": manifest_artifacts,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print_report(manifest, manifest_path)
    return manifest


def validate_bundle(
    manifest_path: str | Path,
    *,
    summary_json: str | Path | None = None,
) -> BundleValidationReport:
    """Validate a manifest-backed handoff bundle."""

    manifest_file = Path(manifest_path).expanduser()
    manifest, messages = _load_manifest_for_validation(manifest_file)
    artifact_reports: list[BundleArtifactValidation] = []
    schema = manifest.get("schema") if isinstance(manifest, dict) else None
    artifacts = manifest.get("artifacts", []) if isinstance(manifest, dict) else []

    if schema != SCHEMA:
        messages.append(f"manifest schema mismatch: expected {SCHEMA}, got {schema!r}")
    if not isinstance(artifacts, list):
        messages.append("manifest artifacts must be a list")
        artifacts = []

    expected_count = manifest.get("artifact_count") if isinstance(manifest, dict) else None
    if expected_count is not None and expected_count != len(artifacts):
        messages.append(
            f"artifact_count mismatch: manifest={expected_count} actual={len(artifacts)}"
        )

    for index, artifact in enumerate(artifacts):
        if isinstance(artifact, dict):
            artifact_reports.append(_validate_artifact(manifest_file, artifact))
        else:
            artifact_reports.append(
                BundleArtifactValidation(
                    label=f"artifact[{index}]",
                    path=manifest_file.parent,
                    ok=False,
                    messages=("artifact entry is not a JSON object",),
                )
            )

    ok = not messages and all(report.ok for report in artifact_reports)
    decision = VALIDATION_PASS_DECISION if ok else VALIDATION_FAIL_DECISION
    report = BundleValidationReport(
        manifest_path=manifest_file,
        schema=schema,
        ok=ok,
        decision=decision,
        artifact_count=len(artifact_reports),
        artifacts=tuple(artifact_reports),
        messages=tuple(messages),
    )
    if summary_json is not None:
        _write_validation_summary(Path(summary_json), report)
    print_validation_report(report)
    return report


def print_report(manifest: dict[str, Any], manifest_path: Path) -> None:
    print("OpenMC-to-DONJON bundle")
    print(f"  schema: {SCHEMA}")
    print(f"  output_dir: {manifest['output_dir']}")
    print(f"  manifest: {manifest_path}")
    print()
    for artifact in manifest["artifacts"]:
        summary = ""
        if artifact.get("summary_schema") is not None:
            summary = f" schema={artifact['summary_schema']}"
        if artifact.get("summary_decision") is not None:
            summary += f" decision={artifact['summary_decision']}"
        if artifact.get("acceptance_decision") is not None:
            summary += f" acceptance={artifact['acceptance_decision']}"
        print(
            f"  {artifact['label']}: {artifact['bundled_path']} "
            f"size={artifact['size_bytes']} sha256={artifact['sha256'][:12]}{summary}"
        )


def print_validation_report(report: BundleValidationReport) -> None:
    print("OpenMC-to-DONJON bundle validation")
    print(f"  schema: {VALIDATION_SCHEMA}")
    print(f"  manifest: {report.manifest_path}")
    print(f"  bundle_schema: {report.schema}")
    print(f"  artifacts: {report.artifact_count}")
    print()
    for message in report.messages:
        print(f"  FAIL manifest: {message}")
    for artifact in report.artifacts:
        status = "PASS" if artifact.ok else "FAIL"
        summary = ""
        if artifact.summary_decision is not None:
            summary += f" decision={artifact.summary_decision}"
        if artifact.acceptance_decision is not None:
            summary += f" acceptance={artifact.acceptance_decision}"
        print(f"  {status} {artifact.label}: {artifact.path}{summary}")
        for message in artifact.messages:
            if not message.startswith("ok:"):
                print(f"    - {message}")
    print()
    print("Bundle validation decision")
    print(f"  {report.decision}")


def _validate_manifest_name(name: str) -> None:
    if not name or Path(name).name != name:
        raise ValueError("manifest name must be a filename, not a path")


def _validate_sources(artifacts: list[ArtifactSpec]) -> None:
    labels: set[str] = set()
    for artifact in artifacts:
        if artifact.label in labels:
            raise ValueError(f"duplicate artifact label: {artifact.label}")
        labels.add(artifact.label)
        if not artifact.source.exists():
            raise FileNotFoundError(f"{artifact.label}: source does not exist: {artifact.source}")
        if not artifact.source.is_file():
            raise ValueError(f"{artifact.label}: source is not a file: {artifact.source}")


def _plan_destinations(output_dir: Path, artifacts: list[ArtifactSpec]) -> list[Path]:
    used: set[str] = set()
    destinations: list[Path] = []
    for artifact in artifacts:
        filename = artifact.source.name or _safe_label(artifact.label)
        if filename in used:
            filename = _unique_filename(_safe_label(artifact.label), artifact.source, used)
        used.add(filename)
        destinations.append(output_dir / filename)
    return destinations


def _unique_filename(label: str, source: Path, used: set[str]) -> str:
    suffix = "".join(source.suffixes)
    stem = label
    index = 1
    while True:
        candidate = f"{stem}{suffix}" if index == 1 else f"{stem}_{index}{suffix}"
        if candidate not in used:
            return candidate
        index += 1


def _validate_overwrite(
    artifacts: list[ArtifactSpec],
    destinations: list[Path],
    manifest_path: Path,
    *,
    force: bool,
) -> None:
    existing: list[Path] = []
    for artifact, path in zip(artifacts, destinations, strict=True):
        if not path.exists():
            continue
        if artifact.source.resolve() == path.resolve():
            continue
        existing.append(path)
    if manifest_path.exists():
        existing.append(manifest_path)
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"bundle output already exists; use --force to overwrite: {names}")


def _artifact_manifest(artifact: ArtifactSpec, destination: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": artifact.label,
        "source": str(artifact.source),
        "bundled_path": destination.name,
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }
    summary = _json_summary_fields(destination)
    if summary:
        payload.update(summary)
    return payload


def _json_summary_fields(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".json":
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"summary_json_readable": False}
    if not isinstance(payload, dict):
        return {"summary_json_readable": True}
    fields: dict[str, Any] = {"summary_json_readable": True}
    for key, manifest_key in (
        ("schema", "summary_schema"),
        ("decision", "summary_decision"),
        ("ok", "summary_ok"),
        ("acceptance_enabled", "acceptance_enabled"),
        ("acceptance_passed", "acceptance_passed"),
        ("acceptance_decision", "acceptance_decision"),
    ):
        if key in payload:
            fields[manifest_key] = payload[key]
    return fields


def _load_manifest_for_validation(path: Path) -> tuple[dict[str, Any], list[str]]:
    messages: list[str] = []
    if not path.exists():
        return {}, [f"manifest does not exist: {path}"]
    if not path.is_file():
        return {}, [f"manifest is not a file: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"manifest JSON is unreadable: {exc}"]
    if not isinstance(payload, dict):
        return {}, ["manifest JSON root must be an object"]
    return payload, messages


def _validate_artifact(
    manifest_path: Path,
    artifact: dict[str, Any],
) -> BundleArtifactValidation:
    label = str(artifact.get("label") or "<missing-label>")
    path = _artifact_validation_path(manifest_path, artifact)
    messages: list[str] = []
    summary_schema: str | None = None
    summary_decision: str | None = None
    acceptance_decision: str | None = None

    if not artifact.get("label"):
        messages.append("missing label")
    if not path.exists():
        messages.append("file does not exist")
        return BundleArtifactValidation(
            label=label,
            path=path,
            ok=False,
            messages=tuple(messages),
        )
    if not path.is_file():
        messages.append("path is not a file")
        return BundleArtifactValidation(
            label=label,
            path=path,
            ok=False,
            messages=tuple(messages),
        )

    expected_size = artifact.get("size_bytes")
    if expected_size is not None and expected_size != path.stat().st_size:
        messages.append(
            f"size mismatch: manifest={expected_size} actual={path.stat().st_size}"
        )
    expected_sha = artifact.get("sha256")
    if expected_sha is not None:
        actual_sha = _sha256(path)
        if expected_sha != actual_sha:
            messages.append(
                f"sha256 mismatch: manifest={str(expected_sha)[:12]} "
                f"actual={actual_sha[:12]}"
            )

    if path.suffix.lower() == ".json":
        json_messages, summary_schema, summary_decision, acceptance_decision = (
            _validate_json_artifact(path, artifact)
        )
        messages.extend(json_messages)

    for key, label_text in (
        ("summary_ok", "summary ok"),
        ("acceptance_passed", "acceptance"),
    ):
        if artifact.get(key) is False:
            messages.append(f"manifest records failed {label_text}")
    for key in ("summary_decision", "acceptance_decision"):
        value = artifact.get(key)
        if value is not None and not _decision_passes(str(value)):
            messages.append(f"manifest records failing {key}: {value}")

    return BundleArtifactValidation(
        label=label,
        path=path,
        ok=not messages,
        messages=tuple(messages),
        summary_schema=summary_schema,
        summary_decision=summary_decision,
        acceptance_decision=acceptance_decision,
    )


def _artifact_validation_path(manifest_path: Path, artifact: dict[str, Any]) -> Path:
    bundled = artifact.get("bundled_path")
    if isinstance(bundled, str) and bundled:
        return manifest_path.parent / bundled
    raw_path = artifact.get("path")
    if isinstance(raw_path, str) and raw_path:
        return Path(raw_path)
    return manifest_path.parent / str(artifact.get("label") or "artifact")


def _validate_json_artifact(
    path: Path,
    manifest_artifact: dict[str, Any],
) -> tuple[list[str], str | None, str | None, str | None]:
    messages: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"JSON artifact is unreadable: {exc}"], None, None, None
    if not isinstance(payload, dict):
        return messages, None, None, None

    summary_schema = _optional_string(payload.get("schema"))
    summary_decision = _optional_string(payload.get("decision"))
    acceptance_decision = _optional_string(payload.get("acceptance_decision"))

    _compare_manifest_json_field(
        messages,
        "summary_schema",
        manifest_artifact.get("summary_schema"),
        summary_schema,
    )
    _compare_manifest_json_field(
        messages,
        "summary_decision",
        manifest_artifact.get("summary_decision"),
        summary_decision,
    )
    _compare_manifest_json_field(
        messages,
        "summary_ok",
        manifest_artifact.get("summary_ok"),
        payload.get("ok"),
    )
    _compare_manifest_json_field(
        messages,
        "acceptance_passed",
        manifest_artifact.get("acceptance_passed"),
        payload.get("acceptance_passed"),
    )
    _compare_manifest_json_field(
        messages,
        "acceptance_decision",
        manifest_artifact.get("acceptance_decision"),
        acceptance_decision,
    )

    if payload.get("ok") is False:
        messages.append("summary payload reports ok=false")
    if summary_decision is not None and not _decision_passes(summary_decision):
        messages.append(f"summary payload reports failing decision: {summary_decision}")
    if payload.get("acceptance_enabled") is True and payload.get("acceptance_passed") is not True:
        messages.append("summary payload reports failed acceptance")
    if acceptance_decision is not None and not _decision_passes(acceptance_decision):
        messages.append(
            f"summary payload reports failing acceptance decision: {acceptance_decision}"
        )
    return messages, summary_schema, summary_decision, acceptance_decision


def _compare_manifest_json_field(
    messages: list[str],
    field: str,
    recorded: Any,
    actual: Any,
) -> None:
    if recorded is None:
        return
    if recorded != actual:
        messages.append(f"{field} mismatch: manifest={recorded!r} actual={actual!r}")


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _decision_passes(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return False
    failing_markers = ("failed", "failure", "error")
    return not any(marker in normalized for marker in failing_markers)


def _write_validation_summary(path: Path, report: BundleValidationReport) -> None:
    payload = {
        "schema": VALIDATION_SCHEMA,
        "decision": report.decision,
        "ok": report.ok,
        "manifest": str(report.manifest_path),
        "bundle_schema": report.schema,
        "artifact_count": report.artifact_count,
        "messages": list(report.messages),
        "artifacts": [
            {
                "label": artifact.label,
                "path": str(artifact.path),
                "ok": artifact.ok,
                "messages": list(artifact.messages),
                "summary_schema": artifact.summary_schema,
                "summary_decision": artifact.summary_decision,
                "acceptance_decision": artifact.acceptance_decision,
            }
            for artifact in report.artifacts
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", label.strip())
    return sanitized.strip("._") or "artifact"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
