"""Read-only web endpoint for OpenMC/DRAGON SPH physics summaries."""

from __future__ import annotations

import hashlib
import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from ..native_sph_validation import (
    converter_receipt_issues,
    native_sph_correction_policy_evidence,
)
from ..openmc_provenance import read_openmc_provenance
from .filesystem import FilesystemScope


OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA = "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1"
NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA = (
    "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1"
)
_LEGACY_OPENMC_SPH_PHYSICS_SUMMARY_SCHEMAS = {
    "openmc2donjon.openmc-ce-mg-33g-sph-physics-summary.v1",
}


def register_openmc_sph_summary_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope | None = None,
) -> None:
    """Register ``/api/openmc-sph-summary`` on a FastAPI app."""

    from fastapi import HTTPException, Query

    scope = filesystem_scope or FilesystemScope()

    @app.get("/api/openmc-sph-summary")
    def api_openmc_sph_summary(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            payload = _load_fixture_summary()
            payload = dict(payload)
            payload["requested_path"] = path
            _validate_summary_payload(payload, HTTPException)
            payload["evidence_audit"] = _build_evidence_audit(
                payload,
                summary_path=None,
                mock_mode=True,
                filesystem_scope=scope,
            )
            return payload

        real_path = _validate_json_path(path, HTTPException, scope)
        try:
            payload = json.loads(real_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"OpenMC SPH physics summary read failed: {exc}",
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=422,
                detail="OpenMC SPH physics summary is not a JSON object",
            )
        payload["requested_path"] = str(real_path)
        _validate_summary_payload(payload, HTTPException)
        payload["evidence_audit"] = _build_evidence_audit(
            payload,
            summary_path=real_path,
            mock_mode=False,
            filesystem_scope=scope,
        )
        return payload


def _build_evidence_audit(
    payload: dict[str, Any],
    *,
    summary_path: Path | None,
    mock_mode: bool,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any]:
    """Describe evidence provenance without inferring physics acceptance.

    A statistically clean summary may still be a bundled fixture or point at
    artifacts that no longer exist.  The web UI needs those facts separately
    from the workflow's own quality flag so it cannot present a copied JSON
    snapshot as a currently reproducible physics result.
    """

    handoff = payload.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}
    native = payload.get("schema") == NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA
    if native:
        declared_specs = {
            "reference_hdf5": (
                "augmented_hdf5_path",
                handoff.get("augmented_hdf5_path"),
            ),
            "reference_macrolib": (
                "reference_macrolib_path",
                handoff.get("reference_macrolib_path"),
            ),
            "sph_macrolib": (
                "macrolib_ascii_path",
                handoff.get("macrolib_ascii_path") or handoff.get("ascii_path"),
            ),
            "verification_macrolib": (
                "verification_macrolib_path",
                handoff.get("verification_macrolib_path"),
            ),
            "donjon_result": (
                "result_listing_path",
                handoff.get("result_listing_path"),
            ),
            "energy_coverage": (
                "energy_coverage_path",
                handoff.get("energy_coverage_path"),
            ),
            "converter_receipt": (
                "converter_receipt_path",
                handoff.get("converter_receipt_path"),
            ),
            "execution_deck": (
                "execution_deck_path",
                handoff.get("execution_deck_path"),
            ),
        }
    else:
        declared_specs = {
            "augmented_hdf5": (None, handoff.get("augmented_hdf5_path")),
            "ascii": (None, _accepted_ascii_path(handoff)),
        }
    fixture_paths = any(
        isinstance(value, str) and value.strip().startswith("/mock/")
        for _, value in declared_specs.values()
    )
    if mock_mode:
        origin = "mock_fixture"
    elif fixture_paths:
        origin = "recorded_fixture"
    else:
        origin = "live_file"

    evidence_manifest = handoff.get("evidence_sha256")
    if not isinstance(evidence_manifest, dict):
        evidence_manifest = {}
    artifacts = []
    for label, (manifest_key, raw_path) in declared_specs.items():
        expected_sha256 = (
            None if manifest_key is None else evidence_manifest.get(manifest_key)
        )
        artifacts.append(
            _probe_evidence_artifact(
                label=label,
                raw_path=raw_path,
                manifest_key=manifest_key,
                expected_sha256=expected_sha256,
                mock_mode=mock_mode,
                filesystem_scope=filesystem_scope,
            )
        )
    statuses = [item["status"] for item in artifacts]
    all_present: bool | None
    if mock_mode:
        all_present = None
    else:
        all_present = bool(statuses) and all(status == "present" for status in statuses)

    if not native or mock_mode:
        evidence_integrity = {
            "verified": None if mock_mode else False,
            "issues": [],
            "handoff_sha256_manifest_complete": None,
            "all_handoff_sha256_match": None,
            "converter_receipt": None,
            "openmc_provenance": None,
            "forbidden_corrections": None,
        }
        all_hash_verified: bool | None = None
    else:
        evidence_integrity = _audit_native_evidence_integrity(
            artifacts=artifacts,
            declared_specs=declared_specs,
            filesystem_scope=filesystem_scope,
        )
        all_hash_verified = evidence_integrity["all_handoff_sha256_match"]

    physics_acceptance = _physics_acceptance(
        payload,
        native=native,
        mock_mode=mock_mode,
        all_present=all_present,
        evidence_integrity=evidence_integrity,
    )
    return {
        "origin": origin,
        "summary_path": str(summary_path) if summary_path is not None else None,
        "summary_file_present": summary_path is not None and summary_path.is_file(),
        "referenced_handoff_artifacts": artifacts,
        "all_referenced_handoff_artifacts_present": all_present,
        "all_referenced_handoff_artifacts_hash_verified": all_hash_verified,
        "evidence_integrity": evidence_integrity,
        "physics_acceptance": physics_acceptance,
        "reactor_acceptance": "not_evaluated",
    }


def _audit_native_evidence_integrity(
    *,
    artifacts: list[dict[str, Any]],
    declared_specs: dict[str, tuple[str | None, Any]],
    filesystem_scope: FilesystemScope,
) -> dict[str, Any]:
    """Revalidate native-SPH evidence against live bytes on every read."""

    del declared_specs  # Paths in ``artifacts`` are already scope-enforced.
    issues: list[str] = []
    by_label = {str(item["label"]): item for item in artifacts}
    manifest_complete = True
    all_hashes_match = True
    for item in artifacts:
        label = str(item["label"])
        expected = item.get("expected_sha256")
        if not _is_sha256(expected):
            manifest_complete = False
            all_hashes_match = False
            issues.append(f"{label} has no valid handoff.evidence_sha256 entry")
        if item.get("status") != "present":
            all_hashes_match = False
            issues.append(f"{label} is not a live readable file")
        elif item.get("hash_matches") is not True:
            all_hashes_match = False
            issues.append(f"{label} SHA-256 does not match the physics summary")

    resolved = {
        label: _artifact_path(item, filesystem_scope)
        for label, item in by_label.items()
    }
    receipt_issues: list[str]
    receipt_path = resolved.get("converter_receipt")
    reference_h5 = resolved.get("reference_hdf5")
    reference_macrolib = resolved.get("reference_macrolib")
    if receipt_path is None or reference_h5 is None or reference_macrolib is None:
        receipt_issues = [
            "Converter receipt, reference HDF5, and reference MACROLIB must all be live files"
        ]
    else:
        receipt_issues = converter_receipt_issues(
            receipt_path,
            reference_h5=reference_h5,
            reference_macrolib=reference_macrolib,
        )
    issues.extend(f"Converter receipt: {issue}" for issue in receipt_issues)

    provenance_issues: list[str] = []
    provenance_status: str | None = None
    provenance_digest: str | None = None
    payload_digest: str | None = None
    if reference_h5 is None:
        provenance_issues.append("reference HDF5 is not a live readable file")
    else:
        try:
            provenance = read_openmc_provenance(reference_h5)
        except (OSError, TypeError, ValueError, KeyError, IndexError) as exc:
            provenance_issues.append(f"cannot read embedded OpenMC provenance: {exc}")
        else:
            provenance_status = str(provenance.get("status") or "unknown")
            provenance_digest = _optional_string(provenance.get("digest_sha256"))
            handoff = provenance.get("handoff")
            if isinstance(handoff, dict):
                payload_digest = _optional_string(handoff.get("payload_sha256"))
            integrity = provenance.get("integrity")
            capabilities = provenance.get("capabilities")
            if not isinstance(integrity, dict) or integrity.get("ok") is not True:
                provenance_issues.append(
                    "embedded OpenMC provenance or MGXS payload digest is invalid"
                )
            if not isinstance(capabilities, dict) or capabilities.get(
                "reference_bound"
            ) is not True:
                provenance_issues.append(
                    "reference HDF5 is not bound to an OpenMC fine-reference chain"
                )
            if not isinstance(capabilities, dict) or capabilities.get(
                "transport_reproducible"
            ) is not True:
                provenance_issues.append(
                    "OpenMC transport input closure is not reproducible"
                )
    issues.extend(f"OpenMC provenance: {issue}" for issue in provenance_issues)

    correction_policy: dict[str, Any] | None = None
    correction_issues: list[str] = []
    correction_inputs = {
        "reference_h5": resolved.get("reference_hdf5"),
        "reference_macrolib": resolved.get("reference_macrolib"),
        "sph_macrolib": resolved.get("sph_macrolib"),
        "verify_macrolib": resolved.get("verification_macrolib"),
        "result_listing": resolved.get("donjon_result"),
        "execution_deck": resolved.get("execution_deck"),
    }
    if any(path is None for path in correction_inputs.values()):
        correction_issues.append(
            "all MACROLIB, listing, reference HDF5, and execution-deck files are required"
        )
    else:
        try:
            correction_policy = native_sph_correction_policy_evidence(
                **correction_inputs
            )
        except (OSError, TypeError, ValueError, KeyError, IndexError) as exc:
            correction_issues.append(f"cannot audit correction policy: {exc}")
        else:
            if correction_policy.get("status") != "verified_absent":
                policy_issues = correction_policy.get("issues")
                if isinstance(policy_issues, list) and policy_issues:
                    correction_issues.extend(str(issue) for issue in policy_issues)
                else:
                    correction_issues.append(
                        "absence of ADF and empirical eigenvalue factors is not proved"
                    )
    issues.extend(
        f"Forbidden-correction policy: {issue}" for issue in correction_issues
    )

    verified = bool(
        manifest_complete
        and all_hashes_match
        and not receipt_issues
        and not provenance_issues
        and not correction_issues
        and correction_policy is not None
        and correction_policy.get("status") == "verified_absent"
    )
    return {
        "verified": verified,
        "issues": issues,
        "handoff_sha256_manifest_complete": manifest_complete,
        "all_handoff_sha256_match": all_hashes_match,
        "converter_receipt": {
            "valid": not receipt_issues,
            "issues": receipt_issues,
        },
        "openmc_provenance": {
            "valid": not provenance_issues,
            "status": provenance_status,
            "digest_sha256": provenance_digest,
            "payload_sha256": payload_digest,
            "issues": provenance_issues,
        },
        "forbidden_corrections": correction_policy
        or {
            "status": "not_provable",
            "issues": correction_issues,
        },
    }


def _artifact_path(
    item: dict[str, Any], filesystem_scope: FilesystemScope
) -> Path | None:
    if item.get("status") != "present" or not isinstance(item.get("path"), str):
        return None
    try:
        return filesystem_scope.enforce(Path(item["path"]), _EvidenceScopeError)
    except _EvidenceScopeError:
        return None


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and re.fullmatch(r"[0-9a-fA-F]{64}", value)
    )


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _physics_acceptance(
    payload: dict[str, Any],
    *,
    native: bool,
    mock_mode: bool,
    all_present: bool | None,
    evidence_integrity: dict[str, Any] | None = None,
) -> str:
    """Return only the acceptance explicitly established by the native validator."""

    if not native or mock_mode:
        return "not_evaluated"
    checks = payload.get("acceptance_checks")
    quality = payload.get("quality")
    native_state = payload.get("native_sph")
    eigenvalue = payload.get("eigenvalue_validation")
    geometry = payload.get("geometry")
    sph = payload.get("sph")
    if not all(
        isinstance(item, dict)
        for item in (checks, quality, native_state, eigenvalue, geometry, sph)
    ):
        return "failed"
    positive = (
        "donjon_normal_end",
        "native_sph_converged",
        "native_sph_factors_unmodified",
        "native_sph_not_stopped_by_oscillation",
        "one_speed_convergence_provable",
        "final_flux_solve_converged",
        "energy_coverage_passed",
        "leakage_balance_available_when_required",
        "reference_physical_balance_within_openmc_uncertainty",
        "donjon_keff_within_openmc_uncertainty",
    )
    boundary = str(geometry.get("boundary_conditions") or "").lower()
    balance_kind = eigenvalue.get("reference_physical_balance_kind")
    physical_balance_fields_present = all(
        isinstance(eigenvalue.get(key), (int, float))
        and not isinstance(eigenvalue.get(key), bool)
        for key in (
            "reference_physical_balance_keff",
            "reference_physical_balance_delta_pcm",
            "reference_physical_balance_z",
            "reference_collision_balance_kinf",
        )
    )
    if balance_kind == "finite-domain-keff":
        balance_contract_valid = (
            eigenvalue.get("reference_finite_balance_available") is True
            and isinstance(eigenvalue.get("reference_finite_balance_keff"), (int, float))
            and isinstance(eigenvalue.get("reference_leakage"), (int, float))
        )
    elif balance_kind == "collision-balance-kinf":
        balance_contract_valid = "vacuum" not in boundary
    else:
        balance_contract_valid = False
    native_records_valid = (
        native_state.get("normal_end") is True
        and native_state.get("converged") is True
        and native_state.get("one_speed_convergence_provable") is True
        and native_state.get("final_flux_solve_converged") is True
        and native_state.get("factors_unmodified") is True
        and native_state.get("flux_nonconvergence_count") == 0
        and native_state.get("negative_factor_correction_count") == 0
        and native_state.get("oscillation_stop_count", 0) == 0
    )
    # Every consumer must explicitly supply its live re-hash/receipt/provenance
    # audit.  Omitting the audit is not backward-compatible evidence and must
    # fail closed rather than inheriting a stored production-ready boolean.
    integrity_verified = bool(
        evidence_integrity is not None
        and evidence_integrity.get("verified") is True
    )
    passed = (
        all_present is True
        and integrity_verified
        and quality.get("production_ready") is True
        and quality.get("structural_passed") is True
        and all(checks.get(key) is True for key in positive)
        and native_records_valid
        and physical_balance_fields_present
        and balance_contract_valid
        and sph.get("clipped_count") == 0
        and checks.get("empirical_eigenvalue_multiplier_used") is False
        and checks.get("adf_used") is False
    )
    return "passed" if passed else "failed"


def _accepted_ascii_path(handoff: dict[str, Any]) -> Any:
    accepted = str(handoff.get("accepted_sph_consumption_format") or "").lower()
    if accepted == "macrolib":
        return handoff.get("macrolib_ascii_path") or handoff.get("ascii_path")
    if accepted == "multicompo":
        return handoff.get("multicompo_ascii_path") or handoff.get("ascii_path")
    return handoff.get("ascii_path")


def _probe_evidence_artifact(
    *,
    label: str,
    raw_path: Any,
    manifest_key: str | None,
    expected_sha256: Any,
    mock_mode: bool,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return {
            "label": label,
            "path": None,
            "status": "not_declared",
            "manifest_key": manifest_key,
            "expected_sha256": expected_sha256,
            "actual_sha256": None,
            "hash_matches": False if manifest_key is not None else None,
        }
    path = raw_path.strip().split("::", 1)[0]
    if mock_mode:
        return {
            "label": label,
            "path": path,
            "status": "fixture",
            "manifest_key": manifest_key,
            "expected_sha256": expected_sha256,
            "actual_sha256": None,
            "hash_matches": None,
        }
    try:
        candidate = filesystem_scope.enforce(Path(path), _EvidenceScopeError)
    except _EvidenceScopeError:
        return {
            "label": label,
            "path": path,
            "status": "outside_scope",
            "manifest_key": manifest_key,
            "expected_sha256": expected_sha256,
            "actual_sha256": None,
            "hash_matches": False if manifest_key is not None else None,
        }
    status = "present" if candidate.is_file() else "missing"
    actual_sha256 = _sha256_file(candidate) if status == "present" else None
    return {
        "label": label,
        "path": str(candidate),
        "status": status,
        "manifest_key": manifest_key,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "hash_matches": (
            actual_sha256 == expected_sha256
            if manifest_key is not None
            and actual_sha256 is not None
            and _is_sha256(expected_sha256)
            else None if manifest_key is None else False
        ),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _EvidenceScopeError(Exception):
    """Small HTTPException-compatible adapter for evidence path probes."""

    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)


def _validate_json_path(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> Path:
    real = filesystem_scope.resolve(raw, http_exception)
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    if real.suffix.lower() != ".json":
        raise http_exception(status_code=400, detail=f"not a JSON summary file: {raw}")
    return real


def _load_fixture_summary() -> dict[str, Any]:
    text = (
        resources.files("openmc2donjon.web.fixtures")
        .joinpath("openmc_sph_physics_summary.json")
        .read_text(encoding="utf-8")
    )
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("mock OpenMC SPH physics summary fixture is not an object")
    return payload


def _validate_summary_payload(payload: dict[str, Any], http_exception: Any) -> None:
    errors: list[str] = []
    _require_type(payload, "schema", str, errors)
    if payload.get("schema") not in {
        OPENMC_SPH_PHYSICS_SUMMARY_SCHEMA,
        NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA,
        *_LEGACY_OPENMC_SPH_PHYSICS_SUMMARY_SCHEMAS,
    }:
        errors.append("schema is not a supported SPH physics summary")
    _require_type(payload, "route", str, errors)
    for key in ("mixture_count", "energy_groups", "legendre_order"):
        _require_type(payload, key, int, errors)
    _require_string_list(payload, "mixture_names", errors)
    for key in ("decisions", "normalization", "flux_uncertainty", "sph", "handoff"):
        _require_type(payload, key, dict, errors)
    per_mixture = payload.get("per_mixture")
    if not isinstance(per_mixture, list):
        errors.append("per_mixture must be a list")
    else:
        for index, row in enumerate(per_mixture):
            if not isinstance(row, dict):
                errors.append(f"per_mixture[{index}] must be an object")
                continue
            _require_type(row, "mixture", str, errors, prefix=f"per_mixture[{index}]")
            for key in (
                "sph_min",
                "sph_max",
                "sph_mean",
                "max_abs_sph_minus_1",
                "ce_flux_min",
                "ce_flux_max",
                "mg_flux_min",
                "mg_flux_max",
            ):
                _require_number(row, key, errors, prefix=f"per_mixture[{index}]")

    if isinstance(payload.get("sph"), dict):
        sph = payload["sph"]
        for key in ("minimum", "maximum", "mean", "max_abs_delta_from_unity"):
            _require_number(sph, key, errors, prefix="sph")
        _require_type(sph, "applied_to_xs", bool, errors, prefix="sph")
        _require_type(sph, "real", bool, errors, prefix="sph")
    if isinstance(payload.get("flux_uncertainty"), dict):
        flux = payload["flux_uncertainty"]
        _require_number(
            flux, "ce_max_relative_std_dev", errors, prefix="flux_uncertainty"
        )
        if not (
            payload.get("schema") == NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA
            and flux.get("mg_max_relative_std_dev") is None
        ):
            _require_number(
                flux,
                "mg_max_relative_std_dev",
                errors,
                prefix="flux_uncertainty",
            )
    if isinstance(payload.get("quality"), dict):
        quality = payload["quality"]
        _require_type(quality, "decision", str, errors, prefix="quality")
        for key in ("structural_passed", "production_ready", "demonstration_quality"):
            _require_type(quality, key, bool, errors, prefix="quality")
        for key in (
            "max_flux_relative_std_dev",
            "production_flux_relative_std_dev_threshold",
            "demonstration_flux_relative_std_dev_threshold",
        ):
            _require_number(quality, key, errors, prefix="quality")
    if isinstance(payload.get("handoff"), dict):
        handoff = payload["handoff"]
        _require_type(handoff, "augmented_hdf5_has_sph", bool, errors, prefix="handoff")
        _require_type(handoff, "ascii_nsp_block_count", int, errors, prefix="handoff")

    if payload.get("schema") == NATIVE_DRAGON_SPH_PHYSICS_SUMMARY_SCHEMA:
        for key in (
            "native_sph",
            "eigenvalue_validation",
            "component_balance",
            "acceptance_checks",
        ):
            _require_type(payload, key, dict, errors)
        native = payload.get("native_sph")
        if isinstance(native, dict):
            for key in ("converged", "normal_end"):
                _require_type(native, key, bool, errors, prefix="native_sph")
            _require_type(native, "iterations", int, errors, prefix="native_sph")
            for key in ("epsilon", "final_rms_factor_update"):
                _require_number(native, key, errors, prefix="native_sph")
        eigenvalue = payload.get("eigenvalue_validation")
        if isinstance(eigenvalue, dict):
            for key in (
                "openmc_keff",
                "openmc_keff_std_dev",
                "reference_rate_balance_keff",
                "reference_rate_balance_delta_pcm",
                "reference_rate_balance_z",
                "donjon_keff",
                "donjon_delta_pcm",
                "donjon_z",
                "max_abs_z",
            ):
                _require_number(eigenvalue, key, errors, prefix="eigenvalue_validation")
        checks = payload.get("acceptance_checks")
        if isinstance(checks, dict):
            for key in (
                "donjon_normal_end",
                "native_sph_converged",
                "energy_coverage_passed",
                "reference_rate_balance_within_openmc_uncertainty",
                "donjon_keff_within_openmc_uncertainty",
            ):
                _require_type(checks, key, bool, errors, prefix="acceptance_checks")
            for key in (
                "empirical_eigenvalue_multiplier_used",
                "adf_used",
            ):
                value = checks.get(key)
                if value is not None and not isinstance(value, bool):
                    errors.append(f"acceptance_checks.{key} must be bool or null")

    if errors:
        raise http_exception(
            status_code=422,
            detail="invalid OpenMC SPH physics summary: " + "; ".join(errors),
        )


def _require_type(
    payload: dict[str, Any],
    key: str,
    expected: type,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    value = payload.get(key)
    qualified = key if prefix is None else f"{prefix}.{key}"
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        errors.append(f"{qualified} must be {expected.__name__}")


def _require_number(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str | None = None,
) -> None:
    value = payload.get(key)
    qualified = key if prefix is None else f"{prefix}.{key}"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{qualified} must be number")


def _require_string_list(payload: dict[str, Any], key: str, errors: list[str]) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{key} must be a list of strings")
