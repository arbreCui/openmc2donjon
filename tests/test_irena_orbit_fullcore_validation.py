from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

import h5py
import numpy as np
import pytest

from openmc2donjon.macrolib import write_macrolib
from openmc2donjon.multicompo import MixtureXS
from openmc2donjon.openmc_provenance import (
    collect_openmc_provenance,
    write_openmc_provenance,
)
from openmc2donjon.production_policy import (
    canonical_production_thresholds,
    production_preflight_policy_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_validator():
    path = (
        ROOT
        / "examples"
        / "irena30_native_fullcore"
        / "validate_orbit_fullcore.py"
    )
    name = "_irena_orbit_fullcore_validation_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()
ORBITS = VALIDATOR.ORBITS


def _mixture(
    name: str,
    *,
    material: str,
    flux: float,
    volume: float,
    net_loss_xs: float,
) -> MixtureXS:
    fuel = material in VALIDATOR.FUEL_MATERIALS
    scatter = 1.0 - net_loss_xs
    return MixtureXS(
        name=name,
        total=np.asarray([1.0]),
        absorption=np.asarray([net_loss_xs]),
        fission=np.asarray([0.36 if fuel else 0.0]),
        nu_fission=np.asarray([0.9 if fuel else 0.0]),
        chi=np.asarray([1.0 if fuel else 0.0]),
        scatter_matrix=np.asarray([[[scatter]]]),
        fissionable=fuel,
        volume=volume,
        flux_weight=np.asarray([flux]),
        h_factor=np.asarray([2.0 if fuel else 0.0]),
        transport_total=np.asarray([1.0]),
    )


def _write_macrolibs(
    region: Path,
    edi: Path,
    *,
    flux_multipliers: np.ndarray | None = None,
    keff: float = 1.0,
) -> None:
    multipliers = (
        np.ones(VALIDATOR.N_POSITIONS)
        if flux_multipliers is None
        else np.asarray(flux_multipliers, dtype=float)
    )
    assert multipliers.shape == (VALIDATOR.N_POSITIONS,)
    # At k=1 this gives source=46.8, collision loss=42.12, leakage=10%.
    net_loss_xs = (52.0 * 0.9 * 0.9) / 91.0
    positions = []
    for index, ((ring, position), material) in enumerate(
        zip(ORBITS.POSITION_ORDER, VALIDATOR.EXPECTED_MATERIALS, strict=True)
    ):
        positions.append(
            _mixture(
                f"R{ring}P{position:02d}_{material}",
                material=material,
                flux=float(multipliers[index]),
                volume=1.0,
                net_loss_xs=net_loss_xs,
            )
        )
    write_macrolib(
        positions,
        np.asarray([1.0e-5, 2.0e7]),
        region,
        reference_keff=keff,
    )

    position_index = {value: index for index, value in enumerate(ORBITS.POSITION_ORDER)}
    aggregate = []
    for orbit in ORBITS.ORBITS:
        indices = [position_index[member] for member in orbit.members]
        aggregate.append(
            _mixture(
                f"{orbit.id}_{orbit.material}",
                material=orbit.material,
                flux=float(np.mean(multipliers[indices])),
                volume=float(orbit.multiplicity),
                net_loss_xs=net_loss_xs,
            )
        )
    write_macrolib(
        aggregate,
        np.asarray([1.0e-5, 2.0e7]),
        edi,
        reference_keff=keff,
    )


def _write_h5(path: Path, *, leakage: float = 0.1) -> None:
    fuel = VALIDATOR.EXPECTED_FUEL_MASK
    power = np.where(fuel, 2.0, 0.0)
    power_std = np.where(fuel, 0.02, 0.0)
    with h5py.File(path, "w") as h5:
        h5.attrs["reference_keff"] = 1.0
        h5.attrs["reference_keff_std_dev"] = 0.005
        h5.attrs["reference_finite_balance_std_dev"] = 0.01
        h5.attrs["reference_finite_balance_keff"] = 1.0
        h5.attrs["reference_leakage"] = leakage
        h5.attrs["reference_leakage_std_dev"] = 0.002
        h5.attrs["physical_position_count"] = 91
        h5.attrs["global_d3_orbit_count"] = 21
        h5.attrs["reference_position_power_count"] = 91
        h5.attrs["reference_position_power_orbit_aggregated"] = False
        h5.attrs["reference_position_power_tally"] = (
            "irena30_fullcore_91_position_power"
        )
        h5.attrs["orbit_transport_pooling_verified"] = True
        h5.attrs["post_hoc_cross_section_averaging"] = False
        h5.attrs["domain_mode"] = "global_d3_orbit_cell"
        h5.attrs["output_region_count"] = 21
        h5.attrs["boundary_conditions"] = "radial vacuum; axial reflective"
        group = h5.create_group("openmc_position_power")
        group.attrs["schema"] = "openmc2donjon.irena30-position-power.v1"
        group.attrs["orbit_aggregation_used"] = False
        group.create_dataset("kappa_fission", data=power)
        group.create_dataset("kappa_fission_std_dev", data=power_std)
        group.create_dataset(
            "position_names", data=np.asarray(VALIDATOR.EXPECTED_POSITION_NAMES, dtype="S")
        )
        group.create_dataset(
            "position_ring",
            data=np.asarray([ring for ring, _position in ORBITS.POSITION_ORDER]),
        )
        group.create_dataset(
            "position_index",
            data=np.asarray([position for _ring, position in ORBITS.POSITION_ORDER]),
        )
        group.create_dataset(
            "position_material",
            data=np.asarray(VALIDATOR.EXPECTED_MATERIALS, dtype="S"),
        )
        group.create_dataset(
            "position_orbit_number", data=np.asarray(ORBITS.MIXTURE_MAP)
        )


def _listing(keff: float = 1.0, *, extra: str = "") -> str:
    return (
        "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 "
        "LIVO 3 3 MAXI 1000 EPSI 1.0E-08 ;\n"
        "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
        "SPHEQU: ITER= 9 ERROR= 8.0E-07 ERR 2= 5.0E-07\n"
        "SPHEQU: ENDING OF SPH CONVERGENCE AFTER 9 ITERATIONS.\n"
        f"{extra}"
        "OPENMC2DONJON IRENA30 FULLCORE NATIVE SPH FINAL K-EFFECTIVE "
        f"{keff:.8f}\n"
        "normal end of execution for donjon 5 Version 5.1.0\n"
    )


def _summary(
    result: Path,
    reference_h5: Path,
    reference_macrolib: Path,
    sph_macrolib: Path,
    verification_macrolib: Path,
    converter_receipt: Path,
    energy_coverage: Path,
    *,
    keff: float = 1.0,
) -> dict[str, Any]:
    return {
        "schema": "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1",
        "mixture_count": 21,
        "quality": {
            "decision": "native_sph_physics_passed",
            "production_ready": True,
            "structural_passed": True,
        },
        "geometry": {
            "boundary_conditions": "radial vacuum; axial reflective",
        },
        "acceptance_checks": {
            "native_sph_converged": True,
            "native_sph_factors_unmodified": True,
            "native_sph_not_stopped_by_oscillation": True,
            "one_speed_convergence_provable": True,
            "final_flux_solve_converged": True,
            "donjon_normal_end": True,
            "converter_receipt_linked": True,
            "empirical_eigenvalue_multiplier_used": False,
            "adf_used": False,
        },
        "native_sph": {
            "solver_family": "sn",
            "converged": True,
            "one_speed_convergence_provable": True,
            "final_flux_solve_converged": True,
            "flux_nonconvergence_count": 0,
            "normal_end": True,
            "factors_unmodified": True,
            "negative_factor_correction_count": 0,
            "oscillation_stop_count": 0,
            "iterations": 9,
            "epsilon": 1.0e-6,
            "final_max_factor_update": 8.0e-7,
            "final_rms_factor_update": 5.0e-7,
        },
        "sph": {
            "real": True,
            "applied_to_xs": True,
            "clipped_count": 0,
        },
        "decisions": {"openmc_sph": "not_used"},
        "zero_flux_policy": "reject",
        "identity_bin_count": 0,
        "floored_bin_count": 0,
        "frozen_group_bin_count": 0,
        "freeze_groups": [],
        "eigenvalue_validation": {
            "openmc_keff": 1.0,
            "openmc_keff_std_dev": 0.005,
            "reference_physical_balance_kind": "finite-domain-keff",
            "reference_finite_balance_available": True,
            "reference_finite_balance_keff": 1.0,
            "reference_finite_balance_std_dev": 0.01,
            "reference_leakage": 0.1,
            "reference_leakage_std_dev": 0.002,
            "donjon_keff": keff,
            "donjon_combined_std_dev": 0.015,
        },
        "handoff": {
            "result_listing_path": str(result.resolve()),
            "augmented_hdf5_path": str(reference_h5.resolve()),
            "augmented_hdf5_has_sph": False,
            "reference_macrolib_path": str(reference_macrolib.resolve()),
            "macrolib_ascii_path": str(sph_macrolib.resolve()),
            "verification_macrolib_path": str(
                verification_macrolib.resolve()
            ),
            "converter_receipt_path": str(converter_receipt.resolve()),
            "energy_coverage_path": str(energy_coverage.resolve()),
            "evidence_sha256": {
                "result_listing_path": _sha256(result),
                "augmented_hdf5_path": _sha256(reference_h5),
                "reference_macrolib_path": _sha256(reference_macrolib),
                "macrolib_ascii_path": _sha256(sph_macrolib),
                "verification_macrolib_path": _sha256(
                    verification_macrolib
                ),
                "converter_receipt_path": _sha256(converter_receipt),
                "energy_coverage_path": _sha256(energy_coverage),
            },
        },
    }


def _case(
    root: Path,
    *,
    flux_multipliers: np.ndarray | None = None,
    keff: float = 1.0,
    leakage: float = 0.1,
    listing_extra: str = "",
) -> dict[str, Any]:
    h5 = root / "reference.h5"
    region = root / "region.macrolib.txt"
    edi = root / "edi.macrolib.txt"
    result = root / "donjon.result"
    physics = root / "physics_summary.json"
    output = root / "fullcore_validation.json"
    reference_macrolib = root / "reference.macrolib.txt"
    sph_macrolib = root / "native_sph.macrolib.txt"
    verification_macrolib = root / "verification.macrolib.txt"
    converter_receipt = root / "converter_summary.json"
    energy_coverage = root / "energy_coverage.json"
    _write_h5(h5, leakage=leakage)
    _write_macrolibs(
        region,
        edi,
        flux_multipliers=flux_multipliers,
        keff=keff,
    )
    result.write_text(_listing(keff, extra=listing_extra), encoding="utf-8")
    reference_macrolib.write_text("reference L_MACROLIB evidence\n", encoding="utf-8")
    sph_macrolib.write_text("native SPH L_MACROLIB evidence\n", encoding="utf-8")
    verification_macrolib.write_text(
        "verification L_MACROLIB evidence\n", encoding="utf-8"
    )
    energy_coverage.write_text(
        json.dumps({"decision": "passed", "outside_fraction": 0.0}),
        encoding="utf-8",
    )
    openmc_provenance = _bind_complete_openmc_provenance(h5)
    thresholds = canonical_production_thresholds()
    converter_receipt.write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.convert.v1",
                "ok": True,
                "converted": True,
                "dry_run": False,
                "format": "macrolib",
                "production_requested": True,
                "preflight_policy": production_preflight_policy_payload(
                    production_requested=True,
                    preflight_executed=True,
                    thresholds=thresholds,
                ),
                "preflight_ok": True,
                "preflight": {
                    "schema": "openmc2donjon.mgxs-input-contract.v1",
                    "decision": "mgxs_input_contract_passed",
                    "inputs": [
                        {
                            "ok": True,
                            "scatter_row_balance": {
                                "fail_threshold": thresholds[
                                    "scatter_row_balance_fail"
                                ]
                            },
                            "physics_checks": {
                                "chi_sum_tolerance": thresholds[
                                    "chi_sum_tolerance"
                                ],
                                "transport_p1_fail_threshold": thresholds[
                                    "transport_p1_fail"
                                ],
                            },
                            "uncertainty": {
                                "checked": True,
                                "require_coverage": True,
                                "warn_threshold": thresholds["uncertainty_warn"],
                                "fail_threshold": thresholds["uncertainty_fail"],
                                "production_fail_threshold": thresholds[
                                    "uncertainty_production_fail"
                                ],
                                "mean_abs_floor": thresholds[
                                    "uncertainty_mean_abs_floor"
                                ],
                            },
                        }
                    ],
                },
                "physical_sph_required": False,
                "input_path": str(h5.resolve()),
                "input_sha256": _sha256(h5),
                "openmc_provenance": openmc_provenance,
                "output_path": str(reference_macrolib.resolve()),
                "output_sha256": _sha256(reference_macrolib),
            }
        ),
        encoding="utf-8",
    )
    summary = _summary(
        result,
        h5,
        reference_macrolib,
        sph_macrolib,
        verification_macrolib,
        converter_receipt,
        energy_coverage,
        keff=keff,
    )
    physics.write_text(json.dumps(summary), encoding="utf-8")
    return {
        "h5": h5,
        "region": region,
        "edi": edi,
        "result": result,
        "physics": physics,
        "summary": summary,
        "output": output,
        "reference_macrolib": reference_macrolib,
        "sph_macrolib": sph_macrolib,
        "verification_macrolib": verification_macrolib,
        "converter_receipt": converter_receipt,
        "energy_coverage": energy_coverage,
    }


def _validate(case: dict[str, Any]) -> dict[str, Any]:
    return VALIDATOR.validate_orbit_fullcore(
        case["physics"],
        case["h5"],
        case["region"],
        case["edi"],
        case["result"],
        output_json=case["output"],
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind_complete_openmc_provenance(input_path: Path) -> dict[str, object]:
    source_dir = input_path.with_suffix(".openmc-sources")
    source_dir.mkdir(exist_ok=True)
    recipe = source_dir / "export_recipe.py"
    geometry = source_dir / "geometry.xml"
    materials = source_dir / "materials.xml"
    settings = source_dir / "settings.xml"
    cross_sections = source_dir / "cross_sections.xml"
    library = source_dir / "U235.h5"
    statepoint = source_dir / "statepoint.20.h5"
    recipe.write_text("# test recipe\n", encoding="utf-8")
    geometry.write_text("<geometry/>\n", encoding="utf-8")
    settings.write_text(
        "<settings><run_mode>eigenvalue</run_mode><particles>1000</particles>"
        "<batches>20</batches><inactive>5</inactive>"
        "<generations_per_batch>1</generations_per_batch><seed>19</seed>"
        "</settings>\n",
        encoding="utf-8",
    )
    library.write_bytes(b"test evaluated data\n")
    cross_sections.write_text(
        '<cross_sections><library materials="U235" path="U235.h5" '
        'type="neutron"/></cross_sections>\n',
        encoding="utf-8",
    )
    materials.write_text(
        "<materials><cross_sections>cross_sections.xml</cross_sections>"
        '<material id="1"><nuclide name="U235"/></material></materials>\n',
        encoding="utf-8",
    )
    with h5py.File(statepoint, "w") as h5:
        h5.attrs["filetype"] = "statepoint"
        h5.attrs["openmc_version"] = np.asarray([0, 15, 4])
        h5.attrs["version"] = np.asarray([18, 1])
        h5.create_dataset("run_mode", data=np.bytes_("eigenvalue"))
        h5.create_dataset("n_particles", data=1000)
        h5.create_dataset("n_batches", data=20)
        h5.create_dataset("n_inactive", data=5)
        h5.create_dataset("generations_per_batch", data=1)
        h5.create_dataset("seed", data=19)
        h5.create_dataset("stride", data=152917)
    record = collect_openmc_provenance(
        recipe_path=recipe,
        statepoint_path=statepoint,
        statepoint_loaded=True,
        declared_files={
            "geometry": geometry,
            "materials": materials,
            "settings": settings,
        },
        declared_metadata={"input_closure_complete": True},
    )
    assert record["capabilities"]["transport_reproducible"] is True
    return write_openmc_provenance(input_path, record)


def test_accepts_strict_21_orbit_sph_with_real_91_position_power() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        payload = _validate(case)

        assert payload["decision"] == "irena30_orbit_fullcore_physics_passed"
        assert all(payload["acceptance_checks"].values())
        assert payload["power_shape"]["physical_position_count"] == 91
        assert payload["power_shape"]["active_fuel_position_count"] == 52
        assert payload["power_shape"]["orbit_aggregation_used"] is False
        assert payload["power_shape"]["rms_relative_error"] < 1.0e-12
        assert payload["power_shape"]["maximum_absolute_relative_error"] < 1.0e-12
        assert len(payload["power_shape"]["openmc_normalized_91"]) == 91
        assert len(payload["power_shape"]["donjon_normalized_91"]) == 91
        assert payload["leakage"]["donjon_fraction"] == pytest.approx(0.1)
        assert payload["evidence"]["edi_role"].startswith("21-orbit")
        assert set(payload["evidence"]["input_sha256"]) == {
            "physics_summary",
            "reference_h5",
            "region_verify",
            "edi_output",
            "result_listing",
        }
        assert all(
            len(value) == 64
            for value in payload["evidence"]["input_sha256"].values()
        )
        assert case["output"].is_file()


def test_rejects_unconverged_final_solve_even_with_normal_end() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        payload = json.loads(case["physics"].read_text(encoding="utf-8"))
        payload["native_sph"]["final_flux_solve_converged"] = False
        payload["native_sph"]["flux_nonconvergence_count"] = 1
        payload["acceptance_checks"]["final_flux_solve_converged"] = False
        case["physics"].write_text(json.dumps(payload), encoding="utf-8")

        result = _validate(case)
        assert result["decision"] == "irena30_orbit_fullcore_review_required"
        assert result["acceptance_checks"]["final_flux_solve_converged"] is False


def test_listing_nonconvergence_and_negative_factor_are_independent_hard_gates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(
            Path(tmp),
            listing_extra=(
                "SNF: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.\n"
                "Warning: negative SPH factor in group 3 and region 2 set to 1.0\n"
            ),
        )
        payload = _validate(case)
        assert payload["decision"] == "irena30_orbit_fullcore_review_required"
        assert payload["acceptance_checks"]["final_flux_solve_converged"] is False
        assert payload["acceptance_checks"]["native_sph_factors_unmodified"] is False


def test_power_gate_cannot_be_satisfied_by_unchanged_21_orbit_average() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        modifiers = np.ones(91)
        # R1P01 and R1P03 are both members of global orbit O03.  Their equal
        # and opposite changes leave the 21-orbit aggregate exactly unchanged.
        first = ORBITS.POSITION_ORDER.index((1, 1))
        second = ORBITS.POSITION_ORDER.index((1, 3))
        assert ORBITS.MIXTURE_MAP[first] == ORBITS.MIXTURE_MAP[second] == 3
        modifiers[first] = 1.10
        modifiers[second] = 0.90
        case = _case(Path(tmp), flux_multipliers=modifiers)

        payload = _validate(case)
        assert payload["acceptance_checks"]["region_edi_production_closure"] is True
        assert payload["acceptance_checks"]["region_edi_collision_loss_closure"] is True
        assert payload["power_shape"]["maximum_absolute_relative_error"] == pytest.approx(
            0.10, rel=1.0e-5
        )
        assert payload["power_shape"]["rms_relative_error"] > 0.01
        assert (
            payload["acceptance_checks"]["normalized_91_position_power_max_within_gate"]
            is False
        )
        assert payload["decision"] == "irena30_orbit_fullcore_review_required"


def test_requires_91_region_out_edition_not_21_orbit_edi_for_power() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        with pytest.raises(ValueError, match="INTG IN with 91 physical regions"):
            VALIDATOR.validate_orbit_fullcore(
                case["physics"],
                case["h5"],
                case["edi"],
                case["edi"],
                case["result"],
            )


def test_keff_and_leakage_have_separate_physical_gates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        leakage_case = _case(Path(tmp), leakage=0.11)
        leakage_payload = _validate(leakage_case)
        assert leakage_payload["acceptance_checks"]["keff_within_statistical_gate"] is True
        assert leakage_payload["acceptance_checks"]["leakage_within_gate"] is False

    with tempfile.TemporaryDirectory() as tmp:
        keff_case = _case(Path(tmp), keff=1.04)
        keff_payload = _validate(keff_case)
        assert keff_payload["acceptance_checks"]["keff_evidence_consistent"] is True
        assert keff_payload["eigenvalue"]["z"] > 2.0
        assert keff_payload["acceptance_checks"]["keff_within_statistical_gate"] is False


def test_rejects_empirical_factor_adf_and_nonphysical_bin_policy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        payload = json.loads(case["physics"].read_text(encoding="utf-8"))
        payload["acceptance_checks"]["empirical_eigenvalue_multiplier_used"] = True
        payload["acceptance_checks"]["adf_used"] = True
        payload["floored_bin_count"] = 1
        case["physics"].write_text(json.dumps(payload), encoding="utf-8")

        result = _validate(case)
        assert result["acceptance_checks"]["empirical_eigenvalue_multiplier_absent"] is False
        assert result["acceptance_checks"]["no_nonphysical_sph_bin_policy"] is False
        assert result["decision"] == "irena30_orbit_fullcore_review_required"


def test_native_summary_must_name_the_same_reference_h5() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        payload = json.loads(case["physics"].read_text(encoding="utf-8"))
        payload["handoff"]["augmented_hdf5_path"] = str(
            (Path(tmp) / "other_reference.h5").resolve()
        )
        case["physics"].write_text(json.dumps(payload), encoding="utf-8")

        result = _validate(case)
        assert (
            result["acceptance_checks"]["summary_and_input_use_same_reference_h5"]
            is False
        )
        assert result["decision"] == "irena30_orbit_fullcore_review_required"


def test_rejects_hashless_or_tampered_native_evidence_and_bad_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        summary = json.loads(case["physics"].read_text(encoding="utf-8"))
        summary["handoff"].pop("evidence_sha256")
        case["physics"].write_text(json.dumps(summary), encoding="utf-8")

        payload = _validate(case)
        assert payload["decision"] == "irena30_orbit_fullcore_review_required"
        assert (
            payload["acceptance_checks"][
                "native_evidence_sha256_manifest_complete"
            ]
            is False
        )

    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        case["sph_macrolib"].write_text(
            case["sph_macrolib"].read_text(encoding="utf-8") + "tampered\n",
            encoding="utf-8",
        )

        payload = _validate(case)
        assert payload["decision"] == "irena30_orbit_fullcore_review_required"
        assert (
            payload["acceptance_checks"][
                "native_evidence_sha256_matches_live_files"
            ]
            is False
        )
        assert (
            payload["native_sph"]["evidence_audit"]["files"][
                "macrolib_ascii_path"
            ]["matches"]
            is False
        )

    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        receipt = json.loads(case["converter_receipt"].read_text(encoding="utf-8"))
        receipt["output_sha256"] = "0" * 64
        case["converter_receipt"].write_text(json.dumps(receipt), encoding="utf-8")
        summary = json.loads(case["physics"].read_text(encoding="utf-8"))
        summary["handoff"]["evidence_sha256"]["converter_receipt_path"] = _sha256(
            case["converter_receipt"]
        )
        case["physics"].write_text(json.dumps(summary), encoding="utf-8")

        payload = _validate(case)
        assert payload["decision"] == "irena30_orbit_fullcore_review_required"
        assert (
            payload["acceptance_checks"][
                "native_evidence_sha256_matches_live_files"
            ]
            is True
        )
        assert (
            payload["acceptance_checks"][
                "native_converter_receipt_matches_reference"
            ]
            is False
        )


def test_mapping_input_cannot_close_production_acceptance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        payload = VALIDATOR.validate_orbit_fullcore(
            case["summary"],
            case["h5"],
            case["region"],
            case["edi"],
            case["result"],
        )
        assert payload["decision"] == "irena30_orbit_fullcore_review_required"
        assert payload["acceptance_checks"]["native_summary_is_file_backed"] is False
        assert payload["evidence"]["physics_summary"] is None
        assert len(payload["evidence"]["input_sha256"]["physics_summary"]) == 64


def test_accepts_provably_converged_spn_solver_family() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _case(Path(tmp))
        text = case["result"].read_text(encoding="utf-8")
        text = text.replace(
            "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 "
            "LIVO 3 3 MAXI 1000 EPSI 1.0E-08 ;",
            "TRACK := TRIVAT: GEOM :: EDIT 1 SPN 3 SCAT 2 ;",
        )
        case["result"].write_text(text, encoding="utf-8")
        summary = json.loads(case["physics"].read_text(encoding="utf-8"))
        summary["native_sph"]["solver_family"] = "spn"
        summary["handoff"]["evidence_sha256"]["result_listing_path"] = _sha256(
            case["result"]
        )
        case["physics"].write_text(json.dumps(summary), encoding="utf-8")

        payload = _validate(case)
        assert payload["decision"] == "irena30_orbit_fullcore_physics_passed"
        assert payload["native_sph"]["listing"]["solver_family"] == "spn"
