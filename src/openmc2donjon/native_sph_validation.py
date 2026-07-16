"""Validate a Converter -> native DRAGON SPH -> DONJON handoff."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from .hdf5_names import read_mixture_names
from .macrolib import read_macrolib_ascii
from .production_policy import canonical_production_policy_issues


SCHEMA = "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1"
CONVERTER_RECEIPT_SCHEMA = "openmc2donjon.convert.v1"
_ITERATION_RE = re.compile(
    r"SPHEQU:\s+ITER=\s*(\d+)\s+ERROR=\s*([0-9.Ee+-]+)\s+ERR 2=\s*([0-9.Ee+-]+)"
)
_ENDING_RE = re.compile(
    r"SPHEQU:\s+ENDING OF SPH CONVERGENCE AFTER\s+(\d+)\s+ITERATIONS"
)
_EPSPH_RE = re.compile(r"EPSPH\s+([0-9.Ee+-]+)\s+\(CONVERGENCE CRITERION\)")
_SCATTER_MOMENTS_RE = re.compile(r"\b(?:SPN|SN)\s+\d+\s+SCAT\s+(\d+)\b")
_TRACK_SOLVER_RE = re.compile(r"TRACK\s*:=\s*(SNT|TRIVAT):", re.IGNORECASE)
_SN_GMRES_RE = re.compile(r"\bGMRES\s+\d+\s+MAXI\s+\d+", re.IGNORECASE)
_SN_DSA_RE = re.compile(r"\bDSA\s+\d+\s+\d+\s+[12]\b", re.IGNORECASE)
_SN_LIVOLANT_RE = re.compile(r"\bLIVO\s+\d+\s+\d+\b", re.IGNORECASE)
_SN_INNER_NONCONVERGENCE = "SNF: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED."
# DRAGON 5.1's SNGMRE path has no corresponding failure message when MAXIT is
# exhausted (and SNT ``EDIT 1`` does not print its final iteration count).
# Consequently, absence of the markers below is positive convergence evidence
# for SNF/Livolant/DSA and TRIFLV/PNFLV paths, but not by itself for SNGMRE.
# Production GMRES evidence needs an upstream explicit nonconvergence marker or
# a listing level/validator contract that proves every SNGMRE solve terminated.
_FLUX_NONCONVERGENCE_MARKERS = (
    _SN_INNER_NONCONVERGENCE,
    "SNF: UNABLE TO CONVERGE ONE-SPEED ITERATIONS IN GROUP",
    "TRIFLV: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.",
    "TRIFLV: UNABLE TO CONVERGE ONE-SPEED ITERATIONS.",
    "PNFLV: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.",
    "PNFLV: UNABLE TO CONVERGE ONE-SPEED ITERATIONS.",
    "FLU2DR: CONVERGENCE NOT REACHED",
    "MAXIMUM NUMBER OF EXTERNAL ITERATIONS IS REACHED",
    "MAXIMUM NUMBER OF THERMAL ITERATIONS IS REACHED",
)
_NEGATIVE_SPH_FACTOR_RE = re.compile(
    r"Warning:\s+negative SPH factor in group\s+\d+\s+and region\s+\d+\s+set to 1\.0",
    re.IGNORECASE,
)
_SPH_OSCILLATION_STOP = "maximum of 3 error oscillations in SPH convergence reached"
_DECK_INLINE_COMMENT_RE = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_DECK_STRING_RE = re.compile(r"'(?:''|[^'])*'")
_DECK_SPH_ASSIGNMENT_RE = re.compile(
    r"\b(?P<corrected>[A-Za-z][A-Za-z0-9_]*)\s*:=\s*SPH:\s*"
    r"(?P<reference>[A-Za-z][A-Za-z0-9_]*)\s+"
    r"(?P<tracking>[A-Za-z][A-Za-z0-9_]*)\s*::",
    re.IGNORECASE,
)
_DECK_EXPLICIT_EMPIRICAL_RE = re.compile(
    r"\b(?:EMPIRICAL|EIGENVALUE[_ -]?MULTIPLIER|KEFF[_ -]?(?:FACTOR|MULTIPLIER)|"
    r"K[_ -]?EFFECTIVE[_ -]?(?:FACTOR|MULTIPLIER)|KFAC(?:TOR)?)\b",
    re.IGNORECASE,
)
_DECK_ADF_RE = re.compile(
    r"\b(?:ADF|ALBEDO[_ -]?DISCONTINUITY[_ -]?FACTOR|DISCONTINUITY[_ -]?FACTOR)\b",
    re.IGNORECASE,
)
_DECK_EVALUATE_RE = re.compile(r"\bEVALUATE\b.*?;", re.IGNORECASE | re.DOTALL)
_SPH_APPLY_MARKER_ATTRS = (
    "sph_apply_schema",
    "sph_apply_operator",
    "sph_apply_input_format",
    "sph_applied_source",
    "sph_applied_mixture_names",
    "sph_applied_macroscopic_names",
)
_ADF_MARKER_ATTRS = (
    "adf_injector",
    "adf_sidecar",
    "adf_face_names",
    "adf_source",
    "adf_kind",
    "adf_real",
)
_EQUIVALENCE_OBJECT_NAMES = frozenset(
    {"sph", "nsph", "adf", "discontinuity_factors"}
)
_EQUIVALENCE_ATTRIBUTE_RE = re.compile(
    r"(?:^|_)(?:sph|nsph|adf)(?:_|$)|^discontinuity_factors$",
    re.IGNORECASE,
)
ENERGY_COVERAGE_SCHEMA = "openmc2donjon.energy-coverage.v1"
ENERGY_COVERAGE_COMPATIBLE_SCHEMAS = frozenset(
    {
        ENERGY_COVERAGE_SCHEMA,
        # Read-only compatibility for already generated diagnostic evidence.
        # New producers must use the model-neutral schema above.
        "openmc2donjon.irena30-energy-coverage.v1",
    }
)
ENERGY_COVERAGE_REQUIRED_SCORES = frozenset(
    {"absorption", "fission", "kappa-fission", "nu-fission"}
)
NATIVE_SPH_EQUIVALENCE_RELATIVE_TOLERANCE = 1.0e-4
NATIVE_SPH_FLUX_RELATIVE_STD_DEV_LIMIT = 0.1


def native_sph_reference_issues(path: str | Path) -> list[str]:
    """Reject any pre-existing equivalence data on a native-SPH reference.

    Native DRAGON SPH must start from a plain, uncorrected Converter
    reference.  Even an unapplied SPH/NSPH payload is ambiguous once
    Converter serializes it into the reference MACROLIB, and any ADF payload
    contradicts the no-ADF native route.  Both therefore fail closed.
    """

    import h5py

    candidate = Path(path).expanduser()
    try:
        with h5py.File(candidate, "r") as h5:
            issues: list[str] = []
            if _hdf5_flag_is_true(h5.attrs.get("sph_applied", False)):
                issues.append(
                    "native-SPH reference HDF5 has sph_applied=true; "
                    "native SPH requires an uncorrected Converter reference"
                )
            markers = [name for name in _SPH_APPLY_MARKER_ATTRS if name in h5.attrs]
            if markers:
                issues.append(
                    "native-SPH reference HDF5 carries applied-SPH markers: "
                    + ", ".join(markers)
                )
            adf_markers = [name for name in _ADF_MARKER_ATTRS if name in h5.attrs]
            if adf_markers:
                issues.append(
                    "native-SPH reference HDF5 carries ADF markers: "
                    + ", ".join(adf_markers)
                )
            payloads: list[str] = []
            payload_attributes: list[str] = []

            for attribute in h5.attrs:
                if _EQUIVALENCE_ATTRIBUTE_RE.search(str(attribute)):
                    payload_attributes.append(f"/@{attribute}")

            def collect_equivalence_payload(name: str, h5_object: Any) -> None:
                basename = name.rsplit("/", 1)[-1].strip().lower()
                if basename in _EQUIVALENCE_OBJECT_NAMES:
                    payloads.append("/" + name.strip("/"))
                for attribute in h5_object.attrs:
                    if _EQUIVALENCE_ATTRIBUTE_RE.search(str(attribute)):
                        payload_attributes.append(
                            f"/{name.strip('/')}@{attribute}"
                        )

            h5.visititems(collect_equivalence_payload)
            if payloads:
                sph_payloads = [
                    name
                    for name in payloads
                    if name.rsplit("/", 1)[-1].lower() in {"sph", "nsph"}
                ]
                adf_payloads = [name for name in payloads if name not in sph_payloads]
                if sph_payloads:
                    issues.append(
                        "native-SPH reference HDF5 contains SPH/NSPH payload(s): "
                        + ", ".join(sorted(sph_payloads))
                    )
                if adf_payloads:
                    issues.append(
                        "native-SPH reference HDF5 contains ADF payload(s): "
                        + ", ".join(sorted(adf_payloads))
                    )
            if payload_attributes:
                sph_attributes = [
                    name
                    for name in payload_attributes
                    if "adf" not in name.lower()
                    and "discontinuity_factors" not in name.lower()
                ]
                adf_attributes = [
                    name for name in payload_attributes if name not in sph_attributes
                ]
                if sph_attributes:
                    issues.append(
                        "native-SPH reference HDF5 contains SPH/NSPH metadata: "
                        + ", ".join(sorted(set(sph_attributes)))
                    )
                if adf_attributes:
                    issues.append(
                        "native-SPH reference HDF5 contains ADF metadata: "
                        + ", ".join(sorted(set(adf_attributes)))
                    )
            return issues
    except OSError as exc:
        return [f"native-SPH reference is not a readable HDF5 file: {exc}"]


def _hdf5_flag_is_true(value: Any) -> bool:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def validate_native_sph(
    reference_h5: str | Path,
    reference_macrolib: str | Path,
    sph_macrolib: str | Path,
    verify_macrolib: str | Path,
    result_listing: str | Path,
    *,
    output_json: str | Path | None = None,
    energy_coverage_json: str | Path | None = None,
    converter_receipt_json: str | Path | None = None,
    execution_deck: str | Path | None = None,
    max_keff_sigma: float = 2.0,
) -> dict[str, Any]:
    """Build auditable native-SPH acceptance evidence.

    Acceptance uses only deterministic convergence, exact reaction-rate
    balance, and consistency with the declared OpenMC statistical uncertainty.
    No empirical eigenvalue multiplier or fitted correction is introduced.
    """

    import h5py

    paths = {
        "reference_h5": Path(reference_h5).resolve(),
        "reference_macrolib": Path(reference_macrolib).resolve(),
        "sph_macrolib": Path(sph_macrolib).resolve(),
        "verify_macrolib": Path(verify_macrolib).resolve(),
        "result_listing": Path(result_listing).resolve(),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label} does not exist: {path}")
    if not math.isfinite(max_keff_sigma) or max_keff_sigma <= 0.0:
        raise ValueError("max_keff_sigma must be positive and finite")
    reference_issues = native_sph_reference_issues(paths["reference_h5"])
    if reference_issues:
        raise ValueError(
            "native SPH reference HDF5 is not an uncorrected reference: "
            + "; ".join(reference_issues)
        )

    reference = read_macrolib_ascii(paths["reference_macrolib"])
    corrected = read_macrolib_ascii(paths["sph_macrolib"])
    verification = read_macrolib_ascii(paths["verify_macrolib"])
    if reference.sph is not None:
        raise ValueError(
            "native SPH reference MACROLIB already contains GROUP/*/NSPH; "
            "native SPH requires a plain, uncorrected Converter reference"
        )
    if reference.adf:
        raise ValueError(
            "native SPH reference MACROLIB contains ADF data; "
            "ADF is forbidden on the no-ADF native-SPH route"
        )
    if corrected.sph is None:
        raise ValueError("native SPH macrolib has no GROUP/*/NSPH factors")
    if corrected.adf or verification.adf:
        raise ValueError(
            "native SPH corrected/verification MACROLIB contains ADF data; "
            "ADF is forbidden on the no-ADF native-SPH route"
        )
    if reference.ngroups != corrected.ngroups or corrected.ngroups != verification.ngroups:
        raise ValueError("reference, SPH, and verification group counts differ")
    if reference.nmixtures != corrected.nmixtures or corrected.nmixtures != verification.nmixtures:
        raise ValueError("reference, SPH, and verification mixture counts differ")
    _require_positive_finite_matrix(
        reference.flux_intg, "reference MACROLIB FLUX-INTG"
    )
    _require_positive_finite_matrix(
        verification.flux_intg, "verification MACROLIB FLUX-INTG"
    )
    _require_positive_finite_matrix(corrected.sph, "native SPH NSPH factors")

    with h5py.File(paths["reference_h5"], "r") as h5:
        mixture_names = list(read_mixture_names(h5))
        keff = _optional_positive(h5.attrs.get("reference_keff"))
        keff_std = _optional_positive(h5.attrs.get("reference_keff_std_dev"))
        collision_balance_tally_kinf = _optional_positive(
            h5.attrs.get(
                "reference_collision_balance_kinf",
                h5.attrs.get("reference_rate_balance_tally_keff"),
            )
        )
        collision_balance_std = _optional_positive(
            h5.attrs.get(
                "reference_collision_balance_std_dev",
                h5.attrs.get("reference_rate_balance_std_dev"),
            )
        )
        finite_balance_keff = _optional_positive(
            h5.attrs.get("reference_finite_balance_keff")
        )
        finite_balance_std = _optional_positive(
            h5.attrs.get("reference_finite_balance_std_dev")
        )
        leakage = _optional_nonnegative(h5.attrs.get("reference_leakage"))
        leakage_std = _optional_nonnegative(
            h5.attrs.get("reference_leakage_std_dev")
        )
        rate_balance_uncertainty_method = _optional_text(
            h5.attrs.get("reference_rate_balance_uncertainty_method")
        )
        coarse_node_side_cm = _optional_positive(
            h5.attrs.get("coarse_node_side_cm")
        )
        includes_node_catchall = bool(
            h5.attrs.get("homogenization_volume_includes_node_catchall", False)
        )
        boundary_conditions = _optional_text(h5.attrs.get("boundary_conditions"))
        center_kind = _optional_text(h5.attrs.get("center_kind"))
        neighbor_kinds = _optional_text(h5.attrs.get("neighbor_kinds"))
        openmc_flux = (
            None
            if "openmc_volume_flux" not in h5
            else np.asarray(h5["openmc_volume_flux"][:], dtype=float)
        )
        flux_std = (
            None
            if "openmc_volume_flux_std_dev" not in h5
            else np.asarray(h5["openmc_volume_flux_std_dev"][:], dtype=float)
        )
    if len(mixture_names) != reference.nmixtures:
        raise ValueError("reference HDF5 and MACROLIB mixture counts differ")
    if keff is None:
        keff = reference.reference_keff
    if keff is None or keff_std is None:
        raise ValueError("production native SPH validation requires OpenMC keff and std_dev")
    if reference.reference_kinf is None:
        raise ValueError("reference MACROLIB has no rate-balance K-INFINITY")
    if verification.reference_keff is None:
        raise ValueError("verification MACROLIB has no calculated K-EFFECTIVE")

    listing = paths["result_listing"].read_text(encoding="utf-8", errors="replace")
    native = _native_convergence(listing)
    coverage_path = (
        None if energy_coverage_json is None else Path(energy_coverage_json).resolve()
    )
    coverage = _read_coverage(coverage_path)
    coverage_evidence = _energy_coverage_evidence(coverage)
    converter_receipt_path = (
        None
        if converter_receipt_json is None
        else Path(converter_receipt_json).expanduser().resolve()
    )
    if converter_receipt_path is not None and not converter_receipt_path.is_file():
        raise FileNotFoundError(
            f"Converter receipt does not exist: {converter_receipt_path}"
        )
    converter_receipt = _converter_receipt_evidence(
        converter_receipt_path,
        reference_h5=paths["reference_h5"],
        reference_macrolib=paths["reference_macrolib"],
    )
    execution_deck_path = (
        None
        if execution_deck is None
        else Path(execution_deck).expanduser().resolve()
    )
    if execution_deck_path is not None and not execution_deck_path.is_file():
        raise FileNotFoundError(
            f"native-SPH execution deck does not exist: {execution_deck_path}"
        )
    correction_policy = native_sph_correction_policy_evidence(
        reference_h5=paths["reference_h5"],
        reference_macrolib=paths["reference_macrolib"],
        sph_macrolib=paths["sph_macrolib"],
        verify_macrolib=paths["verify_macrolib"],
        result_listing=paths["result_listing"],
        execution_deck=execution_deck_path,
    )
    flux_metrics = _flux_and_balance_metrics(reference, corrected, verification)
    reference_flux = np.asarray(reference.flux_intg, dtype=float)
    flux_uncertainty, relative_flux_std = _flux_uncertainty_evidence(
        openmc_flux,
        flux_std,
        reference_flux=reference_flux,
    )

    # K-INFINITY closes only the collision balance.  It is a valid physical
    # eigenvalue check for a non-leaking model, but it must never be compared
    # directly with keff when vacuum leakage is present.  New exporters attach
    # OpenMC's global leakage and a finite-domain P/(C+L) balance.  Legacy
    # closed-domain files fall back to the collision balance.
    finite_balance_available = bool(
        finite_balance_keff is not None
        and finite_balance_std is not None
        and leakage is not None
        and leakage_std is not None
    )
    physical_balance_kind = (
        "finite-domain-keff" if finite_balance_available else "collision-balance-kinf"
    )
    physical_balance_keff = (
        finite_balance_keff if finite_balance_available else reference.reference_kinf
    )
    physical_balance_std = (
        finite_balance_std if finite_balance_available else collision_balance_std
    )
    reference_balance_combined_std = (
        keff_std
        if physical_balance_std is None
        else keff_std + physical_balance_std
    )
    reference_balance_z = (
        physical_balance_keff - keff
    ) / reference_balance_combined_std
    # The final deterministic eigenvalue is calculated from the same sampled
    # multigroup reaction rates as ``reference.reference_kinf``.  Comparing it
    # with the CE eigenvalue using only the CE k standard deviation therefore
    # treats the sampled MGXS as exact and can reject a statistically
    # consistent handoff.  Use the same conservative no-covariance bound for
    # the end-to-end comparison.  This is uncertainty propagation only: no
    # eigenvalue or cross section is modified.
    final_keff_z = (
        verification.reference_keff - keff
    ) / reference_balance_combined_std
    component_flux_residual = max(
        float(flux_metrics["flux_max_relative_residual"]),
        *(
            float(row["flux_max_relative_residual"])
            for row in flux_metrics["per_component"]
        ),
    )
    component_loss_residual = max(
        abs(float(flux_metrics["net_loss_relative_residual"])),
        *(
            abs(float(row["net_loss_relative_residual"]))
            for row in flux_metrics["per_component"]
        ),
    )
    checks = {
        "donjon_normal_end": native["normal_end"],
        "native_sph_converged": native["converged"],
        "native_sph_factors_unmodified": native["factors_unmodified"],
        "native_sph_not_stopped_by_oscillation": (
            native["oscillation_stop_count"] == 0
        ),
        "one_speed_convergence_provable": native[
            "one_speed_convergence_provable"
        ],
        "final_flux_solve_converged": native["final_flux_solve_converged"],
        "energy_coverage_passed": coverage_evidence["passed"],
        "converter_receipt_linked": converter_receipt["valid"],
        "native_sph_factors_finite_positive": bool(
            np.all(np.isfinite(corrected.sph)) and np.all(corrected.sph > 0.0)
        ),
        "reference_flux_strictly_positive": bool(
            np.all(np.isfinite(reference_flux)) and np.all(reference_flux > 0.0)
        ),
        "flux_uncertainty_evidence_present": flux_uncertainty[
            "evidence_valid"
        ],
        "reference_flux_matches_openmc_evidence": flux_uncertainty[
            "reference_flux_matches_macrolib"
        ],
        "flux_uncertainty_within_production_limit": flux_uncertainty[
            "within_production_limit"
        ],
        "component_flux_equivalence_within_tolerance": bool(
            math.isfinite(component_flux_residual)
            and component_flux_residual
            <= NATIVE_SPH_EQUIVALENCE_RELATIVE_TOLERANCE
        ),
        "component_net_loss_equivalence_within_tolerance": bool(
            math.isfinite(component_loss_residual)
            and component_loss_residual
            <= NATIVE_SPH_EQUIVALENCE_RELATIVE_TOLERANCE
        ),
        "leakage_balance_available_when_required": (
            "vacuum" not in (boundary_conditions or "").lower()
            or finite_balance_available
        ),
        "reference_physical_balance_within_openmc_uncertainty": (
            abs(reference_balance_z) <= max_keff_sigma
        ),
        # Compatibility alias for existing frontend readers.  Its meaning is
        # now the selected physical balance, never unconditional K-inf≈keff.
        "reference_rate_balance_within_openmc_uncertainty": (
            abs(reference_balance_z) <= max_keff_sigma
        ),
        "donjon_keff_within_openmc_uncertainty": abs(final_keff_z) <= max_keff_sigma,
        # Tri-state compatibility fields.  False is emitted only when the
        # hash-bound deck and all material artifacts prove absence.  None is
        # deliberately fail-closed and cannot be rendered as a green PASS by
        # existing frontend readers that require the exact boolean False.
        "empirical_eigenvalue_multiplier_used": correction_policy[
            "empirical_eigenvalue_multiplier"
        ]["used"],
        "adf_used": correction_policy["adf"]["used"],
    }
    direct_balance_z = None
    if collision_balance_tally_kinf is not None and collision_balance_std is not None:
        direct_balance_z = (
            reference.reference_kinf - collision_balance_tally_kinf
        ) / collision_balance_std
        checks["reference_macrolib_matches_direct_collision_balance_tally"] = bool(
            abs(direct_balance_z) <= max_keff_sigma
        )
    sph = np.asarray(corrected.sph, dtype=float)
    physical_flux = np.asarray(flux_metrics.pop("physical_flux"), dtype=float)
    flux_metrics["acceptance_relative_tolerance"] = (
        NATIVE_SPH_EQUIVALENCE_RELATIVE_TOLERANCE
    )
    flux_metrics["maximum_component_flux_relative_residual"] = (
        component_flux_residual
    )
    flux_metrics["maximum_component_net_loss_relative_residual"] = (
        component_loss_residual
    )
    passed = all(
        value
        for key, value in checks.items()
        if key
        not in {
            "empirical_eigenvalue_multiplier_used",
            "adf_used",
        }
    ) and all(
        checks[key] is False
        for key in (
            "empirical_eigenvalue_multiplier_used",
            "adf_used",
        )
    )
    per_mixture = []
    for index, name in enumerate(mixture_names):
        ratio = physical_flux[index] / reference_flux[index]
        per_mixture.append(
            {
                "mixture": name,
                "ce_flux_min": float(np.min(reference_flux[index])),
                "ce_flux_max": float(np.max(reference_flux[index])),
                "mg_flux_min": float(np.min(physical_flux[index])),
                "mg_flux_max": float(np.max(physical_flux[index])),
                "normalized_mg_over_ce_min": float(np.min(ratio)),
                "normalized_mg_over_ce_max": float(np.max(ratio)),
                "sph_min": float(np.min(sph[index])),
                "sph_max": float(np.max(sph[index])),
                "sph_mean": float(np.mean(sph[index])),
                "max_abs_sph_minus_1": float(np.max(np.abs(sph[index] - 1.0))),
            }
        )

    handoff_paths: dict[str, Path | None] = {
        "augmented_hdf5_path": paths["reference_h5"],
        "reference_macrolib_path": paths["reference_macrolib"],
        "macrolib_ascii_path": paths["sph_macrolib"],
        "verification_macrolib_path": paths["verify_macrolib"],
        "result_listing_path": paths["result_listing"],
        "energy_coverage_path": coverage_path,
        "converter_receipt_path": converter_receipt_path,
        "execution_deck_path": execution_deck_path,
    }
    evidence_sha256 = {
        key: _sha256_file(path)
        for key, path in handoff_paths.items()
        if path is not None
    }

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "route": (
            "OpenMC CE fine -> Converter -> DRAGON native SPH -> "
            f"DONJON {str(native['solver_family']).upper()}"
        ),
        "handoff_dir": str(paths["reference_h5"].parent),
        "mixture_count": reference.nmixtures,
        "energy_groups": reference.ngroups,
        "legendre_order": max(corrected.scatter) if corrected.scatter else 0,
        "mixture_names": mixture_names,
        "geometry": {
            "kind": "hexagonal",
            "coarse_node_side_cm": coarse_node_side_cm,
            "homogenization_volume_includes_node_catchall": includes_node_catchall,
            "boundary_conditions": boundary_conditions or "unspecified",
            "center_kind": center_kind,
            "neighbor_kinds": (
                None if neighbor_kinds is None else neighbor_kinds.split(",")
            ),
        },
        "decisions": {
            "openmc_sph": "not_used",
            "sph_augment": "native_dragon_sph_applied_to_macrolib",
        },
        "normalization": {
            "method": "DRAGON SPH STD volume-flux normalization",
            "factor": float(flux_metrics["power_normalization_factor"]),
            "formula": "physical_flux = NSPH * DONJON pseudo_flux; normalized by total nu-fission production",
        },
        "sph_target": "native-fixed-source-reaction-rate-equivalence",
        "zero_flux_policy": "reject",
        "identity_bin_count": 0,
        "flux_floor_rel": None,
        "floored_bin_count": 0,
        "freeze_groups": [],
        "frozen_group_bin_count": 0,
        "flux_uncertainty": {
            **flux_uncertainty,
            "ce_max_relative_std_dev": flux_uncertainty[
                "max_relative_std_dev"
            ],
            "mg_max_relative_std_dev": None,
            "ce_flux_dataset": (
                f"{paths['reference_h5']}::/openmc_volume_flux"
                if openmc_flux is not None
                else None
            ),
            "ce_std_dev_dataset": (
                f"{paths['reference_h5']}::/openmc_volume_flux_std_dev"
                if flux_std is not None
                else None
            ),
            "mg_dataset": None,
        },
        "quality": {
            "decision": "native_sph_physics_passed" if passed else "native_sph_review_required",
            "structural_passed": bool(
                native["normal_end"]
                and native["converged"]
                and native["final_flux_solve_converged"]
                and native["one_speed_convergence_provable"]
                and native["factors_unmodified"]
                and native["oscillation_stop_count"] == 0
            ),
            "production_ready": passed,
            "demonstration_quality": passed,
            "max_flux_relative_std_dev": flux_uncertainty[
                "max_relative_std_dev"
            ],
            "production_flux_relative_std_dev_threshold": (
                NATIVE_SPH_FLUX_RELATIVE_STD_DEV_LIMIT
            ),
            "demonstration_flux_relative_std_dev_threshold": 0.2,
            "notes": [
                (
                    "The hash-bound execution deck and material artifacts prove "
                    "that neither ADF nor an empirical eigenvalue multiplier was used."
                    if correction_policy["status"] == "verified_absent"
                    else (
                        "ADF and empirical eigenvalue-factor absence was not "
                        "proved; production acceptance is blocked."
                    )
                ),
                (
                    "The OpenMC-to-DONJON and reference-balance eigenvalue "
                    "gates include the exported conservative balance-score "
                    "bound when available; no covariance is assumed."
                ),
            ],
        },
        "sph": {
            "kind": f"dragon-native-{native['solver_family']}",
            "real": True,
            "applied_to_xs": True,
            "minimum": float(np.min(sph)),
            "maximum": float(np.max(sph)),
            "mean": float(np.mean(sph)),
            "max_abs_delta_from_unity": float(np.max(np.abs(sph - 1.0))),
            "clipped_count": 0,
        },
        "handoff": {
            "augmented_hdf5_has_sph": False,
            "augmented_hdf5_path": str(handoff_paths["augmented_hdf5_path"]),
            "ascii_nsp_block_count": reference.ngroups,
            "ascii_path": str(handoff_paths["macrolib_ascii_path"]),
            "accepted_sph_consumption_format": "macrolib",
            "macrolib_ascii_nsp_block_count": reference.ngroups,
            "macrolib_ascii_path": str(handoff_paths["macrolib_ascii_path"]),
            "reference_macrolib_path": str(handoff_paths["reference_macrolib_path"]),
            "verification_macrolib_path": str(
                handoff_paths["verification_macrolib_path"]
            ),
            "result_listing_path": str(handoff_paths["result_listing_path"]),
            "energy_coverage_path": (
                None if coverage_path is None else str(coverage_path)
            ),
            "converter_receipt_path": (
                None
                if converter_receipt_path is None
                else str(converter_receipt_path)
            ),
            "execution_deck_path": (
                None
                if execution_deck_path is None
                else str(execution_deck_path)
            ),
            "evidence_sha256": evidence_sha256,
        },
        "converter_receipt": converter_receipt,
        "forbidden_corrections_evidence": correction_policy,
        "native_sph": native,
        "energy_coverage": coverage,
        "energy_coverage_validation": coverage_evidence,
        "eigenvalue_validation": {
            "openmc_keff": keff,
            "openmc_keff_std_dev": keff_std,
            "reference_physical_balance_kind": physical_balance_kind,
            "reference_physical_balance_keff": physical_balance_keff,
            "reference_physical_balance_delta_pcm": (
                physical_balance_keff - keff
            )
            * 1.0e5,
            "reference_physical_balance_z": reference_balance_z,
            "reference_collision_balance_kinf": reference.reference_kinf,
            "reference_collision_balance_tally_kinf": collision_balance_tally_kinf,
            "reference_collision_balance_macrolib_vs_tally_delta_pcm": (
                None
                if collision_balance_tally_kinf is None
                else (
                    reference.reference_kinf - collision_balance_tally_kinf
                )
                * 1.0e5
            ),
            "reference_collision_balance_macrolib_vs_tally_z": direct_balance_z,
            "reference_collision_balance_std_dev": collision_balance_std,
            "reference_finite_balance_available": finite_balance_available,
            "reference_finite_balance_keff": finite_balance_keff,
            "reference_finite_balance_std_dev": finite_balance_std,
            "reference_leakage": leakage,
            "reference_leakage_std_dev": leakage_std,
            # Compatibility fields now report the selected physical balance.
            "reference_rate_balance_keff": physical_balance_keff,
            "reference_rate_balance_delta_pcm": (
                physical_balance_keff - keff
            )
            * 1.0e5,
            "reference_rate_balance_z": reference_balance_z,
            "reference_rate_balance_tally_keff": collision_balance_tally_kinf,
            "reference_macrolib_vs_balance_tally_delta_pcm": (
                None
                if collision_balance_tally_kinf is None
                else (
                    reference.reference_kinf - collision_balance_tally_kinf
                )
                * 1.0e5
            ),
            "reference_macrolib_vs_balance_tally_z": direct_balance_z,
            "reference_rate_balance_std_dev": physical_balance_std,
            "reference_rate_balance_combined_std_dev": reference_balance_combined_std,
            "reference_rate_balance_uncertainty_method": (
                "keff-std-only-legacy"
                if physical_balance_std is None
                else rate_balance_uncertainty_method
                or "exported-balance-std-plus-keff-std"
            ),
            "donjon_keff": verification.reference_keff,
            "donjon_delta_pcm": (verification.reference_keff - keff) * 1.0e5,
            "donjon_z": final_keff_z,
            "donjon_combined_std_dev": reference_balance_combined_std,
            "donjon_uncertainty_method": (
                "keff-std-only-legacy"
                if physical_balance_std is None
                else rate_balance_uncertainty_method
                or "exported-balance-std-plus-keff-std"
            ),
            "max_abs_z": max_keff_sigma,
        },
        "component_balance": flux_metrics,
        "acceptance_checks": checks,
        "per_mixture": per_mixture,
    }
    if output_json is not None:
        destination = Path(output_json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def native_sph_correction_policy_evidence(
    *,
    reference_h5: str | Path,
    reference_macrolib: str | Path,
    sph_macrolib: str | Path,
    verify_macrolib: str | Path,
    result_listing: str | Path,
    execution_deck: str | Path | None,
) -> dict[str, Any]:
    """Prove or reject the no-ADF/no-empirical-correction policy.

    The old validator wrote both compatibility fields as unconditional
    ``False``.  This audit instead binds a concrete CLE-2000 deck to the
    echoed source in the DONJON listing and inspects every material artifact.
    Missing or ambiguous evidence is represented by ``used=None`` and blocks
    acceptance.  This function is deterministic and never executes OpenMC or
    DONJON.
    """

    path_map = {
        "reference_h5": Path(reference_h5).expanduser().resolve(),
        "reference_macrolib": Path(reference_macrolib).expanduser().resolve(),
        "sph_macrolib": Path(sph_macrolib).expanduser().resolve(),
        "verify_macrolib": Path(verify_macrolib).expanduser().resolve(),
        "result_listing": Path(result_listing).expanduser().resolve(),
    }
    for label, path in path_map.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label} does not exist: {path}")

    artifact_sha256 = {
        label: _sha256_file(path) for label, path in path_map.items()
    }
    listing = path_map["result_listing"].read_text(
        encoding="utf-8", errors="replace"
    )

    deck_path = (
        None
        if execution_deck is None
        else Path(execution_deck).expanduser().resolve()
    )
    deck_text: str | None = None
    deck_hash: str | None = None
    deck_echoed = False
    deck_code = ""
    shared_issues: list[str] = []
    if deck_path is None:
        shared_issues.append(
            "native-SPH execution deck was not supplied; absence of forbidden corrections cannot be proved"
        )
    elif not deck_path.is_file():
        shared_issues.append(f"native-SPH execution deck does not exist: {deck_path}")
    else:
        deck_text = deck_path.read_text(encoding="utf-8", errors="strict")
        deck_hash = _sha256_file(deck_path)
        deck_echoed = _deck_is_echoed_in_listing(deck_text, listing)
        if not deck_echoed:
            shared_issues.append(
                "execution deck is not reproduced by the source echo in the DONJON result listing"
            )
        deck_code = _deck_code_without_comments_or_strings(deck_text)

    adf_artifact_issues: list[str] = []
    reference_h5_issues = native_sph_reference_issues(path_map["reference_h5"])
    adf_artifact_issues.extend(
        issue for issue in reference_h5_issues if "adf" in issue.lower()
    )
    for label in ("reference_macrolib", "sph_macrolib", "verify_macrolib"):
        macrolib = read_macrolib_ascii(path_map[label])
        if macrolib.adf:
            adf_artifact_issues.append(f"{label} contains ADF records")
    deck_adf_markers = sorted(set(match.group(0) for match in _DECK_ADF_RE.finditer(deck_code)))
    if deck_adf_markers:
        adf_artifact_issues.append(
            "execution deck contains ADF/discontinuity-factor tokens: "
            + ", ".join(deck_adf_markers)
        )
    if adf_artifact_issues:
        adf_used: bool | None = True
    elif deck_text is not None and deck_echoed:
        adf_used = False
    else:
        adf_used = None

    empirical_issues: list[str] = []
    empirical_markers = sorted(
        set(match.group(0) for match in _DECK_EXPLICIT_EMPIRICAL_RE.finditer(deck_code))
    )
    sph_assignment = _DECK_SPH_ASSIGNMENT_RE.search(deck_code)
    direct_transport_consumer: re.Match[str] | None = None
    direct_export: re.Match[str] | None = None
    # CLE-2000's EVALUATE language is general enough to hide a fitted scalar
    # behind an arbitrary variable name.  Until a complete data-flow parser is
    # available, every EVALUATE statement is ambiguous and therefore blocks a
    # proof of absence.  Native SPH production decks do not need EVALUATE.
    ambiguous_evaluations = [
        " ".join(match.group(0).split())
        for match in _DECK_EVALUATE_RE.finditer(deck_code)
    ]
    if empirical_markers:
        empirical_used: bool | None = True
        empirical_issues.append(
            "execution deck contains explicit empirical eigenvalue-factor tokens: "
            + ", ".join(empirical_markers)
        )
    elif deck_text is None or not deck_echoed:
        empirical_used = None
    elif sph_assignment is None:
        empirical_used = None
        empirical_issues.append(
            "execution deck does not contain a direct native SPH assignment "
            "of the form corrected := SPH: reference tracking ::"
        )
    elif ambiguous_evaluations:
        empirical_used = None
        empirical_issues.append(
            "execution deck contains unclassified multiplicative/divisive EVALUATE statements"
        )
    else:
        corrected_name = sph_assignment.group("corrected")
        corrected_assignments = re.findall(
            rf"\b{re.escape(corrected_name)}\s*:=", deck_code, re.IGNORECASE
        )
        direct_transport_consumer = re.search(
            rf"\b[A-Za-z][A-Za-z0-9_]*\s*:=\s*"
            rf"[A-Za-z][A-Za-z0-9_]*:\s+{re.escape(corrected_name)}\b",
            deck_code,
            re.IGNORECASE,
        )
        direct_export = re.search(
            rf"\b[A-Za-z][A-Za-z0-9_]*\s*:=\s*"
            rf"{re.escape(corrected_name)}\s*;",
            deck_code,
            re.IGNORECASE,
        )
        if len(corrected_assignments) != 1:
            empirical_used = None
            empirical_issues.append(
                "native SPH corrected MACROLIB object is reassigned after the SPH: module"
            )
        elif direct_transport_consumer is None or direct_export is None:
            empirical_used = None
            empirical_issues.append(
                "execution deck does not directly consume and export the SPH: corrected MACROLIB"
            )
        else:
            empirical_used = False

    adf_issues = [*shared_issues, *adf_artifact_issues]
    empirical_issues = [*shared_issues, *empirical_issues]
    if adf_used is False and empirical_used is False:
        status = "verified_absent"
    elif adf_used is True or empirical_used is True:
        status = "forbidden_correction_observed"
    else:
        status = "not_provable"
    return {
        "status": status,
        "execution_deck_path": None if deck_path is None else str(deck_path),
        "execution_deck_sha256": deck_hash,
        "deck_reproduced_in_result_listing": deck_echoed,
        "artifact_sha256": artifact_sha256,
        "native_sph_assignment": (
            None
            if sph_assignment is None
            else {
                "corrected_object": sph_assignment.group("corrected"),
                "reference_object": sph_assignment.group("reference"),
                "tracking_object": sph_assignment.group("tracking"),
                "direct_transport_consumer_proved": direct_transport_consumer
                is not None,
                "direct_export_proved": direct_export is not None,
            }
        ),
        "adf": {
            "used": adf_used,
            "evidence_status": _tri_state_evidence_status(adf_used),
            "issues": adf_issues,
        },
        "empirical_eigenvalue_multiplier": {
            "used": empirical_used,
            "evidence_status": _tri_state_evidence_status(empirical_used),
            "issues": empirical_issues,
            "unclassified_evaluate_statements": ambiguous_evaluations,
        },
        "issues": sorted(set(adf_issues + empirical_issues)),
    }


def _tri_state_evidence_status(used: bool | None) -> str:
    if used is True:
        return "observed"
    if used is False:
        return "verified_absent"
    return "not_provable"


def _deck_code_without_comments_or_strings(text: str) -> str:
    without_inline = _DECK_INLINE_COMMENT_RE.sub(" ", text)
    code_lines = []
    for line in without_inline.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("*", "!")):
            continue
        code_lines.append(line)
    return _DECK_STRING_RE.sub("''", "\n".join(code_lines))


def _deck_is_echoed_in_listing(deck: str, listing: str) -> bool:
    """Match the deck, in order, against DONJON's numbered source echo."""

    source_echo = listing.split("->@BEGIN MODULE", 1)[0]
    deck_lines = _normalized_deck_source_lines(deck, strip_sequence=False)
    listing_lines = _normalized_deck_source_lines(source_echo, strip_sequence=True)
    if not deck_lines:
        return False
    cursor = 0
    for expected in deck_lines:
        while cursor < len(listing_lines) and listing_lines[cursor] != expected:
            cursor += 1
        if cursor == len(listing_lines):
            return False
        cursor += 1
    return True


def _normalized_deck_source_lines(
    text: str, *, strip_sequence: bool
) -> list[str]:
    without_inline = _DECK_INLINE_COMMENT_RE.sub(" ", text)
    normalized: list[str] = []
    for line in without_inline.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("*", "!")):
            continue
        if strip_sequence:
            stripped = re.sub(r"\s+\d{4,6}\s*$", "", stripped)
        collapsed = " ".join(stripped.split())
        if collapsed:
            normalized.append(collapsed)
    return normalized


def _native_convergence(listing: str) -> dict[str, Any]:
    iterations = list(_ITERATION_RE.finditer(listing))
    ending = _ENDING_RE.search(listing)
    epsilon_match = _EPSPH_RE.search(listing)
    epsilon = float(epsilon_match.group(1)) if epsilon_match else None
    last = iterations[-1] if iterations else None
    scatter_match = _SCATTER_MOMENTS_RE.search(listing)
    solver_match = _TRACK_SOLVER_RE.search(listing)
    solver_family = (
        "sn" if solver_match and solver_match.group(1).upper() == "SNT" else "spn"
    )
    if solver_family != "sn":
        one_speed_acceleration = "not-applicable"
        one_speed_convergence_provable = True
    elif _SN_GMRES_RE.search(listing):
        # SNGMRE returns after MAXIT without an explicit failure marker in
        # DRAGON 5.1.  Until the listing contract proves every solve ended
        # before MAXIT, an explicit GMRES deck cannot be production evidence.
        one_speed_acceleration = "gmres"
        one_speed_convergence_provable = False
    elif _SN_DSA_RE.search(listing):
        one_speed_acceleration = "dsa"
        one_speed_convergence_provable = True
    elif _SN_LIVOLANT_RE.search(listing):
        one_speed_acceleration = "livolant"
        one_speed_convergence_provable = True
    else:
        # SNF's default Livolant path emits explicit MAXIMUM/UNABLE markers,
        # both of which are hard failures below.
        one_speed_acceleration = "livolant-default"
        one_speed_convergence_provable = True
    rms_error = float(last.group(3)) if last else None
    max_error = float(last.group(2)) if last else None
    converged = bool(
        ending
        and epsilon is not None
        and rms_error is not None
        and rms_error <= epsilon
    )
    flux_nonconvergence_counts = {
        marker: listing.count(marker) for marker in _FLUX_NONCONVERGENCE_MARKERS
    }
    flux_nonconvergence_count = sum(flux_nonconvergence_counts.values())
    negative_factor_corrections = len(_NEGATIVE_SPH_FACTOR_RE.findall(listing))
    oscillation_stop_count = listing.lower().count(_SPH_OSCILLATION_STOP.lower())
    return {
        "solver": (
            "DRAGON SPH with SNT SN"
            if solver_family == "sn"
            else "DRAGON SPH with TRIVAT SPN"
        ),
        "solver_family": solver_family,
        "one_speed_acceleration": one_speed_acceleration,
        "one_speed_convergence_provable": one_speed_convergence_provable,
        "scattering_moments_used": (
            int(scatter_match.group(1)) if scatter_match else None
        ),
        "iterations": int(ending.group(1)) if ending else None,
        "epsilon": epsilon,
        "final_max_factor_update": max_error,
        "final_rms_factor_update": rms_error,
        "converged": converged,
        "factors_unmodified": negative_factor_corrections == 0,
        "negative_factor_correction_count": negative_factor_corrections,
        "oscillation_stop_count": oscillation_stop_count,
        "final_flux_solve_converged": flux_nonconvergence_count == 0,
        "flux_nonconvergence_count": flux_nonconvergence_count,
        "flux_nonconvergence_markers": {
            marker: count
            for marker, count in flux_nonconvergence_counts.items()
            if count
        },
        "normal_end": "normal end of execution for donjon" in listing.lower(),
    }


def _flux_and_balance_metrics(reference, corrected, verification) -> dict[str, Any]:
    reference_production = np.asarray(reference.nusigf, dtype=float) * np.asarray(
        reference.flux_intg, dtype=float
    )
    calculated_production = np.asarray(corrected.nusigf, dtype=float) * np.asarray(
        verification.flux_intg, dtype=float
    )
    reference_production_sum = float(np.sum(reference_production))
    denominator = float(np.sum(calculated_production))
    if not math.isfinite(reference_production_sum) or reference_production_sum <= 0.0:
        raise ValueError("reference MACROLIB has no finite positive fission production")
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("verification macrolib has no positive fission production")
    scale = reference_production_sum / denominator
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("native SPH power-normalization factor is not finite and positive")
    physical_flux = verification.flux_intg * scale * corrected.sph
    _require_positive_finite_matrix(
        physical_flux, "normalized native-SPH physical flux"
    )

    reference_loss = (
        reference.ntot0 - np.sum(reference.scatter[0], axis=2)
    ) * reference.flux_intg
    calculated_loss = (
        corrected.ntot0 - np.sum(corrected.scatter[0], axis=2)
    ) * verification.flux_intg * scale
    relative_flux = physical_flux / reference.flux_intg - 1.0
    if not np.all(np.isfinite(reference_loss)) or not np.all(
        np.isfinite(calculated_loss)
    ):
        raise ValueError("native SPH net-loss balance contains non-finite values")
    component_rows = []
    for index in range(reference.nmixtures):
        loss_ref = float(np.sum(reference_loss[index]))
        loss_calc = float(np.sum(calculated_loss[index]))
        if not math.isfinite(loss_ref) or loss_ref <= 0.0:
            raise ValueError(
                "reference MACROLIB mixture "
                f"{index + 1} has no finite positive net-loss balance"
            )
        if not math.isfinite(loss_calc) or loss_calc <= 0.0:
            raise ValueError(
                "verification MACROLIB mixture "
                f"{index + 1} has no finite positive net-loss balance"
            )
        component_rows.append(
            {
                "mixture_index": index + 1,
                "net_loss_reference": loss_ref,
                "net_loss_donjon": loss_calc,
                "net_loss_relative_residual": loss_calc / loss_ref - 1.0,
                "flux_rms_relative_residual": float(
                    np.sqrt(np.mean(relative_flux[index] ** 2))
                ),
                "flux_max_relative_residual": float(
                    np.max(np.abs(relative_flux[index]))
                ),
            }
        )
    total_reference_loss = float(np.sum(reference_loss))
    total_calculated_loss = float(np.sum(calculated_loss))
    if not math.isfinite(total_reference_loss) or total_reference_loss <= 0.0:
        raise ValueError("reference MACROLIB has no finite positive net-loss balance")
    if not math.isfinite(total_calculated_loss) or total_calculated_loss <= 0.0:
        raise ValueError("verification MACROLIB has no finite positive net-loss balance")
    return {
        "power_normalization_factor": scale,
        "reference_net_loss": total_reference_loss,
        "donjon_net_loss": total_calculated_loss,
        "net_loss_relative_residual": float(
            total_calculated_loss / total_reference_loss - 1.0
        ),
        "flux_rms_relative_residual": float(np.sqrt(np.mean(relative_flux**2))),
        "flux_max_relative_residual": float(np.max(np.abs(relative_flux))),
        "per_component": component_rows,
        "physical_flux": physical_flux,
    }


def _require_positive_finite_matrix(values: Any, label: str) -> None:
    matrix = np.asarray(values, dtype=float)
    if matrix.size == 0 or not np.all(np.isfinite(matrix)) or np.any(matrix <= 0.0):
        raise ValueError(f"{label} must contain only finite, strictly positive values")


def _flux_uncertainty_evidence(
    openmc_flux: np.ndarray | None,
    flux_std: np.ndarray | None,
    *,
    reference_flux: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray | None]:
    """Validate that statistical precision is tied to the converted reference."""

    issues: list[str] = []
    if openmc_flux is None:
        issues.append("reference HDF5 has no /openmc_volume_flux dataset")
    if flux_std is None:
        issues.append("reference HDF5 has no /openmc_volume_flux_std_dev dataset")

    relative_std: np.ndarray | None = None
    arrays_valid = openmc_flux is not None and flux_std is not None
    if arrays_valid:
        assert openmc_flux is not None
        assert flux_std is not None
        if openmc_flux.shape != reference_flux.shape:
            issues.append(
                "/openmc_volume_flux shape does not match reference MACROLIB "
                f"FLUX-INTG: {openmc_flux.shape} != {reference_flux.shape}"
            )
            arrays_valid = False
        if flux_std.shape != reference_flux.shape:
            issues.append(
                "/openmc_volume_flux_std_dev shape does not match reference "
                f"MACROLIB FLUX-INTG: {flux_std.shape} != {reference_flux.shape}"
            )
            arrays_valid = False
        if not np.all(np.isfinite(openmc_flux)) or np.any(openmc_flux <= 0.0):
            issues.append(
                "/openmc_volume_flux must contain only finite, strictly positive values"
            )
            arrays_valid = False
        if not np.all(np.isfinite(flux_std)) or np.any(flux_std < 0.0):
            issues.append(
                "/openmc_volume_flux_std_dev must contain only finite, "
                "non-negative values"
            )
            arrays_valid = False

    reference_matches = False
    if arrays_valid:
        assert openmc_flux is not None
        assert flux_std is not None
        reference_matches = bool(
            np.allclose(
                openmc_flux,
                reference_flux,
                rtol=2.0e-6,
                atol=1.0e-12,
            )
        )
        if not reference_matches:
            issues.append(
                "/openmc_volume_flux does not match the converted reference "
                "MACROLIB FLUX-INTG"
            )
        relative_std = flux_std / openmc_flux

    max_relative_std = (
        None if relative_std is None else float(np.max(relative_std))
    )
    within_limit = bool(
        max_relative_std is not None
        and math.isfinite(max_relative_std)
        and max_relative_std <= NATIVE_SPH_FLUX_RELATIVE_STD_DEV_LIMIT
    )
    evidence_valid = bool(
        openmc_flux is not None
        and flux_std is not None
        and arrays_valid
    )
    return (
        {
            "required": True,
            "evidence_valid": evidence_valid,
            "reference_flux_matches_macrolib": reference_matches,
            "max_relative_std_dev": max_relative_std,
            "production_relative_std_dev_limit": (
                NATIVE_SPH_FLUX_RELATIVE_STD_DEV_LIMIT
            ),
            "within_production_limit": within_limit,
            "issues": issues,
        },
        relative_std,
    )


def _read_coverage(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    candidate = Path(path).resolve()
    if not candidate.is_file():
        raise FileNotFoundError(f"energy coverage summary does not exist: {candidate}")
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("energy coverage summary must be a JSON object")
    return payload


def _energy_coverage_evidence(
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate the score-level coverage calculation, not just its decision."""

    if payload is None:
        return {
            "required": True,
            "present": False,
            "schema_valid": False,
            "self_consistent": False,
            "passed": False,
            "score_names": [],
            "issues": ["energy coverage summary was not supplied"],
        }

    issues: list[str] = []
    schema_valid = payload.get("schema") in ENERGY_COVERAGE_COMPATIBLE_SCHEMAS
    if not schema_valid:
        issues.append(
            "energy coverage schema must be "
            f"{ENERGY_COVERAGE_SCHEMA} (the legacy IRENA schema is read-only compatible)"
        )

    for key in ("statepoint", "energy_mesh_id"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"energy coverage {key} must be a non-empty string")

    numeric_fields = {
        key: _finite_json_number(payload.get(key))
        for key in (
            "full_energy_min_ev",
            "mg_energy_min_ev",
            "mg_energy_max_ev",
            "full_energy_max_ev",
            "max_outside_fraction",
        )
    }
    for key, value in numeric_fields.items():
        if value is None:
            issues.append(f"energy coverage {key} must be finite numeric evidence")

    threshold = numeric_fields["max_outside_fraction"]
    if threshold is not None and not 0.0 <= threshold < 1.0:
        issues.append("energy coverage max_outside_fraction must satisfy 0 <= x < 1")

    energy_bounds = tuple(
        numeric_fields[key]
        for key in (
            "full_energy_min_ev",
            "mg_energy_min_ev",
            "mg_energy_max_ev",
            "full_energy_max_ev",
        )
    )
    if all(value is not None for value in energy_bounds):
        full_min, mg_min, mg_max, full_max = energy_bounds
        assert full_min is not None
        assert mg_min is not None
        assert mg_max is not None
        assert full_max is not None
        if not full_min <= mg_min < mg_max <= full_max:
            issues.append(
                "energy coverage bounds must satisfy "
                "full_min <= mg_min < mg_max <= full_max"
            )

    scores = payload.get("scores")
    score_names: list[str] = []
    calculated_passes: list[bool] = []
    rows_complete = True
    if not isinstance(scores, dict):
        issues.append("energy coverage scores must be an object")
        rows_complete = False
    else:
        score_names = sorted(str(name) for name in scores)
        missing = sorted(ENERGY_COVERAGE_REQUIRED_SCORES.difference(scores))
        unexpected = sorted(set(scores).difference(ENERGY_COVERAGE_REQUIRED_SCORES))
        if missing:
            issues.append("energy coverage scores are missing: " + ", ".join(missing))
            rows_complete = False
        if unexpected:
            issues.append(
                "energy coverage scores are not part of the declared schema: "
                + ", ".join(str(name) for name in unexpected)
            )
            rows_complete = False

        for score_name, row in scores.items():
            if not isinstance(row, dict):
                issues.append(f"energy coverage score {score_name!r} must be an object")
                rows_complete = False
                continue
            row_values = {
                key: _finite_json_number(row.get(key))
                for key in ("low_tail", "retained", "high_tail", "outside_fraction")
            }
            row_valid = True
            for key, value in row_values.items():
                if value is None:
                    issues.append(
                        f"energy coverage score {score_name!r} {key} must be finite"
                    )
                    row_valid = False
            for key in ("low_tail", "retained", "high_tail"):
                value = row_values[key]
                if value is not None and value < 0.0:
                    issues.append(
                        f"energy coverage score {score_name!r} {key} must be non-negative"
                    )
                    row_valid = False
            declared_passed = row.get("passed")
            if not isinstance(declared_passed, bool):
                issues.append(
                    f"energy coverage score {score_name!r} passed must be boolean"
                )
                row_valid = False
            if threshold is None or not 0.0 <= threshold < 1.0:
                row_valid = False

            if not row_valid:
                rows_complete = False
                continue
            low_tail = row_values["low_tail"]
            retained = row_values["retained"]
            high_tail = row_values["high_tail"]
            outside_fraction = row_values["outside_fraction"]
            assert low_tail is not None
            assert retained is not None
            assert high_tail is not None
            assert outside_fraction is not None
            assert threshold is not None
            total = low_tail + retained + high_tail
            if not math.isfinite(total) or total <= 0.0:
                issues.append(
                    f"energy coverage score {score_name!r} has no positive total"
                )
                rows_complete = False
                continue
            calculated_fraction = (low_tail + high_tail) / total
            if not math.isclose(
                outside_fraction,
                calculated_fraction,
                rel_tol=1.0e-9,
                abs_tol=1.0e-12,
            ):
                issues.append(
                    f"energy coverage score {score_name!r} outside_fraction "
                    "does not equal (low_tail + high_tail) / total"
                )
                rows_complete = False
            calculated_passed = calculated_fraction <= threshold
            calculated_passes.append(calculated_passed)
            if declared_passed is not calculated_passed:
                issues.append(
                    f"energy coverage score {score_name!r} passed flag is "
                    "inconsistent with max_outside_fraction"
                )
                rows_complete = False

    decision = payload.get("decision")
    if decision not in {"passed", "failed", "rejected"}:
        issues.append(
            "energy coverage decision must be 'passed', 'failed', or 'rejected'"
        )
    elif rows_complete and len(calculated_passes) == len(
        ENERGY_COVERAGE_REQUIRED_SCORES
    ):
        calculated_passed = all(calculated_passes)
        if (decision == "passed") is not calculated_passed:
            issues.append(
                "energy coverage decision is inconsistent with the score-level results"
            )

    self_consistent = not issues
    return {
        "required": True,
        "present": True,
        "schema_valid": schema_valid,
        "self_consistent": self_consistent,
        "passed": bool(self_consistent and decision == "passed"),
        "score_names": score_names,
        "issues": issues,
    }


def _finite_json_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def converter_receipt_issues(
    receipt_path: str | Path,
    *,
    reference_h5: str | Path,
    reference_macrolib: str | Path,
) -> list[str]:
    """Validate the live Converter receipt linked by native-SPH evidence.

    The receipt binds the exact HDF5 consumed by Converter to the uncorrected
    MACROLIB used as DRAGON's native-SPH starting point.  Paths and digests are
    both checked so copying a valid receipt beside different artifacts cannot
    qualify a handoff.
    """

    candidate = Path(receipt_path).expanduser().resolve()
    input_path = Path(reference_h5).expanduser().resolve()
    output_path = Path(reference_macrolib).expanduser().resolve()
    if not candidate.is_file():
        return [f"Converter receipt does not exist: {candidate}"]
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read Converter receipt: {exc}"]
    if not isinstance(payload, dict):
        return ["Converter receipt must be a JSON object"]

    issues: list[str] = []
    if payload.get("schema") != CONVERTER_RECEIPT_SCHEMA:
        issues.append(f"Converter receipt schema must be {CONVERTER_RECEIPT_SCHEMA}")
    if payload.get("ok") is not True or payload.get("converted") is not True:
        issues.append("Converter receipt does not record a completed conversion")
    if payload.get("dry_run") is not False:
        issues.append("Converter receipt records a dry run")
    if payload.get("format") != "macrolib":
        issues.append("Converter receipt output format is not macrolib")
    issues.extend(production_receipt_policy_issues(payload))
    if payload.get("preflight_ok") is not True:
        issues.append("Converter receipt did not pass preflight")
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        issues.append("Converter receipt does not contain a production preflight report")
    else:
        if preflight.get("schema") != "openmc2donjon.mgxs-input-contract.v1":
            issues.append("Converter preflight schema is not recognized")
        if preflight.get("decision") != "mgxs_input_contract_passed":
            issues.append("Converter production preflight did not pass")
        preflight_inputs = preflight.get("inputs")
        if not isinstance(preflight_inputs, list) or not preflight_inputs:
            issues.append("Converter preflight does not contain an inspected input")
        elif any(
            not isinstance(item, dict) or item.get("ok") is not True
            for item in preflight_inputs
        ):
            issues.append("Converter preflight contains a rejected input")
    if payload.get("physical_sph_required") is not False:
        issues.append(
            "Converter receipt must explicitly record "
            "physical_sph_required=false for a native-SPH reference"
        )
    if not _receipt_path_matches(payload.get("input_path"), input_path):
        issues.append("Converter receipt input path does not match reference HDF5")
    if not _receipt_path_matches(payload.get("output_path"), output_path):
        issues.append("Converter receipt output path does not match reference MACROLIB")
    if payload.get("input_sha256") != _sha256_file(input_path):
        issues.append("Converter receipt input hash does not match reference HDF5")
    if payload.get("output_sha256") != _sha256_file(output_path):
        issues.append("Converter receipt output hash does not match reference MACROLIB")
    try:
        from .openmc_provenance import read_openmc_provenance

        embedded_provenance = read_openmc_provenance(input_path)
    except (OSError, TypeError, ValueError) as exc:
        embedded_provenance = None
        issues.append(f"cannot verify reference HDF5 OpenMC provenance: {exc}")
    receipt_provenance = payload.get("openmc_provenance")
    if embedded_provenance is None:
        issues.append("reference HDF5 has no embedded OpenMC fine-reference provenance")
    else:
        integrity = embedded_provenance.get("integrity")
        capabilities = embedded_provenance.get("capabilities")
        if not isinstance(integrity, dict) or integrity.get("ok") is not True:
            issues.append("reference HDF5 OpenMC provenance integrity is invalid")
        if not isinstance(capabilities, dict) or capabilities.get(
            "reference_bound"
        ) is not True:
            issues.append("reference HDF5 is not a hash-bound OpenMC fine reference")
        if not isinstance(capabilities, dict) or capabilities.get(
            "transport_reproducible"
        ) is not True:
            issues.append(
                "reference HDF5 does not carry a complete reproducible OpenMC "
                "transport input chain"
            )
        if not isinstance(receipt_provenance, dict):
            issues.append("Converter receipt does not contain OpenMC provenance")
        elif receipt_provenance.get("digest_sha256") != embedded_provenance.get(
            "digest_sha256"
        ):
            issues.append(
                "Converter receipt OpenMC provenance does not match reference HDF5"
            )
    return issues


def production_receipt_policy_issues(payload: dict[str, Any]) -> list[str]:
    """Require explicit evidence that Converter used its production preset.

    An engineering ``--check`` can produce the same generic preflight decision
    string as ``--production`` while applying a weaker set of requirements.
    The receipt therefore records both the requested level and whether a
    preflight actually ran; acceptance consumers fail closed on missing or
    contradictory policy metadata.
    """

    issues: list[str] = []
    if payload.get("production_requested") is not True:
        issues.append("Converter receipt does not record production_requested=true")
    policy = payload.get("preflight_policy")
    issues.extend(canonical_production_policy_issues(policy))
    if not isinstance(policy, dict):
        return issues
    effective = policy.get("effective_thresholds")
    if not isinstance(effective, dict):
        return issues

    preflight = payload.get("preflight")
    inputs = preflight.get("inputs") if isinstance(preflight, dict) else None
    if not isinstance(inputs, list) or not inputs:
        return issues
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            continue
        prefix = f"Converter receipt MGXS preflight input {index + 1}"
        scatter = item.get("scatter_row_balance")
        physics = item.get("physics_checks")
        uncertainty = item.get("uncertainty")
        _require_effective_threshold(
            issues,
            prefix,
            scatter,
            "fail_threshold",
            effective,
            "scatter_row_balance_fail",
        )
        _require_effective_threshold(
            issues,
            prefix,
            physics,
            "chi_sum_tolerance",
            effective,
            "chi_sum_tolerance",
        )
        _require_effective_threshold(
            issues,
            prefix,
            physics,
            "transport_p1_fail_threshold",
            effective,
            "transport_p1_fail",
        )
        _require_effective_threshold(
            issues,
            prefix,
            uncertainty,
            "warn_threshold",
            effective,
            "uncertainty_warn",
        )
        _require_effective_threshold(
            issues,
            prefix,
            uncertainty,
            "fail_threshold",
            effective,
            "uncertainty_fail",
        )
        _require_effective_threshold(
            issues,
            prefix,
            uncertainty,
            "production_fail_threshold",
            effective,
            "uncertainty_production_fail",
        )
        _require_effective_threshold(
            issues,
            prefix,
            uncertainty,
            "mean_abs_floor",
            effective,
            "uncertainty_mean_abs_floor",
        )
        if not isinstance(uncertainty, dict) or uncertainty.get("checked") is not True:
            issues.append(f"{prefix} did not execute uncertainty checks")
        if (
            not isinstance(uncertainty, dict)
            or uncertainty.get("require_coverage") is not True
        ):
            issues.append(f"{prefix} did not require std-dev coverage")
    return issues


def _require_effective_threshold(
    issues: list[str],
    prefix: str,
    report: Any,
    report_key: str,
    effective: dict[str, Any],
    policy_key: str,
) -> None:
    report_value = report.get(report_key) if isinstance(report, dict) else None
    policy_value = effective.get(policy_key)
    if not _same_numeric_value(report_value, policy_value):
        issues.append(
            f"{prefix} {report_key} does not match effective production "
            f"threshold {policy_key}"
        )


def _same_numeric_value(left: Any, right: Any) -> bool:
    if (
        not isinstance(left, (int, float))
        or isinstance(left, bool)
        or not isinstance(right, (int, float))
        or isinstance(right, bool)
    ):
        return False
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=0.0)


def _converter_receipt_evidence(
    receipt_path: Path | None,
    *,
    reference_h5: Path,
    reference_macrolib: Path,
) -> dict[str, Any]:
    if receipt_path is None:
        issues = ["Converter receipt was not supplied"]
    else:
        issues = converter_receipt_issues(
            receipt_path,
            reference_h5=reference_h5,
            reference_macrolib=reference_macrolib,
        )
    return {
        "required": True,
        "path": None if receipt_path is None else str(receipt_path),
        "valid": not issues,
        "issues": issues,
        "input_path": str(reference_h5),
        "input_sha256": _sha256_file(reference_h5),
        "output_path": str(reference_macrolib),
        "output_sha256": _sha256_file(reference_macrolib),
    }


def _receipt_path_matches(value: Any, expected: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return Path(value).expanduser().resolve() == expected


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_positive(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) and result > 0.0 else None


def _optional_nonnegative(value: Any) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip()
    return text or None
