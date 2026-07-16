#!/usr/bin/env python3
"""Strict physical acceptance for the IRENA 21-orbit / 91-position route.

This validator is intentionally downstream of ``validate-native-sph``.  The
native-SPH physics summary proves the 21-orbit fixed point and final transport
solve; this module independently checks those hard gates against the listing,
then validates the resulting *physical* 91-position full core against OpenMC.

The two DONJON editions have different, non-interchangeable purposes:

* ``OUT: ... INTG IN`` is a 91-region MACROLIB.  Its group-wise
  ``H-FACTOR * FLUX-INTG`` values are the 91 physical position powers.
* ``EDI: ... MERG MIX COND SAVE`` is a 21-orbit aggregate.  It is used only
  for global production, collision-loss, and leakage closure.

No 21-orbit power average is expanded back onto the 91 positions.  No ADF,
empirical eigenvalue multiplier, clipping, floor, frozen group, or zero-bin
fill is permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from openmc2donjon.macrolib import Macrolib, read_macrolib_ascii
from openmc2donjon.native_sph_validation import converter_receipt_issues


SCHEMA = "openmc2donjon.irena30-orbit-fullcore-physics.v1"
N_ORBITS = 21
N_POSITIONS = 91
FUEL_MATERIALS = frozenset({"INT", "EXT"})

_SPH_ITERATION_RE = re.compile(
    r"SPHEQU:\s+ITER=\s*(\d+)\s+ERROR=\s*([0-9.Ee+\-]+)"
    r"\s+ERR 2=\s*([0-9.Ee+\-]+)"
)
_SPH_END_RE = re.compile(
    r"SPHEQU:\s+ENDING OF SPH CONVERGENCE AFTER\s+(\d+)\s+ITERATIONS"
)
_EPSPH_RE = re.compile(r"EPSPH\s+([0-9.Ee+\-]+)\s+\(CONVERGENCE CRITERION\)")
_FINAL_KEFF_RE = re.compile(
    r"OPENMC2DONJON IRENA30 FULLCORE NATIVE SPH FINAL K-EFFECTIVE"
    r"\s+([0-9.Ee+\-]+)"
)
_TRACK_SOLVER_RE = re.compile(r"TRACK\s*:=\s*(SNT|TRIVAT):", re.IGNORECASE)
_NEGATIVE_FACTOR_RE = re.compile(
    r"negative SPH factor in group\s+\d+\s+and region\s+\d+\s+set to 1\.0",
    re.IGNORECASE,
)
_GMRES_RE = re.compile(r"\bGMRES\s+\d+\s+MAXI\s+\d+", re.IGNORECASE)
_DSA_RE = re.compile(r"\bDSA\s+\d+\s+\d+\s+[12]\b", re.IGNORECASE)
_LIVOLANT_RE = re.compile(r"\bLIVO\s+\d+\s+\d+\b", re.IGNORECASE)
_OSCILLATION_MARKER = "maximum of 3 error oscillations in SPH convergence reached"
_NONCONVERGENCE_MARKERS = (
    "SNF: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.",
    "SNF: UNABLE TO CONVERGE ONE-SPEED ITERATIONS IN GROUP",
    "TRIFLV: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.",
    "TRIFLV: UNABLE TO CONVERGE ONE-SPEED ITERATIONS.",
    "PNFLV: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.",
    "PNFLV: UNABLE TO CONVERGE ONE-SPEED ITERATIONS.",
    "FLU2DR: CONVERGENCE NOT REACHED",
    "MAXIMUM NUMBER OF EXTERNAL ITERATIONS IS REACHED",
    "MAXIMUM NUMBER OF THERMAL ITERATIONS IS REACHED",
)
_NATIVE_EVIDENCE_PATHS = (
    "augmented_hdf5_path",
    "reference_macrolib_path",
    "macrolib_ascii_path",
    "verification_macrolib_path",
    "result_listing_path",
    "converter_receipt_path",
)


def _load_orbits():
    path = Path(__file__).with_name("global_orbits.py")
    name = "_openmc2donjon_irena30_global_orbits_for_validation"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load strict IRENA orbit declaration: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ORBITS = _load_orbits()
EXPECTED_POSITION_NAMES = tuple(
    f"R{ring}P{position:02d}_{ORBITS.material_for_position(ring, position)}"
    for ring, position in ORBITS.POSITION_ORDER
)
EXPECTED_MATERIALS = tuple(
    ORBITS.material_for_position(ring, position)
    for ring, position in ORBITS.POSITION_ORDER
)
EXPECTED_ORBIT_NUMBERS = tuple(ORBITS.MIXTURE_MAP)
EXPECTED_FUEL_MASK = np.asarray(
    [material in FUEL_MATERIALS for material in EXPECTED_MATERIALS], dtype=bool
)


def validate_orbit_fullcore(
    physics_summary: str | Path | Mapping[str, Any],
    reference_h5: str | Path,
    region_verify: str | Path,
    edi_output: str | Path,
    result_listing: str | Path,
    *,
    output_json: str | Path | None = None,
    max_keff_sigma: float = 2.0,
    max_leakage_delta: float = 0.005,
    max_power_rms_relative: float = 0.01,
    max_power_relative: float = 0.02,
    max_openmc_power_relative_std: float = 0.10,
    reaction_rate_closure_rtol: float = 2.0e-5,
) -> dict[str, Any]:
    """Validate one strict full-core native-SPH result without fitting it."""

    criteria = {
        "max_abs_keff_z": _positive_finite(max_keff_sigma, "max_keff_sigma"),
        "max_abs_leakage_fraction_delta": _positive_finite(
            max_leakage_delta, "max_leakage_delta"
        ),
        "max_power_rms_relative_error": _positive_finite(
            max_power_rms_relative, "max_power_rms_relative"
        ),
        "max_power_relative_error": _positive_finite(
            max_power_relative, "max_power_relative"
        ),
        "max_openmc_active_power_relative_std_dev": _positive_finite(
            max_openmc_power_relative_std, "max_openmc_power_relative_std"
        ),
        "reaction_rate_closure_relative_tolerance": _positive_finite(
            reaction_rate_closure_rtol, "reaction_rate_closure_rtol"
        ),
        "adf_used": False,
        "empirical_eigenvalue_multiplier_used": False,
        "power_aggregation_for_acceptance": "91 physical positions",
    }

    paths = {
        "reference_h5": Path(reference_h5).expanduser().resolve(),
        "region_verify": Path(region_verify).expanduser().resolve(),
        "edi_output": Path(edi_output).expanduser().resolve(),
        "result_listing": Path(result_listing).expanduser().resolve(),
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label} does not exist: {path}")

    summary, summary_path = _read_summary(physics_summary)
    reference = _read_openmc_reference(paths["reference_h5"])
    region = read_macrolib_ascii(paths["region_verify"])
    edi = read_macrolib_ascii(paths["edi_output"])
    listing_text = paths["result_listing"].read_text(
        encoding="utf-8", errors="replace"
    )
    listing = _listing_evidence(
        listing_text,
        factor_count=N_ORBITS * region.ngroups,
    )

    _validate_summary_shape(summary)
    _validate_region_shape(region)
    _validate_edi_shape(edi)
    native_evidence = _native_evidence_audit(summary, summary_path)

    region_keff = _required_positive(region.reference_keff, "region K-EFFECTIVE")
    edi_keff = _required_positive(edi.reference_keff, "EDI K-EFFECTIVE")
    listing_keff = _required_positive(listing["final_keff"], "listing final keff")
    summary_keff = _nested_positive(
        summary, "eigenvalue_validation", "donjon_keff"
    )
    keff_consistent = bool(
        _close_ascii(region_keff, listing_keff)
        and _close_ascii(region_keff, summary_keff)
    )

    keff_combined_std = reference["keff_std_dev"] + reference[
        "finite_balance_std_dev"
    ]
    keff_z = (region_keff - reference["keff"]) / keff_combined_std
    reference_finite_balance_z = (
        reference["finite_balance_keff"] - reference["keff"]
    ) / keff_combined_std
    keff_delta_pcm = (region_keff / reference["keff"] - 1.0) * 1.0e5

    region_balance = _neutron_balance(region, region_keff)
    edi_balance = _neutron_balance(edi, region_keff)
    production_closure = _relative_delta(
        edi_balance["fission_production"], region_balance["fission_production"]
    )
    collision_loss_closure = _relative_delta(
        edi_balance["net_collision_loss"], region_balance["net_collision_loss"]
    )
    leakage_delta = (
        edi_balance["leakage_fraction"] - reference["leakage_fraction"]
    )
    leakage_z = (
        None
        if reference["leakage_std_dev"] == 0.0
        else leakage_delta / reference["leakage_std_dev"]
    )

    donjon_power = _position_power(region)
    power = _power_metrics(
        reference["position_power"],
        reference["position_power_std_dev"],
        donjon_power,
    )

    native_checks = _native_summary_checks(summary, listing, paths["result_listing"])
    checks: dict[str, bool] = {
        **native_checks,
        **native_evidence["checks"],
        "strict_21_orbit_native_sph_summary": summary.get("mixture_count")
        == N_ORBITS,
        "openmc_reference_is_91_position_unaggregated": bool(
            reference["position_count"] == N_POSITIONS
            and reference["orbit_aggregation_used"] is False
        ),
        "donjon_region_edition_has_91_positions": region.nmixtures == N_POSITIONS,
        "donjon_edi_has_21_orbits": edi.nmixtures == N_ORBITS,
        "region_edi_production_closure": abs(production_closure)
        <= criteria["reaction_rate_closure_relative_tolerance"],
        "region_edi_collision_loss_closure": abs(collision_loss_closure)
        <= criteria["reaction_rate_closure_relative_tolerance"],
        "keff_evidence_consistent": keff_consistent,
        "region_edi_keff_consistent": _close_ascii(region_keff, edi_keff),
        "keff_within_statistical_gate": abs(keff_z)
        <= criteria["max_abs_keff_z"],
        "openmc_finite_balance_within_statistical_gate": abs(
            reference_finite_balance_z
        )
        <= criteria["max_abs_keff_z"],
        "native_summary_reference_matches_h5": _summary_reference_matches_h5(
            summary, reference
        ),
        "summary_and_input_use_same_reference_h5": _summary_reference_path_matches(
            summary, paths["reference_h5"]
        ),
        "leakage_within_gate": abs(leakage_delta)
        <= criteria["max_abs_leakage_fraction_delta"],
        "openmc_active_power_uncertainty_within_limit": power[
            "openmc_max_active_relative_std_dev"
        ]
        <= criteria["max_openmc_active_power_relative_std_dev"],
        "normalized_91_position_power_rms_within_gate": power[
            "rms_relative_error"
        ]
        <= criteria["max_power_rms_relative_error"],
        "normalized_91_position_power_max_within_gate": power[
            "maximum_absolute_relative_error"
        ]
        <= criteria["max_power_relative_error"],
        "nonfuel_power_remains_zero": power["donjon_nonfuel_power_fraction"]
        <= 1.0e-12,
        "adf_absent": not region.adf and not edi.adf,
        "empirical_eigenvalue_multiplier_absent": _no_empirical_factor(summary),
        "no_nonphysical_sph_bin_policy": _no_nonphysical_sph_bin_policy(summary),
        "real_native_sph_applied_to_cross_sections": _real_native_sph(summary),
    }
    passed = all(checks.values())

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "decision": (
            "irena30_orbit_fullcore_physics_passed"
            if passed
            else "irena30_orbit_fullcore_review_required"
        ),
        "route": (
            "OpenMC CE 91-position fine full core -> Converter 21 D3 orbits -> "
            "DRAGON native SPH -> DONJON 91-position verification"
        ),
        "criteria": criteria,
        "acceptance_checks": checks,
        "native_sph": {
            "summary_schema": summary.get("schema"),
            "summary_decision": _nested(summary, "quality", "decision"),
            "iterations": _nested(summary, "native_sph", "iterations"),
            "epsilon": _nested(summary, "native_sph", "epsilon"),
            "final_rms_factor_update": _nested(
                summary, "native_sph", "final_rms_factor_update"
            ),
            "solver_family": _nested(summary, "native_sph", "solver_family"),
            "listing": listing,
            "evidence_audit": native_evidence,
        },
        "eigenvalue": {
            "openmc_keff": reference["keff"],
            "openmc_keff_std_dev": reference["keff_std_dev"],
            "openmc_finite_balance_std_dev": reference[
                "finite_balance_std_dev"
            ],
            "openmc_finite_balance_keff": reference["finite_balance_keff"],
            "openmc_finite_balance_z": reference_finite_balance_z,
            "combined_std_dev_conservative_l1": keff_combined_std,
            "donjon_keff": region_keff,
            "delta_pcm_relative": keff_delta_pcm,
            "z": keff_z,
        },
        "leakage": {
            "openmc_fraction": reference["leakage_fraction"],
            "openmc_std_dev": reference["leakage_std_dev"],
            "donjon_fraction": edi_balance["leakage_fraction"],
            "fraction_delta": leakage_delta,
            "z_openmc_only": leakage_z,
            "region_balance": region_balance,
            "edi_balance": edi_balance,
            "edi_vs_region_fission_production_relative_delta": production_closure,
            "edi_vs_region_collision_loss_relative_delta": collision_loss_closure,
        },
        "power_shape": power,
        "evidence": {
            "physics_summary": summary_path,
            **{label: str(path) for label, path in paths.items()},
            "input_sha256": {
                "physics_summary": (
                    _sha256_file(Path(summary_path))
                    if summary_path is not None
                    else _sha256_json(summary)
                ),
                **{label: _sha256_file(path) for label, path in paths.items()},
            },
            "region_power_source": "OUT: INTG IN; H-FACTOR * FLUX-INTG",
            "edi_role": "21-orbit aggregate used only for global neutron balance",
        },
    }
    if output_json is not None:
        destination = Path(output_json).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return payload


def _read_summary(
    source: str | Path | Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    if isinstance(source, Mapping):
        return dict(source), None
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"physics_summary does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("physics_summary must contain a JSON object")
    return payload, str(path)


def _decode_strings(dataset: h5py.Dataset) -> tuple[str, ...]:
    values = np.asarray(dataset[:]).reshape(-1)
    return tuple(
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in values
    )


def _read_openmc_reference(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as h5:
        required_attrs = (
            "reference_keff",
            "reference_keff_std_dev",
            "reference_leakage",
            "reference_leakage_std_dev",
            "reference_finite_balance_std_dev",
            "reference_finite_balance_keff",
            "physical_position_count",
            "global_d3_orbit_count",
            "reference_position_power_count",
            "reference_position_power_orbit_aggregated",
            "reference_position_power_tally",
            "orbit_transport_pooling_verified",
            "post_hoc_cross_section_averaging",
            "domain_mode",
            "output_region_count",
        )
        missing_attrs = [name for name in required_attrs if name not in h5.attrs]
        if missing_attrs:
            raise ValueError(
                f"OpenMC handoff lacks strict full-core attributes: {missing_attrs}"
            )
        boundary = _attr_text(h5.attrs.get("boundary_conditions"))
        if "vacuum" not in boundary.lower() or "reflect" not in boundary.lower():
            raise ValueError(
                "strict IRENA full core requires radial vacuum and axial reflection"
            )
        if int(h5.attrs["physical_position_count"]) != N_POSITIONS:
            raise ValueError("OpenMC handoff physical_position_count must be 91")
        if int(h5.attrs["global_d3_orbit_count"]) != N_ORBITS:
            raise ValueError("OpenMC handoff global_d3_orbit_count must be 21")
        if int(h5.attrs["reference_position_power_count"]) != N_POSITIONS:
            raise ValueError("OpenMC handoff reference position power count must be 91")
        if bool(h5.attrs["reference_position_power_orbit_aggregated"]):
            raise ValueError("OpenMC position power must not be orbit aggregated")
        if _attr_text(h5.attrs["reference_position_power_tally"]) != (
            "irena30_fullcore_91_position_power"
        ):
            raise ValueError("OpenMC handoff does not name the strict 91-position tally")
        if not bool(h5.attrs["orbit_transport_pooling_verified"]):
            raise ValueError("OpenMC 21-orbit transport-time pooling is not verified")
        if bool(h5.attrs["post_hoc_cross_section_averaging"]):
            raise ValueError("post-hoc orbit cross-section averaging is forbidden")
        if _attr_text(h5.attrs["domain_mode"]) != "global_d3_orbit_cell":
            raise ValueError("OpenMC handoff does not use global D3 orbit cell domains")
        if int(h5.attrs["output_region_count"]) != N_ORBITS:
            raise ValueError("OpenMC handoff must export exactly 21 orbit regions")
        if "openmc_position_power" not in h5:
            raise ValueError("OpenMC handoff has no /openmc_position_power evidence")
        group = h5["openmc_position_power"]
        if _attr_text(group.attrs.get("schema")) != (
            "openmc2donjon.irena30-position-power.v1"
        ):
            raise ValueError("OpenMC position-power schema is missing or unsupported")
        if bool(group.attrs.get("orbit_aggregation_used", True)):
            raise ValueError("OpenMC position-power evidence is orbit aggregated")
        required_datasets = (
            "kappa_fission",
            "kappa_fission_std_dev",
            "position_names",
            "position_ring",
            "position_index",
            "position_material",
            "position_orbit_number",
        )
        missing = [name for name in required_datasets if name not in group]
        if missing:
            raise ValueError(f"OpenMC position-power group lacks datasets: {missing}")
        power = np.asarray(group["kappa_fission"][:], dtype=float).reshape(-1)
        power_std = np.asarray(
            group["kappa_fission_std_dev"][:], dtype=float
        ).reshape(-1)
        names = _decode_strings(group["position_names"])
        rings = tuple(int(value) for value in group["position_ring"][:])
        indices = tuple(int(value) for value in group["position_index"][:])
        materials = _decode_strings(group["position_material"])
        orbit_numbers = tuple(
            int(value) for value in group["position_orbit_number"][:]
        )

        keff = _required_positive(h5.attrs["reference_keff"], "reference_keff")
        keff_std = _required_positive(
            h5.attrs["reference_keff_std_dev"], "reference_keff_std_dev"
        )
        finite_std = _required_positive(
            h5.attrs["reference_finite_balance_std_dev"],
            "reference_finite_balance_std_dev",
        )
        finite_keff = _required_positive(
            h5.attrs["reference_finite_balance_keff"],
            "reference_finite_balance_keff",
        )
        leakage = _nonnegative_finite(
            h5.attrs["reference_leakage"], "reference_leakage"
        )
        leakage_std = _nonnegative_finite(
            h5.attrs["reference_leakage_std_dev"], "reference_leakage_std_dev"
        )

    if power.shape != (N_POSITIONS,) or power_std.shape != (N_POSITIONS,):
        raise ValueError("OpenMC position kappa-fission mean/std must have shape (91,)")
    if not np.all(np.isfinite(power)) or np.any(power < 0.0):
        raise ValueError("OpenMC position kappa-fission means must be finite/non-negative")
    if not np.all(np.isfinite(power_std)) or np.any(power_std < 0.0):
        raise ValueError("OpenMC position kappa-fission std_dev must be finite/non-negative")
    if names != EXPECTED_POSITION_NAMES:
        raise ValueError("OpenMC position names/order differ from DRAGON HEXZ order")
    if tuple(zip(rings, indices, strict=True)) != tuple(ORBITS.POSITION_ORDER):
        raise ValueError("OpenMC ring/position order differs from strict IRENA order")
    if materials != EXPECTED_MATERIALS:
        raise ValueError("OpenMC position materials differ from strict IRENA declaration")
    if orbit_numbers != EXPECTED_ORBIT_NUMBERS:
        raise ValueError("OpenMC position-to-orbit map differs from strict D3 declaration")
    if np.any(power[EXPECTED_FUEL_MASK] <= 0.0):
        raise ValueError("all 52 declared INT/EXT positions need positive OpenMC power")
    if np.any(power[~EXPECTED_FUEL_MASK] != 0.0):
        raise ValueError("nonfuel IRENA positions have nonzero OpenMC kappa-fission")
    return {
        "keff": keff,
        "keff_std_dev": keff_std,
        "finite_balance_std_dev": finite_std,
        "finite_balance_keff": finite_keff,
        "leakage_fraction": leakage,
        "leakage_std_dev": leakage_std,
        "position_power": power,
        "position_power_std_dev": power_std,
        "position_count": len(power),
        "orbit_aggregation_used": False,
    }


def _validate_summary_shape(summary: Mapping[str, Any]) -> None:
    if summary.get("schema") != (
        "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1"
    ):
        raise ValueError("physics_summary is not a validate-native-sph v1 summary")
    if int(summary.get("mixture_count", 0)) != N_ORBITS:
        raise ValueError("strict orbit physics_summary must contain 21 mixtures")


def _validate_region_shape(region: Macrolib) -> None:
    if region.nmixtures != N_POSITIONS:
        raise ValueError(
            "region verification must be OUT: INTG IN with 91 physical regions; "
            f"found {region.nmixtures}"
        )
    if region.h_factor is None:
        raise ValueError(
            "91-region verification has no H-FACTOR; physical power cannot be checked"
        )
    if 0 not in region.scatter:
        raise ValueError("91-region verification has no P0 scattering matrix")


def _validate_edi_shape(edi: Macrolib) -> None:
    if edi.nmixtures != N_ORBITS:
        raise ValueError(
            "strict D3 EDI output must aggregate exactly 21 orbit mixtures; "
            f"found {edi.nmixtures}"
        )
    if 0 not in edi.scatter:
        raise ValueError("EDI balance output has no P0 scattering matrix")


def _listing_evidence(text: str, *, factor_count: int) -> dict[str, Any]:
    iterations = list(_SPH_ITERATION_RE.finditer(text))
    ending = list(_SPH_END_RE.finditer(text))
    epsilon_matches = list(_EPSPH_RE.finditer(text))
    final_keff_matches = list(_FINAL_KEFF_RE.finditer(text))
    solver_matches = list(_TRACK_SOLVER_RE.finditer(text))
    nonconvergence = {
        marker: text.lower().count(marker.lower())
        for marker in _NONCONVERGENCE_MARKERS
        if marker.lower() in text.lower()
    }
    last = iterations[-1] if iterations else None
    epsilon = float(epsilon_matches[-1].group(1)) if epsilon_matches else None
    final_error = float(last.group(2)) if last else None
    final_rms = float(last.group(3)) if last else None
    # SPHEQU.f stops on ERR2, the RMS over NMERGE*NGCOND factors.  ERROR is
    # the maximum update and is not compared with EPSPH by DRAGON.  Preserve
    # that solver contract, while independently checking the exact norm bound
    # max <= sqrt(N)*RMS (0.2% only covers E10.3 listing round-off).
    maximum_rms_bound = (
        None
        if final_rms is None or factor_count <= 0
        else math.sqrt(factor_count) * final_rms
    )
    solver_family = (
        None
        if not solver_matches
        else ("sn" if solver_matches[-1].group(1).upper() == "SNT" else "spn")
    )
    return {
        "normal_end": "normal end of execution for donjon" in text.lower(),
        "sph_convergence_ending_present": bool(ending),
        "sph_iterations": int(ending[-1].group(1)) if ending else None,
        "epsilon": epsilon,
        "final_max_factor_update": final_error,
        "final_rms_factor_update": final_rms,
        "fixed_point_within_epsilon": bool(
            epsilon is not None
            and epsilon > 0.0
            and final_rms is not None
            and final_rms <= epsilon
        ),
        "maximum_update_rms_norm_bound": maximum_rms_bound,
        "maximum_update_within_rms_norm_bound": bool(
            final_error is not None
            and maximum_rms_bound is not None
            and final_error <= maximum_rms_bound * 1.002
        ),
        "negative_factor_correction_count": len(_NEGATIVE_FACTOR_RE.findall(text)),
        "oscillation_stop_count": text.lower().count(_OSCILLATION_MARKER.lower()),
        "flux_nonconvergence_count": sum(nonconvergence.values()),
        "flux_nonconvergence_markers": nonconvergence,
        "solver_family": solver_family,
        "one_speed_method_provable": bool(
            solver_family == "spn"
            or (
                solver_family == "sn"
                and not _GMRES_RE.search(text)
                and (_DSA_RE.search(text) or _LIVOLANT_RE.search(text))
            )
        ),
        "final_keff": (
            float(final_keff_matches[-1].group(1)) if final_keff_matches else None
        ),
    }


def _native_evidence_audit(
    summary: Mapping[str, Any],
    summary_path: str | None,
) -> dict[str, Any]:
    """Recompute every native-SPH evidence digest before full-core acceptance.

    A mapping is useful to unit-test field-level physics logic, but it is not
    immutable evidence and therefore cannot close production acceptance.  A
    file-backed summary must bind all native-SPH artifacts and the Converter
    receipt; this function reads and hashes the live files again.
    """

    issues: list[str] = []
    handoff = summary.get("handoff")
    file_backed = summary_path is not None
    if not file_backed:
        issues.append(
            "physics_summary was supplied as an in-memory mapping; production "
            "acceptance requires a file-backed summary"
        )
    if not isinstance(handoff, Mapping):
        return {
            "checks": {
                "native_summary_is_file_backed": file_backed,
                "native_evidence_sha256_manifest_complete": False,
                "native_evidence_files_present": False,
                "native_evidence_sha256_matches_live_files": False,
                "native_converter_receipt_matches_reference": False,
            },
            "issues": [*issues, "native-SPH summary has no handoff object"],
            "files": {},
        }

    hashes = handoff.get("evidence_sha256")
    manifest_present = isinstance(hashes, Mapping)
    if not manifest_present:
        issues.append("native-SPH handoff has no evidence SHA-256 manifest")
        hashes = {}
    assert isinstance(hashes, Mapping)

    keys = list(_NATIVE_EVIDENCE_PATHS)
    if handoff.get("energy_coverage_path") is not None:
        keys.append("energy_coverage_path")
    files: dict[str, dict[str, Any]] = {}
    manifest_complete = manifest_present
    files_present = True
    hashes_match = True
    resolved: dict[str, Path] = {}
    for key in keys:
        raw_path = handoff.get(key)
        expected_hash = hashes.get(key)
        if not isinstance(raw_path, str) or not raw_path.strip():
            issues.append(f"native-SPH evidence path is not declared: {key}")
            manifest_complete = False
            files_present = False
            hashes_match = False
            files[key] = {
                "path": None,
                "expected_sha256": expected_hash,
                "actual_sha256": None,
                "matches": False,
            }
            continue
        path = Path(raw_path.strip().split("::", 1)[0]).expanduser().resolve()
        resolved[key] = path
        present = path.is_file()
        if not present:
            issues.append(f"native-SPH evidence file does not exist: {key}: {path}")
            files_present = False
        declared_hash = (
            expected_hash
            if isinstance(expected_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            else None
        )
        if declared_hash is None:
            issues.append(f"native-SPH evidence hash is not declared: {key}")
            manifest_complete = False
        actual_hash = _sha256_file(path) if present else None
        matches = bool(
            declared_hash is not None
            and actual_hash is not None
            and declared_hash == actual_hash
        )
        if not matches:
            issues.append(f"native-SPH evidence hash mismatch: {key}")
            hashes_match = False
        files[key] = {
            "path": str(path),
            "expected_sha256": declared_hash,
            "actual_sha256": actual_hash,
            "matches": matches,
        }

    receipt_issues: list[str] = []
    receipt = resolved.get("converter_receipt_path")
    reference_h5 = resolved.get("augmented_hdf5_path")
    reference_macrolib = resolved.get("reference_macrolib_path")
    if (
        receipt is None
        or reference_h5 is None
        or reference_macrolib is None
        or not receipt.is_file()
        or not reference_h5.is_file()
        or not reference_macrolib.is_file()
    ):
        receipt_issues.append(
            "Converter receipt and its bound HDF5/MACROLIB are not all present"
        )
    else:
        receipt_issues.extend(
            converter_receipt_issues(
                receipt,
                reference_h5=reference_h5,
                reference_macrolib=reference_macrolib,
            )
        )
    issues.extend(receipt_issues)
    return {
        "checks": {
            "native_summary_is_file_backed": file_backed,
            "native_evidence_sha256_manifest_complete": manifest_complete,
            "native_evidence_files_present": files_present,
            "native_evidence_sha256_matches_live_files": hashes_match,
            "native_converter_receipt_matches_reference": not receipt_issues,
        },
        "issues": issues,
        "files": files,
    }


def _native_summary_checks(
    summary: Mapping[str, Any],
    listing: Mapping[str, Any],
    listing_path: Path,
) -> dict[str, bool]:
    native = summary.get("native_sph")
    acceptance = summary.get("acceptance_checks")
    quality = summary.get("quality")
    handoff = summary.get("handoff")
    if not all(isinstance(value, Mapping) for value in (native, acceptance, quality)):
        raise ValueError("physics_summary lacks native/acceptance/quality objects")
    assert isinstance(native, Mapping)
    assert isinstance(acceptance, Mapping)
    assert isinstance(quality, Mapping)
    summary_listing = None
    if isinstance(handoff, Mapping):
        value = handoff.get("result_listing_path")
        if value:
            summary_listing = Path(str(value)).expanduser().resolve()
    return {
        "native_sph_fixed_point_converged": bool(native.get("converged"))
        and bool(acceptance.get("native_sph_converged")),
        "one_speed_convergence_provable": bool(
            native.get("one_speed_convergence_provable")
        )
        and bool(acceptance.get("one_speed_convergence_provable")),
        "final_flux_solve_converged": bool(native.get("final_flux_solve_converged"))
        and int(native.get("flux_nonconvergence_count", -1)) == 0
        and bool(acceptance.get("final_flux_solve_converged"))
        and int(listing["flux_nonconvergence_count"]) == 0,
        "donjon_normal_end": bool(native.get("normal_end"))
        and bool(acceptance.get("donjon_normal_end"))
        and bool(listing["normal_end"]),
        "native_sph_factors_unmodified": bool(native.get("factors_unmodified"))
        and int(native.get("negative_factor_correction_count", -1)) == 0
        and bool(acceptance.get("native_sph_factors_unmodified"))
        and int(listing["negative_factor_correction_count"]) == 0,
        "native_sph_not_stopped_by_oscillation": int(
            native.get("oscillation_stop_count", -1)
        )
        == 0
        and bool(acceptance.get("native_sph_not_stopped_by_oscillation"))
        and int(listing["oscillation_stop_count"]) == 0,
        "listing_fixed_point_within_declared_epsilon": bool(
            listing["sph_convergence_ending_present"]
            and listing["fixed_point_within_epsilon"]
        ),
        "listing_maximum_update_within_rms_norm_bound": bool(
            listing["maximum_update_within_rms_norm_bound"]
        ),
        "listing_uses_provable_one_speed_method": bool(
            listing["one_speed_method_provable"]
        ),
        "summary_listing_solver_family_consistent": bool(
            native.get("solver_family") in {"sn", "spn"}
            and native.get("solver_family") == listing.get("solver_family")
        ),
        "summary_listing_sph_convergence_consistent": _summary_listing_convergence_matches(
            native, listing
        ),
        "native_summary_uses_finite_domain_balance": bool(
            _nested(summary, "eigenvalue_validation", "reference_physical_balance_kind")
            == "finite-domain-keff"
            and _nested(
                summary,
                "eigenvalue_validation",
                "reference_finite_balance_available",
            )
            is True
        ),
        "native_summary_all_physics_checks_pass": _summary_acceptance_checks_pass(
            acceptance
        ),
        "native_summary_production_ready": bool(quality.get("production_ready"))
        and bool(quality.get("structural_passed")),
        "summary_and_input_use_same_result_listing": summary_listing is None
        or summary_listing == listing_path,
    }


def _no_empirical_factor(summary: Mapping[str, Any]) -> bool:
    acceptance = summary.get("acceptance_checks")
    criteria_value = (
        acceptance.get("empirical_eigenvalue_multiplier_used")
        if isinstance(acceptance, Mapping)
        else None
    )
    adf_value = (
        acceptance.get("adf_used") if isinstance(acceptance, Mapping) else None
    )
    sph = summary.get("sph")
    clipped = sph.get("clipped_count") if isinstance(sph, Mapping) else None
    return criteria_value is False and adf_value is False and clipped == 0


def _real_native_sph(summary: Mapping[str, Any]) -> bool:
    sph = summary.get("sph")
    decisions = summary.get("decisions")
    handoff = summary.get("handoff")
    return bool(
        isinstance(sph, Mapping)
        and sph.get("real") is True
        and sph.get("applied_to_xs") is True
        and isinstance(decisions, Mapping)
        and decisions.get("openmc_sph") == "not_used"
        and isinstance(handoff, Mapping)
        and handoff.get("augmented_hdf5_has_sph") is False
    )


def _summary_acceptance_checks_pass(acceptance: Mapping[str, Any]) -> bool:
    false_by_contract = {
        "empirical_eigenvalue_multiplier_used",
        "adf_used",
    }
    if not acceptance:
        return False
    for key, value in acceptance.items():
        if key in false_by_contract:
            if value is not False:
                return False
        elif value is not True:
            return False
    return false_by_contract.issubset(acceptance)


def _summary_listing_convergence_matches(
    native: Mapping[str, Any], listing: Mapping[str, Any]
) -> bool:
    pairs = (
        (native.get("epsilon"), listing.get("epsilon")),
        (native.get("final_max_factor_update"), listing.get("final_max_factor_update")),
        (native.get("final_rms_factor_update"), listing.get("final_rms_factor_update")),
    )
    if native.get("iterations") != listing.get("sph_iterations"):
        return False
    for first, second in pairs:
        if first is None or second is None:
            return False
        if not math.isclose(float(first), float(second), rel_tol=1.0e-9, abs_tol=1.0e-14):
            return False
    return True


def _summary_reference_matches_h5(
    summary: Mapping[str, Any], reference: Mapping[str, Any]
) -> bool:
    validation = summary.get("eigenvalue_validation")
    if not isinstance(validation, Mapping):
        return False
    pairs = (
        (validation.get("openmc_keff"), reference["keff"]),
        (validation.get("openmc_keff_std_dev"), reference["keff_std_dev"]),
        (validation.get("reference_finite_balance_keff"), reference["finite_balance_keff"]),
        (
            validation.get("reference_finite_balance_std_dev"),
            reference["finite_balance_std_dev"],
        ),
        (validation.get("reference_leakage"), reference["leakage_fraction"]),
        (validation.get("reference_leakage_std_dev"), reference["leakage_std_dev"]),
    )
    for first, second in pairs:
        if first is None:
            return False
        if not math.isclose(float(first), float(second), rel_tol=1.0e-9, abs_tol=1.0e-14):
            return False
    return True


def _summary_reference_path_matches(
    summary: Mapping[str, Any], reference_h5: Path
) -> bool:
    handoff = summary.get("handoff")
    if not isinstance(handoff, Mapping):
        return False
    declared = handoff.get("augmented_hdf5_path")
    if not declared:
        return False
    return Path(str(declared)).expanduser().resolve() == reference_h5


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _no_nonphysical_sph_bin_policy(summary: Mapping[str, Any]) -> bool:
    return bool(
        summary.get("zero_flux_policy") == "reject"
        and int(summary.get("identity_bin_count", -1)) == 0
        and int(summary.get("floored_bin_count", -1)) == 0
        and int(summary.get("frozen_group_bin_count", -1)) == 0
        and summary.get("freeze_groups") == []
    )


def _neutron_balance(macrolib: Macrolib, keff: float) -> dict[str, float]:
    flux = np.asarray(macrolib.flux_intg, dtype=float)
    production = float(np.sum(np.asarray(macrolib.nusigf) * flux))
    scattering = np.asarray(macrolib.sigs[0], dtype=float)
    collision_loss = float(
        np.sum((np.asarray(macrolib.ntot0) - scattering) * flux)
    )
    source = production / keff
    leakage_rate = source - collision_loss
    if not all(math.isfinite(value) for value in (production, collision_loss, source)):
        raise ValueError("DONJON neutron balance contains non-finite values")
    if production <= 0.0 or collision_loss <= 0.0 or source <= 0.0:
        raise ValueError("DONJON neutron balance production/loss/source must be positive")
    roundoff = 1.0e-10 * max(source, collision_loss)
    if leakage_rate < -roundoff:
        raise ValueError("DONJON neutron balance implies negative physical leakage")
    leakage_rate = max(0.0, leakage_rate)
    return {
        "fission_production": production,
        "net_collision_loss": collision_loss,
        "fission_source": source,
        "leakage_rate": leakage_rate,
        "leakage_fraction": leakage_rate / source,
    }


def _position_power(region: Macrolib) -> np.ndarray:
    assert region.h_factor is not None
    h_factor = np.asarray(region.h_factor, dtype=float)
    flux = np.asarray(region.flux_intg, dtype=float)
    if h_factor.shape != flux.shape or h_factor.shape[0] != N_POSITIONS:
        raise ValueError("91-region H-FACTOR/FLUX-INTG shapes are inconsistent")
    if not np.all(np.isfinite(h_factor)) or np.any(h_factor < 0.0):
        raise ValueError("DONJON H-FACTOR values must be finite/non-negative")
    if not np.all(np.isfinite(flux)) or np.any(flux < 0.0):
        raise ValueError("DONJON position fluxes must be finite/non-negative")
    result = np.sum(h_factor * flux, axis=1)
    if float(np.sum(result)) <= 0.0:
        raise ValueError("DONJON 91-position total power is not positive")
    return result


def _power_metrics(
    reference: np.ndarray,
    reference_std: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, Any]:
    if candidate.shape != (N_POSITIONS,):
        raise ValueError("DONJON physical power must contain exactly 91 positions")
    ref_total = float(np.sum(reference))
    candidate_total = float(np.sum(candidate))
    ref_norm = reference / ref_total
    candidate_norm = candidate / candidate_total
    active = EXPECTED_FUEL_MASK
    relative = (candidate_norm[active] - ref_norm[active]) / ref_norm[active]
    active_indices = np.flatnonzero(active)
    worst_local = int(np.argmax(np.abs(relative)))
    worst_index = int(active_indices[worst_local])
    openmc_relative_std = reference_std[active] / reference[active]
    nonfuel_fraction = float(np.sum(candidate[~active]) / candidate_total)
    return {
        "physical_position_count": N_POSITIONS,
        "active_fuel_position_count": int(np.count_nonzero(active)),
        "orbit_aggregation_used": False,
        "normalization": "each 91-entry vector divided by its own total power",
        "rms_relative_error": float(np.sqrt(np.mean(np.square(relative)))),
        "maximum_absolute_relative_error": float(np.max(np.abs(relative))),
        "worst_position_index_zero_based": worst_index,
        "worst_position": EXPECTED_POSITION_NAMES[worst_index],
        "worst_signed_relative_error": float(relative[worst_local]),
        "openmc_max_active_relative_std_dev": float(
            np.max(openmc_relative_std)
        ),
        "donjon_nonfuel_power_fraction": nonfuel_fraction,
        "openmc_normalized_91": ref_norm.tolist(),
        "donjon_normalized_91": candidate_norm.tolist(),
        "active_position_relative_error": {
            EXPECTED_POSITION_NAMES[index]: float(value)
            for index, value in zip(active_indices, relative, strict=True)
        },
    }


def _nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _nested_positive(mapping: Mapping[str, Any], *keys: str) -> float:
    return _required_positive(_nested(mapping, *keys), ".".join(keys))


def _attr_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def _required_positive(value: Any, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} is required")
    result = float(np.asarray(value, dtype=float).reshape(()))
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _nonnegative_finite(value: Any, label: str) -> float:
    result = float(np.asarray(value, dtype=float).reshape(()))
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be non-negative and finite")
    return result


def _positive_finite(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _close_ascii(first: float, second: float) -> bool:
    return bool(math.isclose(first, second, rel_tol=2.0e-6, abs_tol=2.0e-7))


def _relative_delta(candidate: float, reference: float) -> float:
    if not math.isfinite(reference) or reference == 0.0:
        raise ValueError("reaction-rate closure reference must be finite/nonzero")
    return candidate / reference - 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-summary", type=Path, required=True)
    parser.add_argument("--reference-h5", type=Path, required=True)
    parser.add_argument("--region-verify", type=Path, required=True)
    parser.add_argument("--edi", type=Path, required=True)
    parser.add_argument("--result-listing", type=Path, required=True)
    parser.add_argument("--max-keff-sigma", type=float, default=2.0)
    parser.add_argument("--max-leakage-delta", type=float, default=0.005)
    parser.add_argument("--max-power-rms", type=float, default=0.01)
    parser.add_argument("--max-power-relative", type=float, default=0.02)
    parser.add_argument("--max-openmc-power-relative-std", type=float, default=0.10)
    parser.add_argument("--reaction-rate-closure-rtol", type=float, default=2.0e-5)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = validate_orbit_fullcore(
            args.physics_summary,
            args.reference_h5,
            args.region_verify,
            args.edi,
            args.result_listing,
            output_json=args.summary,
            max_keff_sigma=args.max_keff_sigma,
            max_leakage_delta=args.max_leakage_delta,
            max_power_rms_relative=args.max_power_rms,
            max_power_relative=args.max_power_relative,
            max_openmc_power_relative_std=args.max_openmc_power_relative_std,
            reaction_rate_closure_rtol=args.reaction_rate_closure_rtol,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    print(f"decision: {payload['decision']}")
    print(
        "keff: "
        f"{payload['eigenvalue']['donjon_keff']:.8f}, "
        f"z={payload['eigenvalue']['z']:+.3f}"
    )
    print(
        "leakage: "
        f"{payload['leakage']['donjon_fraction']:.6f}, "
        f"delta={payload['leakage']['fraction_delta']:+.6f}"
    )
    print(
        "91-position power: "
        f"rms={payload['power_shape']['rms_relative_error']:.3%}, "
        f"max={payload['power_shape']['maximum_absolute_relative_error']:.3%}"
    )
    return 0 if payload["decision"].endswith("_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
