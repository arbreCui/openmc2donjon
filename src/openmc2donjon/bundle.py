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


@dataclass(frozen=True)
class ArtifactSpec:
    label: str
    source: Path


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
