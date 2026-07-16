"""Assemble accepted native-SPH MACROLIB components for a downstream model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .macrolib import Macrolib, read_macrolib_ascii, write_macrolib
from .multicompo import MixtureXS
from .native_sph_validation import (
    SCHEMA as NATIVE_SPH_SUMMARY_SCHEMA,
    converter_receipt_issues,
    native_sph_correction_policy_evidence,
)
from .web.openmc_sph_summary import _physics_acceptance


SCHEMA = "openmc2donjon.accepted-component-library.v1"
MAP_SCHEMA = "openmc2donjon.component-map-library.v1"
_NATIVE_ACCEPTANCE_POSITIVE_CHECKS = (
    "donjon_normal_end",
    "native_sph_converged",
    "native_sph_factors_unmodified",
    "native_sph_not_stopped_by_oscillation",
    "one_speed_convergence_provable",
    "final_flux_solve_converged",
    "energy_coverage_passed",
    "converter_receipt_linked",
    "leakage_balance_available_when_required",
    "reference_physical_balance_within_openmc_uncertainty",
    "donjon_keff_within_openmc_uncertainty",
)
_NATIVE_HANDOFF_EVIDENCE = (
    ("reference HDF5", "augmented_hdf5_path"),
    ("reference MACROLIB", "reference_macrolib_path"),
    ("corrected SPH MACROLIB", "macrolib_ascii_path"),
    ("verification MACROLIB", "verification_macrolib_path"),
    ("DONJON result listing", "result_listing_path"),
    ("energy coverage report", "energy_coverage_path"),
    ("Converter receipt", "converter_receipt_path"),
    ("executed CLE-2000 deck", "execution_deck_path"),
)


@dataclass(frozen=True, slots=True)
class AcceptedComponent:
    """One named component selected from an accepted native-SPH MACROLIB."""

    name: str
    macrolib: Path
    physics_summary: Path
    source_mixture: str


@dataclass(frozen=True, slots=True)
class ComponentPosition:
    """One downstream position assigned to an accepted component type."""

    name: str
    component: str


def assemble_accepted_component_library(
    components: Iterable[AcceptedComponent],
    output_path: str | Path,
    *,
    summary_json: str | Path | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Write one MACROLIB from explicitly selected, physically accepted inputs.

    Every source must have a live native-SPH validation summary whose accepted
    MACROLIB path matches the selected file.  The operation only selects and
    concatenates existing corrected mixture records; it never averages cross
    sections, fits an eigenvalue, or changes an SPH factor.
    """

    selected = tuple(components)
    _validate_declaration(selected)
    destination = Path(output_path).expanduser().resolve()
    if destination.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {destination}")

    source_rows: list[dict[str, object]] = []
    mixtures: list[MixtureXS] = []
    reference_energy: np.ndarray | None = None
    reference_moments: tuple[int, ...] | None = None
    reference_node_side: float | None = None
    missing_node_side: list[str] = []

    for component in selected:
        macrolib_path = component.macrolib.expanduser().resolve()
        summary_path = component.physics_summary.expanduser().resolve()
        source = read_macrolib_ascii(macrolib_path)
        physics = _accepted_physics_summary(summary_path, macrolib_path)
        geometry = physics.get("geometry")
        node_side = None if not isinstance(geometry, dict) else geometry.get("coarse_node_side_cm")
        if node_side is not None:
            node_side = float(node_side)
            if not np.isfinite(node_side) or node_side <= 0.0:
                raise ValueError(f"component {component.name}: invalid node side")
            if geometry.get("homogenization_volume_includes_node_catchall") is not True:
                raise ValueError(
                    f"component {component.name}: homogenization does not cover the declared node"
                )
            if reference_node_side is None:
                reference_node_side = node_side
            elif node_side != reference_node_side:
                raise ValueError(
                    f"component {component.name}: node side {node_side} differs from "
                    f"the library side {reference_node_side}"
                )
        elif reference_node_side is not None:
            raise ValueError(f"component {component.name}: physics summary has no declared node side")
        else:
            missing_node_side.append(component.name)
        source_names = tuple(str(name) for name in physics["mixture_names"])
        if component.source_mixture not in source_names:
            raise ValueError(
                f"component {component.name}: source mixture "
                f"{component.source_mixture!r} is not in {source_names!r}"
            )
        source_index = source_names.index(component.source_mixture)
        if source_index >= source.nmixtures:
            raise ValueError(
                f"component {component.name}: physics summary mixture order "
                "does not match the native-SPH MACROLIB"
            )
        if source.sph is None:
            raise ValueError(f"component {component.name}: native-SPH MACROLIB has no NSPH data")
        if source.adf:
            raise ValueError(f"component {component.name}: ADF data is forbidden in this library route")

        energy = _ascending_energy(source, component.name)
        moments = tuple(sorted(source.scatter))
        if reference_energy is None:
            reference_energy = energy
            reference_moments = moments
        else:
            if not np.array_equal(energy, reference_energy):
                raise ValueError(f"component {component.name}: energy boundaries differ from the library")
            if moments != reference_moments:
                raise ValueError(f"component {component.name}: scattering moments differ from the library")

        mixtures.append(_selected_mixture(component.name, source, source_index))
        source_rows.append(
            {
                "component": component.name,
                "source_mixture": component.source_mixture,
                "source_mixture_index": source_index + 1,
                "macrolib": str(macrolib_path),
                "macrolib_sha256": _sha256(macrolib_path),
                "physics_summary": str(summary_path),
                "physics_summary_sha256": _sha256(summary_path),
                "native_sph_decision": physics["quality"]["decision"],
                "coarse_node_side_cm": node_side,
            }
        )

    if reference_node_side is not None and missing_node_side:
        raise ValueError(
            "all components must declare the same node side when any component does: "
            + ", ".join(missing_node_side)
        )
    assert reference_energy is not None
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_macrolib(mixtures, reference_energy, destination)
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "decision": "accepted_component_library_assembled",
        "component_count": len(mixtures),
        "component_names": [mixture.name for mixture in mixtures],
        "energy_groups": mixtures[0].ngroups,
        "legendre_order": mixtures[0].nmoments - 1,
        "coarse_node_side_cm": reference_node_side,
        "output_path": str(destination),
        "output_sha256": _sha256(destination),
        "sources": source_rows,
        "physics_policy": {
            "native_sph_required": True,
            "adf_used": False,
            "empirical_eigenvalue_multiplier_used": False,
            "cross_section_averaging": False,
            "component_order_is_declared": True,
        },
    }
    if summary_json is not None:
        summary_path = Path(summary_json).expanduser().resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def expand_component_library(
    component_library: str | Path,
    library_summary: str | Path,
    positions: Iterable[ComponentPosition],
    output_path: str | Path,
    *,
    summary_json: str | Path | None = None,
    force: bool = False,
) -> dict[str, object]:
    """Map accepted component records onto declared downstream positions.

    The operation performs exact record selection and duplication.  It does
    not average, fit, homogenize, or rerun SPH.  A position-expanded library
    is useful when a downstream edition must preserve one result per physical
    node even though many nodes share the same qualified component type.
    """

    declared = tuple(positions)
    _validate_positions(declared)
    source_path = Path(component_library).expanduser().resolve()
    summary_path = Path(library_summary).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if destination.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {destination}")
    source = read_macrolib_ascii(source_path)
    receipt = _accepted_component_library_summary(summary_path, source_path)
    component_names = tuple(str(name) for name in receipt["component_names"])
    if len(component_names) != source.nmixtures:
        raise ValueError("component-library summary order does not match its MACROLIB")
    if source.sph is None:
        raise ValueError("accepted component library has no NSPH data")
    if source.adf:
        raise ValueError("ADF data is forbidden in the component-map route")
    by_name = {name: index for index, name in enumerate(component_names)}
    unknown = sorted({position.component for position in declared} - set(by_name))
    if unknown:
        raise ValueError(f"unknown accepted component type(s): {', '.join(unknown)}")

    mixtures = [
        _selected_mixture(position.name, source, by_name[position.component]) for position in declared
    ]
    energy = _ascending_energy(source, "component-library")
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_macrolib(mixtures, energy, destination)
    payload: dict[str, object] = {
        "schema": MAP_SCHEMA,
        "decision": "accepted_components_mapped_to_declared_positions",
        "position_count": len(declared),
        "position_names": [position.name for position in declared],
        "component_names": list(component_names),
        "assignments": [
            {
                "position": position.name,
                "component": position.component,
                "component_mixture_index": by_name[position.component] + 1,
            }
            for position in declared
        ],
        "energy_groups": source.ngroups,
        "legendre_order": max(source.scatter) if source.scatter else 0,
        "component_library": str(source_path),
        "component_library_sha256": _sha256(source_path),
        "component_library_summary": str(summary_path),
        "component_library_summary_sha256": _sha256(summary_path),
        "output_path": str(destination),
        "output_sha256": _sha256(destination),
        "physics_policy": {
            "native_sph_inherited": True,
            "adf_used": False,
            "empirical_eigenvalue_multiplier_used": False,
            "cross_section_averaging": False,
            "cross_section_fitting": False,
            "position_records_are_exact_component_copies": True,
        },
    }
    if summary_json is not None:
        output_summary = Path(summary_json).expanduser().resolve()
        output_summary.parent.mkdir(parents=True, exist_ok=True)
        output_summary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def _validate_declaration(components: tuple[AcceptedComponent, ...]) -> None:
    if not components:
        raise ValueError("at least one accepted component is required")
    names = [component.name.strip() for component in components]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("component names must be non-empty and unique")
    if any(not component.source_mixture.strip() for component in components):
        raise ValueError("source mixture names must be non-empty")


def _validate_positions(positions: tuple[ComponentPosition, ...]) -> None:
    if not positions:
        raise ValueError("at least one downstream position is required")
    names = [position.name.strip() for position in positions]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("position names must be non-empty and unique")
    if any(not position.component.strip() for position in positions):
        raise ValueError("position component names must be non-empty")


def _accepted_component_library_summary(
    path: Path,
    component_library: Path,
) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"component-library summary does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid component-library summary JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError(f"component-library summary must use {SCHEMA}: {path}")
    if payload.get("decision") != "accepted_component_library_assembled":
        raise ValueError(f"component library is not accepted: {path}")
    declared_path = Path(str(payload.get("output_path", ""))).expanduser().resolve()
    if declared_path != component_library:
        raise ValueError(
            "component-library summary output does not match selected MACROLIB: "
            f"{declared_path} != {component_library}"
        )
    declared_hash = str(payload.get("output_sha256", ""))
    actual_hash = _sha256(component_library)
    if not declared_hash or declared_hash != actual_hash:
        raise ValueError("component-library summary hash does not match selected MACROLIB")
    names = payload.get("component_names")
    if (
        not isinstance(names, list)
        or not names
        or any(not isinstance(name, str) or not name for name in names)
    ):
        raise ValueError("component-library summary has no valid component order")
    return payload


def _native_sph_acceptance_issues(payload: dict[str, Any]) -> list[str]:
    """Return strict native-SPH acceptance failures shared by all consumers.

    A copied legacy summary can claim ``production_ready`` and repeat old
    acceptance booleans without proving that the final transport solve or its
    one-speed iterations converged.  Keep the raw solver record, physical
    balance contract, geometry, and live evidence files as independent gates.
    The final call to the web evidence-audit predicate prevents this consumer
    gate from becoming weaker than the summary page.
    """

    issues: list[str] = []
    if payload.get("schema") != NATIVE_SPH_SUMMARY_SCHEMA:
        return ["physics summary is not a native-SPH validation result"]

    quality = payload.get("quality")
    if not isinstance(quality, dict):
        issues.append("native-SPH physics summary has no quality block")
    else:
        if quality.get("production_ready") is not True:
            issues.append("native-SPH physics summary is not production-ready")
        if quality.get("structural_passed") is not True:
            issues.append("native-SPH structural validation did not pass")

    checks = payload.get("acceptance_checks")
    if not isinstance(checks, dict):
        issues.append("native-SPH physics summary has no acceptance checks")
    else:
        for key in _NATIVE_ACCEPTANCE_POSITIVE_CHECKS:
            if checks.get(key) is not True:
                issues.append(f"native-SPH acceptance check did not pass: {key}")
        if checks.get("empirical_eigenvalue_multiplier_used") is not False:
            issues.append(
                "native-SPH empirical eigenvalue multiplier is present or its "
                "absence is not proved"
            )
        if checks.get("adf_used") is not False:
            issues.append("native-SPH ADF is present or its absence is not proved")

    native = payload.get("native_sph")
    if not isinstance(native, dict):
        issues.append("native-SPH summary has no raw solver evidence")
    else:
        for key in (
            "normal_end",
            "converged",
            "one_speed_convergence_provable",
            "final_flux_solve_converged",
            "factors_unmodified",
        ):
            if native.get(key) is not True:
                issues.append(f"native-SPH raw solver evidence did not prove {key}")
        for key in (
            "flux_nonconvergence_count",
            "negative_factor_correction_count",
            "oscillation_stop_count",
        ):
            value = native.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value != 0:
                issues.append(f"native-SPH raw solver evidence requires {key}=0")

    sph = payload.get("sph")
    clipped_count = sph.get("clipped_count") if isinstance(sph, dict) else None
    if not isinstance(clipped_count, int) or isinstance(clipped_count, bool) or clipped_count != 0:
        issues.append("native-SPH factors must have clipped_count=0")

    geometry = payload.get("geometry")
    if not isinstance(geometry, dict):
        issues.append("native-SPH summary has no geometry evidence")
        boundary = ""
    else:
        node_side = geometry.get("coarse_node_side_cm")
        if not _finite_number(node_side) or float(node_side) <= 0.0:
            issues.append("native-SPH geometry has no positive finite coarse node side")
        if geometry.get("homogenization_volume_includes_node_catchall") is not True:
            issues.append("native-SPH homogenization does not cover the full coarse node")
        boundary_value = geometry.get("boundary_conditions")
        boundary = boundary_value.strip().lower() if isinstance(boundary_value, str) else ""
        if not boundary or boundary == "unspecified":
            issues.append("native-SPH geometry has no explicit boundary conditions")

    eigenvalue = payload.get("eigenvalue_validation")
    if not isinstance(eigenvalue, dict):
        issues.append("native-SPH summary has no physical eigenvalue-balance evidence")
    else:
        for key in (
            "reference_physical_balance_keff",
            "reference_physical_balance_delta_pcm",
            "reference_physical_balance_z",
            "reference_collision_balance_kinf",
        ):
            if not _finite_number(eigenvalue.get(key)):
                issues.append(f"native-SPH physical balance has no finite {key}")
        balance_kind = eigenvalue.get("reference_physical_balance_kind")
        if balance_kind == "finite-domain-keff":
            if eigenvalue.get("reference_finite_balance_available") is not True:
                issues.append("native-SPH finite-domain physical balance is unavailable")
            if not _finite_number(eigenvalue.get("reference_finite_balance_keff")):
                issues.append("native-SPH finite-domain balance has no finite keff")
            leakage = eigenvalue.get("reference_leakage")
            if not _finite_number(leakage) or float(leakage) < 0.0:
                issues.append("native-SPH finite-domain balance has no nonnegative leakage")
        elif balance_kind == "collision-balance-kinf":
            if "vacuum" in boundary:
                issues.append("native-SPH vacuum geometry requires a finite-domain leakage balance")
        else:
            issues.append("native-SPH summary has no recognized physical balance kind")

    handoff = payload.get("handoff")
    evidence_present = True
    if not isinstance(handoff, dict):
        issues.append("native-SPH physics summary has no handoff block")
        evidence_present = False
    else:
        evidence = list(_NATIVE_HANDOFF_EVIDENCE)
        evidence_hashes = handoff.get("evidence_sha256")
        if not isinstance(evidence_hashes, dict):
            issues.append("native-SPH handoff has no evidence SHA-256 manifest")
            evidence_hashes = {}
            evidence_present = False
        for label, key in evidence:
            raw_path = handoff.get(key)
            if not isinstance(raw_path, str) or not raw_path.strip():
                issues.append(f"native-SPH {label} evidence path is not declared")
                evidence_present = False
                continue
            evidence_path = Path(raw_path.strip().split("::", 1)[0]).expanduser()
            if not evidence_path.is_file():
                issues.append(f"native-SPH {label} evidence file does not exist: {evidence_path}")
                evidence_present = False
                continue
            expected_hash = evidence_hashes.get(key)
            if not isinstance(expected_hash, str) or not expected_hash.strip():
                issues.append(f"native-SPH {label} evidence hash is not declared")
                evidence_present = False
            elif expected_hash != _sha256(evidence_path):
                issues.append(f"native-SPH {label} evidence hash mismatch")
                evidence_present = False

        receipt_path = _declared_handoff_path(handoff, "converter_receipt_path")
        reference_h5 = _declared_handoff_path(handoff, "augmented_hdf5_path")
        reference_macrolib = _declared_handoff_path(
            handoff, "reference_macrolib_path"
        )
        receipt_issues: list[str] = []
        if (
            receipt_path is not None
            and reference_h5 is not None
            and reference_macrolib is not None
            and receipt_path.is_file()
            and reference_h5.is_file()
            and reference_macrolib.is_file()
        ):
            receipt_issues = converter_receipt_issues(
                receipt_path,
                reference_h5=reference_h5,
                reference_macrolib=reference_macrolib,
            )
            issues.extend(receipt_issues)
        else:
            receipt_issues = [
                "native-SPH Converter receipt/reference artifacts are unavailable"
            ]
            issues.extend(receipt_issues)

        corrected_macrolib = _declared_handoff_path(
            handoff, "macrolib_ascii_path"
        )
        verify_macrolib = _declared_handoff_path(
            handoff, "verification_macrolib_path"
        )
        result_listing = _declared_handoff_path(handoff, "result_listing_path")
        execution_deck = _declared_handoff_path(handoff, "execution_deck_path")
        policy_paths = (
            reference_h5,
            reference_macrolib,
            corrected_macrolib,
            verify_macrolib,
            result_listing,
            execution_deck,
        )
        policy_verified = False
        if any(path is None or not path.is_file() for path in policy_paths):
            issues.append(
                "native-SPH no-ADF/no-empirical policy lacks a complete live "
                "deck and MACROLIB evidence chain"
            )
        else:
            assert reference_h5 is not None
            assert reference_macrolib is not None
            assert corrected_macrolib is not None
            assert verify_macrolib is not None
            assert result_listing is not None
            assert execution_deck is not None
            try:
                correction_policy = native_sph_correction_policy_evidence(
                    reference_h5=reference_h5,
                    reference_macrolib=reference_macrolib,
                    sph_macrolib=corrected_macrolib,
                    verify_macrolib=verify_macrolib,
                    result_listing=result_listing,
                    execution_deck=execution_deck,
                )
            except (OSError, TypeError, ValueError, KeyError, IndexError) as exc:
                issues.append(
                    "native-SPH no-ADF/no-empirical policy audit failed: "
                    f"{exc}"
                )
            else:
                policy_verified = correction_policy.get("status") == "verified_absent"
                if not policy_verified:
                    policy_issues = correction_policy.get("issues")
                    if isinstance(policy_issues, list) and policy_issues:
                        issues.extend(str(issue) for issue in policy_issues)
                    else:
                        issues.append(
                            "native-SPH no-ADF/no-empirical policy was not proved"
                        )

        evidence_integrity = {
            "verified": bool(
                evidence_present and not receipt_issues and policy_verified
            )
        }

    audit = _physics_acceptance(
        payload,
        native=True,
        mock_mode=False,
        all_present=evidence_present,
        evidence_integrity=(
            evidence_integrity if isinstance(handoff, dict) else {"verified": False}
        ),
    )
    if audit != "passed" and not issues:
        issues.append("native-SPH evidence audit did not establish physics acceptance")
    return issues


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and bool(np.isfinite(float(value)))


def _declared_handoff_path(handoff: dict[str, Any], key: str) -> Path | None:
    value = handoff.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value.strip().split("::", 1)[0]).expanduser().resolve()


def _accepted_physics_summary(path: Path, macrolib_path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"physics summary does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid physics summary JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != NATIVE_SPH_SUMMARY_SCHEMA:
        raise ValueError(f"physics summary must use {NATIVE_SPH_SUMMARY_SCHEMA}: {path}")
    quality = payload.get("quality")
    handoff = payload.get("handoff")
    names = payload.get("mixture_names")
    if not isinstance(quality, dict) or quality.get("production_ready") is not True:
        raise ValueError(f"native-SPH physics summary is not production-ready: {path}")
    if not isinstance(handoff, dict):
        raise ValueError(f"native-SPH summary has no handoff block: {path}")
    declared = Path(str(handoff.get("macrolib_ascii_path", ""))).expanduser().resolve()
    if declared != macrolib_path:
        raise ValueError(
            f"native-SPH summary MACROLIB does not match the selected source: {declared} != {macrolib_path}"
        )
    strict_issues = _native_sph_acceptance_issues(payload)
    if strict_issues:
        raise ValueError(
            f"native-SPH strict physics acceptance failed: {path}: "
            + "; ".join(strict_issues)
        )
    if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names):
        raise ValueError(f"native-SPH summary has no valid mixture order: {path}")
    return payload


def _ascending_energy(source: Macrolib, component_name: str) -> np.ndarray:
    energy = np.asarray(source.energy, dtype=float)
    if energy.shape != (source.ngroups + 1,):
        raise ValueError(f"component {component_name}: MACROLIB has no complete ENERGY block")
    ascending = energy[::-1]
    if not np.all(np.isfinite(ascending)) or np.any(np.diff(ascending) <= 0.0):
        raise ValueError(f"component {component_name}: invalid MACROLIB energy boundaries")
    return ascending


def _selected_mixture(name: str, source: Macrolib, index: int) -> MixtureXS:
    moments = np.stack([source.scatter[moment][index] for moment in sorted(source.scatter)])
    total = np.asarray(source.ntot0[index], dtype=float).copy()
    diff = np.asarray(source.diff[index], dtype=float)
    transport_total = np.divide(
        1.0,
        3.0 * diff,
        out=total.copy(),
        where=diff > 0.0,
    )
    volume = float(source.volume[index])
    if not np.isfinite(volume) or volume <= 0.0:
        raise ValueError(f"component {name}: source volume must be positive")
    return MixtureXS(
        name=name,
        total=total,
        absorption=np.zeros(source.ngroups, dtype=float),
        fission=np.zeros(source.ngroups, dtype=float),
        nu_fission=np.asarray(source.nusigf[index], dtype=float).copy(),
        chi=np.asarray(source.chi[index], dtype=float).copy(),
        scatter_matrix=moments,
        fissionable=bool(np.any(source.nusigf[index] > 0.0)),
        volume=volume,
        inverse_velocity=None,
        transport_total=transport_total,
        flux_weight=np.asarray(source.flux_intg[index], dtype=float) / volume,
        h_factor=(
            None if source.h_factor is None else np.asarray(source.h_factor[index], dtype=float).copy()
        ),
        adf={},
        sph=np.asarray(source.sph[index], dtype=float).copy(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
