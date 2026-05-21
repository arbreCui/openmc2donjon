"""Final handoff summary payloads for managed OpenMC-to-DONJON runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HANDOFF_SUMMARY_SCHEMA = "openmc2donjon.handoff-summary.v1"
HANDOFF_PASS_DECISION = "openmc2donjon_handoff_passed"
HANDOFF_FAIL_DECISION = "openmc2donjon_handoff_failed"


def write_handoff_summary(
    path: Path,
    *,
    package_version: str,
    run_dir: Path,
    recipe_path: Path,
    statepoint_path: Path | None,
    hdf5_path: Path,
    output_path: Path,
    output_format: str,
    summary: dict[str, object],
    run_summary_json: Path | None,
    check_summary_json: Path | None,
    manifest_path: Path,
    bundle_validation_summary_json: Path | None,
    bundle_validation_passed: bool | None,
    bundle_validation_decision: str | None,
    adf_enabled: bool,
    sph_enabled: bool,
) -> None:
    payload = handoff_summary_payload(
        package_version=package_version,
        run_dir=run_dir,
        recipe_path=recipe_path,
        statepoint_path=statepoint_path,
        hdf5_path=hdf5_path,
        output_path=output_path,
        output_format=output_format,
        summary=summary,
        run_summary_json=run_summary_json,
        check_summary_json=check_summary_json,
        manifest_path=manifest_path,
        bundle_validation_summary_json=bundle_validation_summary_json,
        bundle_validation_passed=bundle_validation_passed,
        bundle_validation_decision=bundle_validation_decision,
        adf_enabled=adf_enabled,
        sph_enabled=sph_enabled,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def handoff_summary_payload(
    *,
    package_version: str,
    run_dir: Path,
    recipe_path: Path,
    statepoint_path: Path | None,
    hdf5_path: Path,
    output_path: Path,
    output_format: str,
    summary: dict[str, object],
    run_summary_json: Path | None,
    check_summary_json: Path | None,
    manifest_path: Path,
    bundle_validation_summary_json: Path | None,
    bundle_validation_passed: bool | None,
    bundle_validation_decision: str | None,
    adf_enabled: bool,
    sph_enabled: bool,
) -> dict[str, object]:
    manifest = _read_json_object(manifest_path)
    ok = bundle_validation_passed is not False
    return {
        "schema": HANDOFF_SUMMARY_SCHEMA,
        "package_version": package_version,
        "decision": HANDOFF_PASS_DECISION if ok else HANDOFF_FAIL_DECISION,
        "ok": ok,
        "run_dir": str(run_dir),
        "recipe": str(recipe_path),
        "statepoint": None if statepoint_path is None else str(statepoint_path),
        "hdf5": str(hdf5_path),
        "output": str(output_path),
        "format": output_format,
        "run_summary_json": _path_string(run_summary_json),
        "check_summary_json": _path_string(check_summary_json),
        "manifest": str(manifest_path),
        "bundle_validation_summary_json": _path_string(bundle_validation_summary_json),
        "bundle_validation_enabled": bundle_validation_summary_json is not None,
        "bundle_validation_passed": bundle_validation_passed,
        "bundle_validation_decision": bundle_validation_decision,
        "checked": bool(summary.get("checked")),
        "check_passed": summary.get("check_passed"),
        "energy_groups": summary.get("energy_groups"),
        "legendre_order": summary.get("legendre_order"),
        "mixture_count": summary.get("mixture_count"),
        "mixture_names": summary.get("mixture_names"),
        "state_points": summary.get("state_points"),
        "burnup_axis": summary.get("burnup_axis"),
        "selected_mixtures": summary.get("selected_mixtures"),
        "artifact_count": _manifest_artifact_count(manifest),
        "artifact_labels": _manifest_artifact_labels(manifest),
        "correction_artifacts": {"adf": adf_enabled, "sph": sph_enabled},
    }


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _manifest_artifact_count(manifest: dict[str, Any] | None) -> int | None:
    if manifest is None:
        return None
    value = manifest.get("artifact_count")
    return value if isinstance(value, int) else None


def _manifest_artifact_labels(manifest: dict[str, Any] | None) -> list[str]:
    artifacts = [] if manifest is None else manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        return []
    return [
        artifact["label"]
        for artifact in artifacts
        if isinstance(artifact, dict) and isinstance(artifact.get("label"), str)
    ]


def _path_string(path: Path | None) -> str | None:
    return None if path is None else str(path)
