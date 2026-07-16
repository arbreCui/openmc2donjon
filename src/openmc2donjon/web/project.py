"""Manifest-driven Converter project status and guarded manifest editing."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from ..component_library import _native_sph_acceptance_issues
from ..native_sph_validation import (
    native_sph_reference_issues,
    production_receipt_policy_issues,
)
from ..physical_sph_contract import (
    physical_colorset_sph_issues,
    physical_sph_issues,
)
from .execution import parse_donjon_k_effective
from .filesystem import FilesystemScope


PROJECT_STATUS_SCHEMA = "openmc2donjon.project-status.v3"
PROJECT_MANIFEST_SCHEMA = "openmc2donjon.project.v1"
PROJECT_MANIFEST_EDITOR_SCHEMA = "openmc2donjon.project-manifest.v1"
ACCEPTANCE_DECISION_SCHEMA = "openmc2donjon.acceptance.v1"
IRENA30_FULLCORE_VALIDATOR_CONTRACT = "irena30-orbit-fullcore-v1"
IRENA30_FULLCORE_PHYSICS_SCHEMA = (
    "openmc2donjon.irena30-orbit-fullcore-physics.v1"
)
IRENA30_FULLCORE_PASSED_DECISION = "irena30_orbit_fullcore_physics_passed"
IRENA30_FULLCORE_TEMPLATE = "irena30-fullcore-physical"
NATIVE_SPH_PHYSICS_SCHEMA = (
    "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1"
)
PROJECT_MANIFEST_NAME = "openmc2donjon.project.json"
_GENERIC_PHYSICAL_SPH_CONTRACT = "physical-sph"
_IRENA_COLORSET_SPH_CONTRACT = "irena30-colorset-sph"
_LEGACY_COLORSET_SPH_CONTRACT = "physical-colorset-sph"
_NATIVE_SPH_CONTRACT = "native-sph"
_COLORSET_SPH_CONTRACTS = {
    _IRENA_COLORSET_SPH_CONTRACT,
    _LEGACY_COLORSET_SPH_CONTRACT,
}
_PHYSICAL_SPH_CONTRACTS = {
    _GENERIC_PHYSICAL_SPH_CONTRACT,
    _NATIVE_SPH_CONTRACT,
    *_COLORSET_SPH_CONTRACTS,
}
_CONTRACTS = {"converter-hdf5", *_PHYSICAL_SPH_CONTRACTS}
_FORMATS = {"multicompo", "macrolib"}
_WRITER_BACKENDS = {"ascii", "pygan"}
_ACCEPTANCE_MODES = {"handoff-only", "physics-gated"}


def register_project_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope | None = None,
) -> None:
    """Register project status, creation, and manifest editor endpoints."""

    from fastapi import Body, HTTPException, Query

    scope = filesystem_scope or FilesystemScope()
    create_body = Body(...)
    manifest_body = Body(...)

    @app.get("/api/project/status")
    def api_project_status(root: str = Query(..., min_length=1)) -> dict[str, Any]:
        project_root = scope.resolve(root, HTTPException)
        return project_status(project_root, mock_mode=mock_mode)

    @app.get("/api/project/manifest")
    def api_project_manifest(root: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            raise HTTPException(
                status_code=409,
                detail="project manifest editing is unavailable in mock mode",
            )
        project_root = scope.resolve(root, HTTPException)
        manifest_path = project_root / PROJECT_MANIFEST_NAME
        scope.enforce(manifest_path, HTTPException)
        if not manifest_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"project manifest does not exist: {manifest_path}",
            )
        manifest, issues = _read_manifest(manifest_path, project_root)
        if manifest is None:
            raise HTTPException(
                status_code=422,
                detail=_manifest_rejection_detail(issues),
            )
        if issues:
            raise HTTPException(
                status_code=422,
                detail=_manifest_rejection_detail(issues),
            )
        return _manifest_editor_payload(project_root, manifest_path, manifest)

    @app.post("/api/project/manifest")
    def api_project_manifest_save(
        payload: dict[str, Any] = manifest_body,
    ) -> dict[str, Any]:
        if mock_mode:
            raise HTTPException(
                status_code=409,
                detail="project manifest editing is unavailable in mock mode",
            )
        raw_root = payload.get("root")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise HTTPException(status_code=422, detail="root must be a non-empty path")
        project_root = scope.resolve(raw_root, HTTPException)
        manifest_path = project_root / PROJECT_MANIFEST_NAME
        scope.enforce(manifest_path, HTTPException)
        if not manifest_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"project manifest does not exist: {manifest_path}",
            )
        current_manifest, current_issues = _read_manifest(manifest_path, project_root)
        if current_manifest is None:
            raise HTTPException(
                status_code=422,
                detail=_manifest_rejection_detail(current_issues),
            )
        manifest = payload.get("manifest")
        if not isinstance(manifest, dict):
            raise HTTPException(
                status_code=422,
                detail="project manifest must be a JSON object",
            )
        issues = _validate_manifest(manifest, project_root)
        if (
            current_manifest.get("template") == IRENA30_FULLCORE_TEMPLATE
            and manifest.get("template") != IRENA30_FULLCORE_TEMPLATE
        ):
            issues.append(
                "strict IRENA full-core template identity cannot be removed or changed"
            )
        if issues:
            raise HTTPException(
                status_code=422,
                detail=_manifest_rejection_detail(issues),
            )
        _create_project_artifact_directories(project_root, manifest)
        _write_manifest_atomic(manifest_path, manifest)
        return _manifest_editor_payload(project_root, manifest_path, manifest)

    @app.post("/api/project/create")
    def api_project_create(payload: dict[str, Any] = create_body) -> dict[str, Any]:
        if mock_mode:
            raise HTTPException(
                status_code=409,
                detail="project creation is unavailable in mock mode",
            )
        raw_root = payload.get("root")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise HTTPException(status_code=422, detail="root must be a non-empty path")
        project_root = scope.resolve(raw_root, HTTPException)
        manifest_path = project_root / PROJECT_MANIFEST_NAME
        if manifest_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"project manifest already exists: {manifest_path}",
            )
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            name = project_root.name or "Converter project"
        acceptance_mode = payload.get("acceptance_mode", "handoff-only")
        if acceptance_mode not in _ACCEPTANCE_MODES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "acceptance_mode must be handoff-only or physics-gated"
                ),
            )
        writer_backend = payload.get("writer_backend", "ascii")
        if writer_backend not in _WRITER_BACKENDS:
            raise HTTPException(
                status_code=422,
                detail="writer_backend must be ascii or pygan",
            )
        project_root.mkdir(parents=True, exist_ok=True)
        manifest = _starter_manifest(
            name.strip(),
            acceptance_mode=str(acceptance_mode),
            writer_backend=str(writer_backend),
        )
        _create_project_artifact_directories(project_root, manifest)
        if acceptance_mode == "physics-gated":
            decision_path = project_root / "acceptance" / "decision.json"
            if decision_path.exists():
                raise HTTPException(
                    status_code=409,
                    detail=f"project acceptance decision already exists: {decision_path}",
                )
            _write_manifest_atomic(decision_path, _starter_acceptance_decision())
        _write_manifest_atomic(manifest_path, manifest)
        return project_status(project_root, mock_mode=False)


def project_status(root: Path, *, mock_mode: bool = False) -> dict[str, Any]:
    """Inspect a project described by ``openmc2donjon.project.json``.

    Component count, names, paths, contracts, and downstream consumer are all
    project data. The backend has no built-in assumption that a project is
    IRENA, has five components, uses colorsets, or owns a 91-position core.
    """

    manifest_path = root / PROJECT_MANIFEST_NAME
    manifest, configuration_issues = _read_manifest(manifest_path, root)
    configured = manifest is not None and not configuration_issues
    if not configured:
        return _unconfigured_status(
            root,
            manifest_path,
            configuration_issues,
            mock_mode=mock_mode,
        )

    assert manifest is not None
    rows = [_component_status(root, component, mock_mode=mock_mode) for component in manifest["components"]]
    required = [row for row in rows if row["required"]]
    accepted_inputs = sum(row["handoff"]["state"] == "accepted" for row in required)
    accepted_outputs = sum(row["output"]["state"] == "accepted" for row in required)
    ready_components = sum(
        row["handoff"]["state"] == "accepted" and row["output"]["state"] == "accepted" for row in required
    )
    consumer = _consumer_status(root, manifest.get("consumer"), mock_mode=mock_mode)
    handoffs_ready = bool(required) and ready_components == len(required)
    acceptance_mode = _manifest_acceptance_mode(manifest)
    acceptance = _acceptance_status(
        root,
        manifest.get("acceptance"),
        components=manifest["components"],
        components_ready=handoffs_ready,
        mock_mode=mock_mode,
    )
    physics_accepted = acceptance["state"] == "accepted"
    acceptance_basis = acceptance["basis"]
    machine_verified_acceptance = bool(
        physics_accepted and acceptance_basis == "machine-verified"
    )
    project_declared_acceptance = bool(
        physics_accepted and acceptance_basis == "project-declared"
    )
    ready_for_consumer = handoffs_ready and (
        acceptance_mode == "handoff-only" or physics_accepted
    )
    return {
        "schema": PROJECT_STATUS_SCHEMA,
        "manifest_schema": PROJECT_MANIFEST_SCHEMA,
        "manifest_path": str(manifest_path),
        "configured": True,
        "configuration_issues": [],
        "name": manifest["name"],
        "description": manifest.get("description", ""),
        "template": manifest.get("template"),
        "workflow": manifest.get("workflow", "component-library"),
        "acceptance_mode": acceptance_mode,
        "acceptance_required": acceptance_mode == "physics-gated",
        "root": str(root),
        "root_exists": root.is_dir() if not mock_mode else True,
        "required_components": len(required),
        "accepted_inputs": accepted_inputs,
        "accepted_outputs": accepted_outputs,
        "ready_components": ready_components,
        "handoffs_ready": handoffs_ready,
        "physics_accepted": physics_accepted,
        "acceptance_basis": acceptance_basis,
        "machine_verified_acceptance": machine_verified_acceptance,
        "project_declared_acceptance": project_declared_acceptance,
        "ready_for_consumer": ready_for_consumer,
        "components": rows,
        "consumer": consumer,
        "acceptance": acceptance,
        # Compatibility aliases for older clients while the UI migrates.
        "required_colorsets": len(required),
        "accepted_handoffs": accepted_inputs,
        "accepted_cpos": accepted_outputs,
        "ready_for_core": ready_for_consumer,
        "colorsets": rows,
        "core": _legacy_core_status(consumer),
    }


def _read_manifest(path: Path, root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, [f"missing {PROJECT_MANIFEST_NAME}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read project manifest: {exc}"]
    if not isinstance(payload, dict):
        return None, ["project manifest must be a JSON object"]

    return payload, _validate_manifest(payload, root)


def _validate_manifest(payload: dict[str, Any], root: Path) -> list[str]:
    """Validate the same manifest contract for status reads and editor saves."""

    issues: list[str] = []
    if payload.get("schema") != PROJECT_MANIFEST_SCHEMA:
        issues.append(f"schema must be {PROJECT_MANIFEST_SCHEMA}")
    if not isinstance(payload.get("name"), str) or not payload["name"].strip():
        issues.append("name must be a non-empty string")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        issues.append("components must be a non-empty array")
        return issues

    seen: set[str] = set()
    for index, component in enumerate(components):
        prefix = f"components[{index}]"
        if not isinstance(component, dict):
            issues.append(f"{prefix} must be an object")
            continue
        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id.strip():
            issues.append(f"{prefix}.id must be a non-empty string")
        elif component_id in seen:
            issues.append(f"duplicate component id: {component_id}")
        else:
            seen.add(component_id)
        if not isinstance(component.get("label"), str) or not component["label"].strip():
            issues.append(f"{prefix}.label must be a non-empty string")
        for field in ("input", "output"):
            value = component.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"{prefix}.{field} must be a non-empty relative path")
            elif _safe_project_path(root, value) is None:
                issues.append(f"{prefix}.{field} must stay inside the project root")
        receipt = component.get("receipt")
        if receipt is not None and (
            not isinstance(receipt, str) or _safe_project_path(root, receipt) is None
        ):
            issues.append(f"{prefix}.receipt must be a relative path inside the project root")
        contract = component.get("contract", "converter-hdf5")
        if isinstance(contract, dict):
            contract = contract.get("kind")
        if contract not in _CONTRACTS:
            issues.append(f"{prefix}.contract must be one of {sorted(_CONTRACTS)}")
        physics_summary = component.get("physics_summary")
        if physics_summary is not None and contract != _NATIVE_SPH_CONTRACT:
            issues.append(
                f"{prefix}.physics_summary is only valid for native-sph components"
            )
        elif physics_summary is not None:
            if (
                not isinstance(physics_summary, str)
                or not physics_summary.strip()
                or _safe_project_path(root, physics_summary) is None
            ):
                issues.append(
                    f"{prefix}.physics_summary must be a relative path inside "
                    "the project root"
                )
            if "receipt" not in component:
                issues.append(
                    f"{prefix}.receipt must explicitly declare the Converter "
                    "receipt when physics_summary is declared"
                )
            elif (
                isinstance(receipt, str)
                and isinstance(physics_summary, str)
                and _safe_project_path(root, receipt)
                == _safe_project_path(root, physics_summary)
            ):
                issues.append(
                    f"{prefix}.receipt and physics_summary must be different files"
                )
        native_sph = component.get("native_sph")
        if "native_sph" in component and contract != _NATIVE_SPH_CONTRACT:
            issues.append(
                f"{prefix}.native_sph is only valid for native-sph components"
            )
        elif "native_sph" in component:
            issues.extend(
                _native_sph_execution_declaration_issues(
                    root,
                    native_sph,
                    prefix=f"{prefix}.native_sph",
                )
            )
        output_format = component.get("format", "multicompo")
        if output_format not in _FORMATS:
            issues.append(f"{prefix}.format must be one of {sorted(_FORMATS)}")
        conversion = component.get("conversion")
        if conversion is not None:
            if not isinstance(conversion, dict):
                issues.append(f"{prefix}.conversion must be an object")
            else:
                writer_backend = conversion.get("writer_backend", "ascii")
                if writer_backend not in _WRITER_BACKENDS:
                    issues.append(
                        f"{prefix}.conversion.writer_backend must be one of "
                        f"{sorted(_WRITER_BACKENDS)}"
                    )
                for field in ("root_name", "comment"):
                    value = conversion.get(field)
                    if value is not None and not isinstance(value, str):
                        issues.append(f"{prefix}.conversion.{field} must be a string")
                for field in ("burnup", "h_factor_default"):
                    value = conversion.get(field)
                    if value is not None and (
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(float(value))
                    ):
                        issues.append(
                            f"{prefix}.conversion.{field} must be a finite number"
                        )
                mixtures = conversion.get("mixtures")
                if mixtures is not None and (
                    not isinstance(mixtures, list)
                    or not all(
                        isinstance(item, str) and item.strip() for item in mixtures
                    )
                ):
                    issues.append(
                        f"{prefix}.conversion.mixtures must be an array of "
                        "non-empty strings"
                    )
        evidence = component.get("evidence", [])
        if not isinstance(evidence, list):
            issues.append(f"{prefix}.evidence must be an array")
        else:
            for evidence_index, item in enumerate(evidence):
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    issues.append(f"{prefix}.evidence[{evidence_index}] needs label and path")
                elif _safe_project_path(root, item["path"]) is None:
                    issues.append(
                        f"{prefix}.evidence[{evidence_index}].path must stay inside the project root"
                    )
    raw_acceptance_mode = payload.get("acceptance_mode")
    if (
        raw_acceptance_mode is not None
        and raw_acceptance_mode not in _ACCEPTANCE_MODES
    ):
        issues.append(
            "acceptance_mode must be handoff-only or physics-gated"
        )
    acceptance = payload.get("acceptance")
    if raw_acceptance_mode == "handoff-only" and acceptance is not None:
        issues.append(
            "handoff-only projects must not declare an acceptance ledger"
        )
    if raw_acceptance_mode == "physics-gated" and not isinstance(
        acceptance, dict
    ):
        issues.append(
            "physics-gated projects must declare acceptance.decision"
        )
    if acceptance is not None:
        if not isinstance(acceptance, dict):
            issues.append("acceptance must be an object")
        else:
            decision = acceptance.get("decision")
            if not isinstance(decision, str) or not decision.strip():
                issues.append("acceptance.decision must be a non-empty relative path")
            elif _safe_project_path(root, decision) is None:
                issues.append("acceptance.decision must stay inside the project root")
            validator = acceptance.get("validator")
            if validator is not None:
                if not isinstance(validator, dict):
                    issues.append("acceptance.validator must be an object")
                else:
                    contract = validator.get("contract")
                    if contract != IRENA30_FULLCORE_VALIDATOR_CONTRACT:
                        issues.append(
                            "acceptance.validator.contract must be "
                            f"{IRENA30_FULLCORE_VALIDATOR_CONTRACT}"
                        )
                    summary = validator.get("summary")
                    if not isinstance(summary, str) or not summary.strip():
                        issues.append(
                            "acceptance.validator.summary must be a non-empty relative path"
                        )
                    elif _safe_project_path(root, summary) is None:
                        issues.append(
                            "acceptance.validator.summary must stay inside the project root"
                        )
                    component = validator.get("component")
                    if component is not None and (
                        not isinstance(component, str) or not component.strip()
                    ):
                        issues.append(
                            "acceptance.validator.component must be a non-empty component id"
                        )
                    elif isinstance(component, str) and component not in seen:
                        issues.append(
                            "acceptance.validator.component does not name a project component"
                        )
    if payload.get("template") == IRENA30_FULLCORE_TEMPLATE:
        if raw_acceptance_mode == "handoff-only":
            issues.append(
                "strict IRENA full-core projects cannot use handoff-only mode"
            )
        if (
            not isinstance(acceptance, dict)
            or not isinstance(acceptance.get("validator"), dict)
        ):
            issues.append(
                "strict IRENA full-core projects must declare acceptance.validator"
            )
    return issues


def _manifest_rejection_detail(issues: list[str]) -> str:
    return "project manifest rejected: " + "; ".join(issues)


def _native_sph_execution_declaration_issues(
    root: Path,
    declaration: Any,
    *,
    prefix: str,
) -> list[str]:
    """Validate an optional, project-owned native-SPH execution declaration."""

    if not isinstance(declaration, dict):
        return [f"{prefix} must be an object"]

    issues: list[str] = []
    resolved: dict[str, Path] = {}
    for field in ("deck", "working_directory"):
        value = declaration.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{prefix}.{field} must be a non-empty relative path")
            continue
        candidate = Path(value)
        if candidate.is_absolute() or (
            candidate.parts and candidate.parts[0].startswith("~")
        ):
            issues.append(f"{prefix}.{field} must be a relative path")
            continue
        path = _safe_relative_project_path(root, value)
        if path is None:
            issues.append(f"{prefix}.{field} must stay inside the project root")
            continue
        resolved[field] = path

    deck_value = declaration.get("deck")
    if (
        isinstance(deck_value, str)
        and deck_value.strip()
        and Path(deck_value).suffix.lower() != ".x2m"
    ):
        issues.append(f"{prefix}.deck must end with .x2m")

    working_path = resolved.get("working_directory")
    if working_path is not None and working_path.exists() and not working_path.is_dir():
        issues.append(f"{prefix}.working_directory must be a directory")
    deck_path = resolved.get("deck")
    if deck_path is not None and deck_path.exists() and not deck_path.is_file():
        issues.append(f"{prefix}.deck must be a regular file when it exists")
    if deck_path is not None and deck_path == working_path:
        issues.append(f"{prefix}.deck and working_directory must be different paths")
    return issues


def _manifest_editor_payload(
    root: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": PROJECT_MANIFEST_EDITOR_SCHEMA,
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def _manifest_acceptance_mode(manifest: dict[str, Any]) -> str:
    """Return the explicit mode, or infer it for pre-mode manifests."""

    mode = manifest.get("acceptance_mode")
    if mode in _ACCEPTANCE_MODES:
        return str(mode)
    return "physics-gated" if isinstance(manifest.get("acceptance"), dict) else "handoff-only"


def _create_project_artifact_directories(
    root: Path,
    manifest: dict[str, Any],
) -> None:
    """Create every project-owned parent needed by the declared workflow."""

    directories = {root / "outputs", root / "diagnostics"}
    components = manifest.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            output_value = component.get("output")
            for value in (component.get("input"), output_value):
                path = _safe_project_path(root, value) if isinstance(value, str) else None
                if path is not None:
                    directories.add(path.parent)
            receipt_value = component.get("receipt")
            if receipt_value is None and isinstance(output_value, str):
                receipt_value = f"{output_value}.convert.json"
            receipt_path = (
                _safe_project_path(root, receipt_value)
                if isinstance(receipt_value, str)
                else None
            )
            if receipt_path is not None:
                directories.add(receipt_path.parent)
            physics_summary_value = component.get("physics_summary")
            physics_summary_path = (
                _safe_project_path(root, physics_summary_value)
                if isinstance(physics_summary_value, str)
                else None
            )
            if physics_summary_path is not None:
                directories.add(physics_summary_path.parent)
            evidence = component.get("evidence")
            if isinstance(evidence, list):
                for item in evidence:
                    if not isinstance(item, dict):
                        continue
                    raw_path = item.get("path")
                    path = (
                        _safe_project_path(root, raw_path)
                        if isinstance(raw_path, str)
                        else None
                    )
                    if path is not None:
                        directories.add(path.parent)
            native_sph = component.get("native_sph")
            if isinstance(native_sph, dict):
                deck = native_sph.get("deck")
                deck_path = (
                    _safe_relative_project_path(root, deck)
                    if isinstance(deck, str)
                    else None
                )
                if deck_path is not None:
                    directories.add(deck_path.parent)
                working_directory = native_sph.get("working_directory")
                working_path = (
                    _safe_relative_project_path(root, working_directory)
                    if isinstance(working_directory, str)
                    else None
                )
                if working_path is not None:
                    directories.add(working_path)

    acceptance = manifest.get("acceptance")
    if isinstance(acceptance, dict):
        for raw_path in (
            acceptance.get("decision"),
            acceptance.get("validator", {}).get("summary")
            if isinstance(acceptance.get("validator"), dict)
            else None,
        ):
            path = (
                _safe_project_path(root, raw_path)
                if isinstance(raw_path, str)
                else None
            )
            if path is not None:
                directories.add(path.parent)

    consumer = manifest.get("consumer")
    if isinstance(consumer, dict) and isinstance(consumer.get("runs"), list):
        for run in consumer["runs"]:
            if not isinstance(run, dict):
                continue
            for raw_path in (run.get("deck"), run.get("result")):
                path = (
                    _safe_project_path(root, raw_path)
                    if isinstance(raw_path, str)
                    else None
                )
                if path is not None:
                    directories.add(path.parent)

    for directory in sorted(directories, key=str):
        directory.mkdir(parents=True, exist_ok=True)


def _write_manifest_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            temporary_path = Path(stream.name)
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _unconfigured_status(
    root: Path,
    manifest_path: Path,
    issues: list[str],
    *,
    mock_mode: bool,
) -> dict[str, Any]:
    consumer = {
        "kind": "unconfigured",
        "label": "No downstream consumer configured",
        "href": None,
        "runs": [],
    }
    return {
        "schema": PROJECT_STATUS_SCHEMA,
        "manifest_schema": None,
        "manifest_path": str(manifest_path),
        "configured": False,
        "configuration_issues": issues,
        "name": root.name or str(root),
        "description": "",
        "template": None,
        "workflow": None,
        "acceptance_mode": None,
        "acceptance_required": False,
        "root": str(root),
        "root_exists": root.is_dir() if not mock_mode else True,
        "required_components": 0,
        "accepted_inputs": 0,
        "accepted_outputs": 0,
        "ready_components": 0,
        "handoffs_ready": False,
        "physics_accepted": False,
        "acceptance_basis": "not-required",
        "machine_verified_acceptance": False,
        "project_declared_acceptance": False,
        "ready_for_consumer": False,
        "components": [],
        "consumer": consumer,
        "acceptance": _empty_acceptance_status(),
        "required_colorsets": 0,
        "accepted_handoffs": 0,
        "accepted_cpos": 0,
        "ready_for_core": False,
        "colorsets": [],
        "core": _legacy_core_status(consumer),
    }


def _component_status(
    root: Path,
    definition: dict[str, Any],
    *,
    mock_mode: bool,
) -> dict[str, Any]:
    input_path = _safe_project_path(root, str(definition["input"]))
    output_path = _safe_project_path(root, str(definition["output"]))
    assert input_path is not None and output_path is not None
    contract = definition.get("contract", "converter-hdf5")
    contract_kind = contract.get("kind") if isinstance(contract, dict) else contract
    legacy_native_receipt = (
        contract_kind == _NATIVE_SPH_CONTRACT
        and "physics_summary" not in definition
    )
    receipt_value = definition.get("receipt", f"{definition['output']}.convert.json")
    declared_receipt_path = _safe_project_path(root, str(receipt_value))
    assert declared_receipt_path is not None
    if legacy_native_receipt:
        receipt_path: Path | None = None
        physics_summary_path: Path | None = declared_receipt_path
    elif contract_kind == _NATIVE_SPH_CONTRACT:
        receipt_path = declared_receipt_path
        physics_summary_value = definition.get(
            "physics_summary",
            f"{definition['output']}.physics.json",
        )
        physics_summary_path = _safe_project_path(root, str(physics_summary_value))
        assert physics_summary_path is not None
    else:
        receipt_path = declared_receipt_path
        physics_summary_path = None
    output_format = str(definition.get("format", "multicompo"))
    evidence_paths = [
        {
            "id": str(item.get("id", f"evidence-{index + 1}")),
            "label": str(item.get("label", item.get("id", f"Evidence {index + 1}"))),
            "path": str(_safe_project_path(root, str(item["path"]))),
        }
        for index, item in enumerate(definition.get("evidence", []))
    ]
    paths = {
        "directory": str(input_path.parent),
        "input": str(input_path),
        "output": str(output_path),
        "receipt": "" if receipt_path is None else str(receipt_path),
        "physics_summary": "" if physics_summary_path is None else str(physics_summary_path),
        "evidence": evidence_paths,
        # Compatibility aliases for the IRENA-specific pages.
        "sph_applied": str(input_path),
        "cpo": str(output_path),
        "cpo_receipt": "" if receipt_path is None else str(receipt_path),
    }
    native_sph = _native_sph_execution_status(root, definition)
    if mock_mode:
        artifact = {"state": "missing", "issues": ["mock project has no physical files"]}
        return _component_row(
            definition,
            contract_kind,
            output_format,
            paths,
            native_sph,
            artifact,
            artifact,
            artifact,
        )

    evidence = _evidence_status(evidence_paths)
    handoff = _handoff_status(input_path, contract_kind)
    if contract_kind == _NATIVE_SPH_CONTRACT:
        assert physics_summary_path is not None
        output = _native_sph_output_status(
            output_path,
            physics_summary_path,
            receipt_path,
            input_path,
            identity=definition.get("identity"),
            metadata=(definition.get("metadata") if isinstance(definition.get("metadata"), dict) else {}),
        )
        if legacy_native_receipt:
            output = {
                "state": "rejected" if output["state"] != "missing" else "missing",
                "issues": [
                    "legacy native-sph manifest uses receipt as physics_summary; "
                    "declare a distinct Converter receipt and physics_summary",
                    *output["issues"],
                ],
            }
    else:
        assert receipt_path is not None
        output = _output_status(
            output_path,
            receipt_path,
            input_path,
            output_format=output_format,
            identity=definition.get("identity"),
            require_physical_sph=contract_kind in _PHYSICAL_SPH_CONTRACTS,
        )
    return _component_row(
        definition,
        contract_kind,
        output_format,
        paths,
        native_sph,
        evidence,
        handoff,
        output,
    )


def _native_sph_execution_status(
    root: Path,
    definition: dict[str, Any],
) -> dict[str, str] | None:
    """Resolve declared runner inputs without implying that either one exists."""

    declaration = definition.get("native_sph")
    if not isinstance(declaration, dict):
        return None
    deck = declaration.get("deck")
    working_directory = declaration.get("working_directory")
    if not isinstance(deck, str) or not isinstance(working_directory, str):
        return None
    deck_path = _safe_relative_project_path(root, deck)
    working_path = _safe_relative_project_path(root, working_directory)
    if deck_path is None or working_path is None:
        return None
    return {
        "deck_path": str(deck_path),
        "working_directory": str(working_path),
    }


def _component_row(
    definition: dict[str, Any],
    contract_kind: str,
    output_format: str,
    paths: dict[str, Any],
    native_sph: dict[str, str] | None,
    evidence: dict[str, Any],
    handoff: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    metadata = definition.get("metadata") if isinstance(definition.get("metadata"), dict) else {}
    raw_conversion = (
        definition.get("conversion")
        if isinstance(definition.get("conversion"), dict)
        else {}
    )
    conversion_mixtures = raw_conversion.get("mixtures")
    conversion = {
        "writer_backend": str(raw_conversion.get("writer_backend", "ascii")),
        "root_name": (
            raw_conversion["root_name"]
            if isinstance(raw_conversion.get("root_name"), str)
            and raw_conversion["root_name"].strip()
            else "CPO"
        ),
        "comment": raw_conversion.get("comment"),
        "burnup": raw_conversion.get("burnup"),
        "h_factor_default": raw_conversion.get("h_factor_default"),
        "mixtures": list(conversion_mixtures)
        if isinstance(conversion_mixtures, list)
        else [],
    }
    return {
        "id": str(definition["id"]),
        "label": str(definition["label"]),
        "role": str(definition.get("role", "")),
        "required": bool(definition.get("required", True)),
        "contract": contract_kind,
        "format": output_format,
        "identity": definition.get("identity"),
        "metadata": metadata,
        "conversion": conversion,
        "paths": paths,
        "native_sph": native_sph,
        "evidence": evidence,
        "handoff": handoff,
        "output": output,
        # Compatibility aliases.
        "target": str(metadata.get("target", definition["label"])),
        "neighbors": str(metadata.get("neighbors", "")),
        "source_pair": evidence,
        "cpo": output,
    }


def _evidence_status(items: list[dict[str, str]]) -> dict[str, Any]:
    if not items:
        return {"state": "not-required", "issues": []}
    missing = [item["label"] for item in items if not Path(item["path"]).is_file()]
    if missing:
        return {"state": "missing", "issues": [f"missing {label}" for label in missing]}
    return {"state": "present", "issues": []}


def _handoff_status(path: Path, contract_kind: str) -> dict[str, Any]:
    if not path.is_file():
        return {"state": "missing", "issues": ["missing Converter input HDF5"]}
    try:
        if contract_kind == _NATIVE_SPH_CONTRACT:
            issues = native_sph_reference_issues(path)
        elif contract_kind in _COLORSET_SPH_CONTRACTS:
            issues = physical_colorset_sph_issues(path)
        elif contract_kind == _GENERIC_PHYSICAL_SPH_CONTRACT:
            issues = physical_sph_issues(path)
        else:
            import h5py

            issues = [] if h5py.is_hdf5(path) else ["Converter input is not an HDF5 file"]
    except (OSError, KeyError, ValueError) as exc:
        issues = [f"cannot validate Converter input: {exc}"]
    return {"state": "accepted" if not issues else "rejected", "issues": issues}


def _native_sph_output_status(
    output_path: Path,
    summary_path: Path,
    converter_receipt_path: Path | None,
    input_path: Path,
    *,
    identity: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Validate one live Converter -> native-SPH component result."""

    if not output_path.is_file():
        return {"state": "missing", "issues": ["missing native-SPH MACROLIB"]}
    if not summary_path.is_file():
        return {"state": "rejected", "issues": ["missing native-SPH physics summary"]}
    try:
        preview = output_path.read_text(encoding="utf-8", errors="replace")[:65_536]
        issues = [] if "L_MACROLIB" in preview.upper() else ["not a readable L_MACROLIB ASCII object"]
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {
                "state": "rejected",
                "issues": ["native-SPH physics summary is not a JSON object"],
            }
        issues.extend(_native_sph_acceptance_issues(payload))
        handoff = payload.get("handoff")
        if not isinstance(handoff, dict):
            issues.append("native-SPH physics summary has no handoff block")
        else:
            if not _same_path(handoff.get("macrolib_ascii_path"), output_path):
                issues.append("physics summary MACROLIB does not match the project output")
            if not _same_path(handoff.get("augmented_hdf5_path"), input_path):
                issues.append("physics summary Converter reference does not match the project input")
            if converter_receipt_path is None:
                issues.append(
                    "project does not declare a distinct Converter receipt for the "
                    "native-SPH reference MACROLIB"
                )
            elif not _same_path(
                handoff.get("converter_receipt_path"), converter_receipt_path
            ):
                issues.append(
                    "physics summary Converter receipt does not match the project receipt"
                )
            reference_macrolib_value = handoff.get("reference_macrolib_path")
            if not isinstance(reference_macrolib_value, str) or not reference_macrolib_value:
                issues.append("physics summary has no Converter reference MACROLIB path")
            elif converter_receipt_path is not None:
                reference_macrolib_path = Path(reference_macrolib_value).expanduser().resolve(
                    strict=False
                )
                issues.extend(
                    _converter_receipt_issues(
                        converter_receipt_path,
                        input_path,
                        reference_macrolib_path,
                        output_format="macrolib",
                        require_physical_sph=False,
                    )
                )
        mixture_names = payload.get("mixture_names")
        if isinstance(identity, str) and identity:
            if not isinstance(mixture_names, list) or identity not in mixture_names:
                issues.append(f"physics summary does not contain target component {identity}")
        expected_side = metadata.get("node_side_cm")
        if expected_side is not None:
            geometry = payload.get("geometry")
            actual_side = geometry.get("coarse_node_side_cm") if isinstance(geometry, dict) else None
            if actual_side is None or not math.isclose(
                float(actual_side), float(expected_side), rel_tol=0.0, abs_tol=1.0e-9
            ):
                issues.append(f"native-SPH node side does not match project declaration {expected_side} cm")
            if (
                not isinstance(geometry, dict)
                or geometry.get("homogenization_volume_includes_node_catchall") is not True
            ):
                issues.append("native-SPH homogenization does not cover the full project node")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        issues = [f"cannot validate native-SPH output: {exc}"]
    return {"state": "accepted" if not issues else "rejected", "issues": issues}


def _output_status(
    output_path: Path,
    receipt_path: Path,
    input_path: Path,
    *,
    output_format: str,
    identity: Any,
    require_physical_sph: bool,
) -> dict[str, Any]:
    if not output_path.is_file():
        return {"state": "missing", "issues": ["missing Converter output"]}
    try:
        preview = output_path.read_text(encoding="utf-8", errors="replace")[:65_536]
        issues = _converted_output_issues(preview, output_format, identity)
        issues.extend(
            _converter_receipt_issues(
                receipt_path,
                input_path,
                output_path,
                output_format=output_format,
                require_physical_sph=require_physical_sph,
            )
        )
    except OSError as exc:
        issues = [f"cannot read Converter output: {exc}"]
    return {"state": "accepted" if not issues else "rejected", "issues": issues}


def _converted_output_issues(text: str, output_format: str, identity: Any) -> list[str]:
    issues: list[str] = []
    upper = text.upper()
    expected = "L_MULTICOMPO" if output_format == "multicompo" else "L_MACROLIB"
    if "SIGNATURE" not in upper or expected not in upper:
        issues.append(f"not a readable {expected} ASCII object")
    if isinstance(identity, str) and identity and identity.lower() not in text.lower():
        issues.append(f"Converter output comment does not record identity {identity}")
    return issues


def _converter_receipt_issues(
    receipt_path: Path,
    input_path: Path,
    output_path: Path,
    *,
    output_format: str,
    require_physical_sph: bool,
) -> list[str]:
    if not receipt_path.is_file():
        return ["missing hash-linked Converter receipt"]
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read Converter receipt: {exc}"]
    if not isinstance(payload, dict):
        return ["Converter receipt must be a JSON object"]

    issues: list[str] = []
    if payload.get("schema") != "openmc2donjon.convert.v1":
        issues.append("Converter receipt schema is not recognized")
    if not payload.get("ok") or not payload.get("converted") or payload.get("dry_run"):
        issues.append("Converter receipt does not record a completed conversion")
    issues.extend(production_receipt_policy_issues(payload))
    if payload.get("preflight_ok") is not True:
        issues.append("Converter receipt does not record a passing MGXS preflight")
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        issues.append("Converter receipt has no auditable MGXS preflight object")
    else:
        if preflight.get("schema") != "openmc2donjon.mgxs-input-contract.v1":
            issues.append("Converter receipt MGXS preflight schema is not recognized")
        if preflight.get("decision") != "mgxs_input_contract_passed":
            issues.append("Converter receipt MGXS preflight decision did not pass")
        preflight_inputs = preflight.get("inputs")
        if not isinstance(preflight_inputs, list) or not preflight_inputs:
            issues.append("Converter receipt MGXS preflight has no input results")
        elif any(
            not isinstance(item, dict) or item.get("ok") is not True
            for item in preflight_inputs
        ):
            issues.append("Converter receipt MGXS preflight contains a failed input")
    if payload.get("format") != output_format:
        issues.append("Converter receipt format does not match the project component")
    if require_physical_sph and not payload.get("physical_sph_required"):
        issues.append("Converter receipt did not enforce the physical SPH contract")
    if not _same_path(payload.get("input_path"), input_path):
        issues.append("Converter receipt input path does not match this component input")
    if not _same_path(payload.get("output_path"), output_path):
        issues.append("Converter receipt output path does not match this component output")
    if payload.get("input_sha256") != _file_sha256(input_path):
        issues.append("Converter input hash no longer matches the project handoff")
    if payload.get("output_sha256") != _file_sha256(output_path):
        issues.append("Converter output hash no longer matches the project artifact")
    return issues


def _consumer_status(
    root: Path,
    consumer: Any,
    *,
    mock_mode: bool,
) -> dict[str, Any]:
    if not isinstance(consumer, dict):
        return {
            "kind": "external",
            "label": "External consumer",
            "href": "/donjon",
            "runs": [],
        }
    runs: list[dict[str, Any]] = []
    for index, item in enumerate(consumer.get("runs", [])):
        if not isinstance(item, dict):
            continue
        result_path = _safe_project_path(root, str(item.get("result", "")))
        deck_path = _safe_project_path(root, str(item.get("deck", "")))
        k_effective: float | None = None
        completed = False
        if not mock_mode and result_path is not None and result_path.is_file():
            completed = True
            try:
                k_effective = parse_donjon_k_effective(
                    result_path.read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                k_effective = None
        runs.append(
            {
                "id": str(item.get("id", f"run-{index + 1}")),
                "label": str(item.get("label", item.get("id", f"Run {index + 1}"))),
                "state": "completed" if completed else "missing",
                "deck_path": None if deck_path is None else str(deck_path),
                "result_path": None if result_path is None else str(result_path),
                "k_effective": k_effective,
            }
        )
    return {
        "kind": str(consumer.get("kind", "external")),
        "label": str(consumer.get("label", "External consumer")),
        "href": consumer.get("href", "/donjon"),
        "runs": runs,
    }


def _acceptance_status(
    root: Path,
    definition: Any,
    *,
    components: list[dict[str, Any]],
    components_ready: bool,
    mock_mode: bool,
) -> dict[str, Any]:
    """Read a project-owned, model-specific acceptance decision.

    Converter never invents observables or tolerances.  The project decision
    names its own criteria and hash-linkable evidence; this reader only checks
    that the ledger is structurally complete and that referenced files exist.
    """

    if not isinstance(definition, dict):
        return _empty_acceptance_status()
    machine_validation = _machine_acceptance_status(
        root,
        definition.get("validator"),
        components=components,
        mock_mode=mock_mode,
    )
    basis = (
        "machine-verified"
        if machine_validation["declared"]
        else "project-declared"
    )
    decision_path = _safe_project_path(root, str(definition.get("decision", "")))
    if decision_path is None:
        status = _empty_acceptance_status()
        status.update(
            {
                "declared": True,
                "basis": basis,
                "state": "invalid",
                "issues": ["acceptance decision path is invalid"],
                "machine_validation": machine_validation,
            }
        )
        return status
    base = {
        "declared": True,
        "basis": basis,
        "state": "missing",
        "decision_path": str(decision_path),
        "decision_sha256": None,
        "summary": "",
        "criteria": [],
        "issues": [],
        "machine_validation": machine_validation,
    }
    if mock_mode or not decision_path.is_file():
        base["issues"] = ["missing project acceptance decision"]
        return base
    try:
        payload = json.loads(decision_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base.update(state="invalid", issues=[f"cannot read acceptance decision: {exc}"])
        return base
    if not isinstance(payload, dict):
        base.update(state="invalid", issues=["acceptance decision must be a JSON object"])
        return base

    issues: list[str] = []
    if payload.get("schema") != ACCEPTANCE_DECISION_SCHEMA:
        issues.append(f"acceptance schema must be {ACCEPTANCE_DECISION_SCHEMA}")
    requested_state = payload.get("status")
    if requested_state not in {"pending", "accepted", "rejected"}:
        issues.append("acceptance status must be pending, accepted, or rejected")
        requested_state = "pending"
    raw_criteria = payload.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        issues.append("acceptance criteria must be a non-empty array")
        raw_criteria = []

    criteria: list[dict[str, Any]] = []
    criterion_ids: set[str] = set()
    for index, item in enumerate(raw_criteria):
        prefix = f"criteria[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be an object")
            continue
        criterion_id = item.get("id")
        label = item.get("label")
        criterion_state = item.get("status")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            issues.append(f"{prefix}.id must be a non-empty string")
            criterion_id = f"criterion-{index + 1}"
        elif criterion_id in criterion_ids:
            issues.append(f"duplicate acceptance criterion id: {criterion_id}")
        criterion_ids.add(str(criterion_id))
        if not isinstance(label, str) or not label.strip():
            issues.append(f"{prefix}.label must be a non-empty string")
            label = str(criterion_id)
        if criterion_state not in {"pending", "passed", "failed"}:
            issues.append(f"{prefix}.status must be pending, passed, or failed")
            criterion_state = "pending"
        evidence_rows: list[dict[str, Any]] = []
        raw_evidence = item.get("evidence", [])
        if not isinstance(raw_evidence, list):
            issues.append(f"{prefix}.evidence must be an array")
            raw_evidence = []
        for evidence_index, evidence in enumerate(raw_evidence):
            evidence_prefix = f"{prefix}.evidence[{evidence_index}]"
            if not isinstance(evidence, dict):
                issues.append(f"{evidence_prefix} must be an object")
                continue
            raw_path = evidence.get("path")
            path = _safe_project_path(root, raw_path) if isinstance(raw_path, str) else None
            if path is None:
                issues.append(f"{evidence_prefix}.path must stay inside the project root")
                continue
            actual_hash = None if mock_mode else _file_sha256(path)
            expected_hash = evidence.get("sha256")
            evidence_state = "present" if actual_hash is not None else "missing"
            if actual_hash is None:
                issues.append(f"missing acceptance evidence: {path}")
            elif not _is_sha256(expected_hash):
                evidence_state = "hash-unverified"
                issues.append(
                    f"acceptance evidence sha256 must be a 64-character hex digest: {path}"
                )
            elif expected_hash.lower() != actual_hash:
                evidence_state = "hash-mismatch"
                issues.append(f"acceptance evidence hash mismatch: {path}")
            evidence_rows.append(
                {
                    "label": str(evidence.get("label", path.name)),
                    "path": str(path),
                    "state": evidence_state,
                    "sha256": actual_hash,
                }
            )
        if criterion_state == "passed" and not evidence_rows:
            issues.append(f"{prefix} is passed but has no declared evidence")
        criteria.append(
            {
                "id": str(criterion_id),
                "label": str(label),
                "status": str(criterion_state),
                "evidence": evidence_rows,
            }
        )

    failed = any(item["status"] == "failed" for item in criteria)
    all_passed = bool(criteria) and all(item["status"] == "passed" for item in criteria)
    machine_state = machine_validation["state"]
    machine_required = machine_validation["declared"]
    machine_passed = not machine_required or machine_state == "passed"
    structural_failure = bool(issues) or machine_state == "invalid"
    if structural_failure:
        state = "invalid"
    elif requested_state == "rejected" or failed or machine_state == "rejected":
        state = "rejected"
    elif (
        requested_state == "accepted"
        and components_ready
        and all_passed
        and machine_passed
    ):
        state = "accepted"
    else:
        state = "pending"
        if requested_state == "accepted" and not components_ready:
            issues.append("acceptance cannot close until required Converter outputs are ready")
        if requested_state == "accepted" and not all_passed:
            issues.append("acceptance cannot close until every declared criterion passes")
        if requested_state == "accepted" and not machine_passed:
            issues.append(
                "acceptance cannot close until the declared machine validator passes"
            )

    base.update(
        state=state,
        decision_sha256=_file_sha256(decision_path),
        summary=str(payload.get("summary", "")),
        criteria=criteria,
        issues=[*issues, *machine_validation["issues"]],
    )
    return base


def _machine_acceptance_status(
    root: Path,
    definition: Any,
    *,
    components: list[dict[str, Any]],
    mock_mode: bool,
) -> dict[str, Any]:
    """Verify a declared model-specific machine acceptance summary.

    This is intentionally a small contract dispatcher, not a generic physics
    oracle.  Projects without a validator retain project-owned external
    acceptance.  The strict IRENA contract additionally binds a file-backed
    full-core validator result to the live project component and native-SPH
    summary before the project ledger can close.
    """

    if not isinstance(definition, dict):
        return _empty_machine_validation_status()
    contract = definition.get("contract")
    raw_summary = definition.get("summary")
    summary_path = (
        _safe_project_path(root, raw_summary)
        if isinstance(raw_summary, str)
        else None
    )
    base: dict[str, Any] = {
        "declared": True,
        "contract": contract if isinstance(contract, str) else None,
        "component": (
            definition.get("component")
            if isinstance(definition.get("component"), str)
            else None
        ),
        "state": "missing",
        "summary_path": None if summary_path is None else str(summary_path),
        "summary_sha256": None,
        "checks_passed": 0,
        "checks_total": 0,
        "evidence": [],
        "issues": [],
    }
    if contract != IRENA30_FULLCORE_VALIDATOR_CONTRACT:
        base.update(
            state="invalid",
            issues=[
                "unsupported acceptance machine-validator contract: "
                f"{contract!r}"
            ],
        )
        return base
    if summary_path is None:
        base.update(
            state="invalid",
            issues=["machine-validator summary path is invalid"],
        )
        return base
    if mock_mode or not summary_path.is_file():
        base["issues"] = [f"missing machine-validator summary: {summary_path}"]
        return base

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        base.update(
            state="invalid",
            issues=[f"cannot read machine-validator summary: {exc}"],
        )
        return base
    if not isinstance(payload, dict):
        base.update(
            state="invalid",
            issues=["machine-validator summary must be a JSON object"],
        )
        return base

    structural_issues: list[str] = []
    rejection_issues: list[str] = []
    if payload.get("schema") != IRENA30_FULLCORE_PHYSICS_SCHEMA:
        structural_issues.append(
            "machine-validator schema must be "
            f"{IRENA30_FULLCORE_PHYSICS_SCHEMA}"
        )
    if payload.get("decision") != IRENA30_FULLCORE_PASSED_DECISION:
        rejection_issues.append(
            "machine-validator decision did not pass strict IRENA full-core physics"
        )

    checks = payload.get("acceptance_checks")
    if not isinstance(checks, dict) or not checks:
        structural_issues.append(
            "machine-validator summary needs non-empty acceptance_checks"
        )
        checks = {}
    non_boolean_checks = [
        str(key) for key, value in checks.items() if not isinstance(value, bool)
    ]
    failed_checks = [str(key) for key, value in checks.items() if value is False]
    if non_boolean_checks:
        structural_issues.append(
            "machine-validator acceptance checks must be boolean: "
            + ", ".join(non_boolean_checks)
        )
    if failed_checks:
        rejection_issues.append(
            "machine-validator acceptance checks failed: "
            + ", ".join(failed_checks)
        )
    base["checks_total"] = len(checks)
    base["checks_passed"] = sum(value is True for value in checks.values())

    evidence = payload.get("evidence")
    hashes: Any = None
    if not isinstance(evidence, dict):
        structural_issues.append("machine-validator summary has no evidence object")
        evidence = {}
    else:
        hashes = evidence.get("input_sha256")
    if not isinstance(hashes, dict) or not hashes:
        structural_issues.append(
            "machine-validator summary has no input_sha256 evidence manifest"
        )
        hashes = {}

    required_evidence = {
        "physics_summary",
        "reference_h5",
        "region_verify",
        "edi_output",
        "result_listing",
    }
    missing_evidence = sorted(required_evidence - set(hashes))
    if missing_evidence:
        structural_issues.append(
            "machine-validator input_sha256 is incomplete: "
            + ", ".join(missing_evidence)
        )

    resolved_evidence: dict[str, Path] = {}
    evidence_rows: list[dict[str, Any]] = []
    for label, expected_hash in hashes.items():
        if not isinstance(label, str) or not label:
            structural_issues.append(
                "machine-validator input_sha256 keys must be non-empty strings"
            )
            continue
        raw_path = evidence.get(label)
        path = (
            _safe_project_path(root, raw_path)
            if isinstance(raw_path, str)
            else None
        )
        actual_hash = None if path is None or mock_mode else _file_sha256(path)
        state = "present"
        if path is None:
            state = "invalid-path"
            structural_issues.append(
                f"machine-validator evidence path is missing or outside the project: {label}"
            )
        elif actual_hash is None:
            state = "missing"
            structural_issues.append(
                f"machine-validator evidence file is missing: {label}: {path}"
            )
        elif not _is_sha256(expected_hash):
            state = "hash-unverified"
            structural_issues.append(
                f"machine-validator evidence hash is invalid: {label}"
            )
        elif expected_hash.lower() != actual_hash:
            state = "hash-mismatch"
            structural_issues.append(
                f"machine-validator evidence hash mismatch: {label}: {path}"
            )
        if path is not None:
            resolved_evidence[label] = path
        evidence_rows.append(
            {
                "id": label,
                "path": None if path is None else str(path),
                "state": state,
                "sha256": actual_hash,
            }
        )
    base["evidence"] = evidence_rows

    component = _machine_validator_component(definition, components)
    if component is None:
        structural_issues.append(
            "machine-validator component must identify exactly one native-sph project component"
        )
    else:
        component_id = str(component["id"])
        base["component"] = component_id
        input_path = _safe_project_path(root, str(component["input"]))
        output_path = _safe_project_path(root, str(component["output"]))
        physics_summary_value = component.get("physics_summary")
        physics_summary_path = (
            _safe_project_path(root, physics_summary_value)
            if isinstance(physics_summary_value, str)
            else None
        )
        assert input_path is not None and output_path is not None
        if physics_summary_path is None:
            structural_issues.append(
                "machine-validator component must declare physics_summary separately "
                "from its Converter receipt"
            )
        if resolved_evidence.get("reference_h5") != input_path:
            structural_issues.append(
                "machine-validator reference_h5 is not the declared project component input"
            )
        if resolved_evidence.get("physics_summary") != physics_summary_path:
            structural_issues.append(
                "machine-validator physics_summary is not the declared component physics_summary"
            )
        component_evidence_paths = {
            _safe_project_path(root, str(item.get("path", "")))
            for item in component.get("evidence", [])
            if isinstance(item, dict)
        }
        if summary_path not in component_evidence_paths:
            structural_issues.append(
                "machine-validator summary is not declared as component evidence"
            )
        native_summary_path = resolved_evidence.get("physics_summary")
        if native_summary_path is not None and native_summary_path.is_file():
            structural_issues.extend(
                _machine_native_summary_binding_issues(
                    native_summary_path,
                    input_path=input_path,
                    output_path=output_path,
                    fullcore_payload=payload,
                )
            )

    base["summary_sha256"] = _file_sha256(summary_path)
    if structural_issues:
        state = "invalid"
    elif rejection_issues:
        state = "rejected"
    else:
        state = "passed"
    base.update(
        state=state,
        issues=[*structural_issues, *rejection_issues],
    )
    return base


def _machine_validator_component(
    definition: dict[str, Any],
    components: list[dict[str, Any]],
) -> dict[str, Any] | None:
    requested = definition.get("component")
    if isinstance(requested, str) and requested:
        candidates = [item for item in components if item.get("id") == requested]
    else:
        candidates = []
        for item in components:
            contract = item.get("contract", "converter-hdf5")
            contract_kind = contract.get("kind") if isinstance(contract, dict) else contract
            if contract_kind == _NATIVE_SPH_CONTRACT:
                candidates.append(item)
    if len(candidates) != 1:
        return None
    component = candidates[0]
    contract = component.get("contract", "converter-hdf5")
    contract_kind = contract.get("kind") if isinstance(contract, dict) else contract
    return component if contract_kind == _NATIVE_SPH_CONTRACT else None


def _machine_native_summary_binding_issues(
    path: Path,
    *,
    input_path: Path,
    output_path: Path,
    fullcore_payload: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read bound native-SPH summary: {exc}"]
    if not isinstance(payload, dict):
        return ["bound native-SPH summary must be a JSON object"]
    if payload.get("schema") != NATIVE_SPH_PHYSICS_SCHEMA:
        issues.append("bound physics_summary is not a native-SPH physics summary")
    handoff = payload.get("handoff")
    if not isinstance(handoff, dict):
        issues.append("bound native-SPH summary has no handoff object")
    else:
        if not _same_path(handoff.get("augmented_hdf5_path"), input_path):
            issues.append(
                "bound native-SPH summary does not use the project component input"
            )
        if not _same_path(handoff.get("macrolib_ascii_path"), output_path):
            issues.append(
                "bound native-SPH summary does not produce the project component output"
            )
    native_record = fullcore_payload.get("native_sph")
    if not isinstance(native_record, dict):
        issues.append("machine-validator summary has no native_sph binding record")
    else:
        if native_record.get("summary_schema") != payload.get("schema"):
            issues.append(
                "machine-validator native_sph summary_schema does not match the bound summary"
            )
        quality = payload.get("quality")
        native_decision = quality.get("decision") if isinstance(quality, dict) else None
        if native_record.get("summary_decision") != native_decision:
            issues.append(
                "machine-validator native_sph summary_decision does not match the bound summary"
            )
    return issues


def _empty_machine_validation_status() -> dict[str, Any]:
    return {
        "declared": False,
        "contract": None,
        "component": None,
        "state": "not-declared",
        "summary_path": None,
        "summary_sha256": None,
        "checks_passed": 0,
        "checks_total": 0,
        "evidence": [],
        "issues": [],
    }


def _empty_acceptance_status() -> dict[str, Any]:
    return {
        "declared": False,
        "basis": "not-required",
        "state": "not-required",
        "decision_path": None,
        "decision_sha256": None,
        "summary": "",
        "criteria": [],
        "issues": [],
        "machine_validation": _empty_machine_validation_status(),
    }


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _starter_manifest(
    name: str,
    *,
    acceptance_mode: str,
    writer_backend: str = "ascii",
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": PROJECT_MANIFEST_SCHEMA,
        "name": name,
        "description": "Generic Converter project. Edit the component array for this model.",
        "workflow": "component-library",
        "acceptance_mode": acceptance_mode,
        "components": [
            {
                "id": "component-1",
                "label": "Component 1",
                "role": "User-defined homogenized component or model region",
                "required": True,
                "input": "components/component-1/mgxs_library.h5",
                "output": "outputs/component-1.mcompo.txt",
                "format": "multicompo",
                "contract": "converter-hdf5",
                "conversion": {"writer_backend": writer_backend},
            }
        ],
        "consumer": {
            "kind": "external",
            "label": "User-supplied DRAGON/DONJON model",
            "href": "/donjon",
        },
    }
    if acceptance_mode == "physics-gated":
        manifest["acceptance"] = {"decision": "acceptance/decision.json"}
    return manifest


def _starter_acceptance_decision() -> dict[str, Any]:
    return {
        "schema": ACCEPTANCE_DECISION_SCHEMA,
        "status": "pending",
        "summary": "Define this model's independent physics acceptance criteria and evidence.",
        "criteria": [
            {
                "id": "physics-closure",
                "label": "Project-defined physics closure",
                "status": "pending",
                "evidence": [],
            }
        ],
    }


def _legacy_core_status(consumer: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["id"]: item for item in consumer.get("runs", [])}
    missing = {"state": "missing", "deck_path": "", "result_path": "", "k_effective": None}
    return {
        "directory": "",
        "sn": by_id.get("sn", missing),
        "spn": by_id.get("spn", missing),
        "closure_state": "pending-reference-comparison",
    }


def _safe_project_path(root: Path, value: str) -> Path | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    project_root = root.resolve(strict=False)
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return None
    return resolved


def _safe_relative_project_path(root: Path, value: str) -> Path | None:
    """Resolve a project path only when its manifest spelling is relative."""

    if not value:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or (
        candidate.parts and candidate.parts[0].startswith("~")
    ):
        return None
    try:
        return _safe_project_path(root, value)
    except (OSError, RuntimeError, ValueError):
        return None


def _same_path(value: Any, expected: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return Path(value).expanduser().resolve(strict=False) == expected.resolve(strict=False)


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
