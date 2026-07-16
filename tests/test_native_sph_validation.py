from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import h5py
import numpy as np
import pytest

from openmc2donjon.macrolib import write_macrolib
from openmc2donjon.multicompo import MixtureXS
from openmc2donjon.native_sph_validation import (
    _native_convergence,
    validate_native_sph,
)
from openmc2donjon.openmc_provenance import (
    collect_openmc_provenance,
    write_openmc_provenance,
)
from openmc2donjon.production_policy import (
    effective_production_thresholds,
    production_preflight_policy_payload,
)


def test_native_convergence_uses_dragons_declared_rms_stopping_criterion() -> None:
    listing = (
        "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 ;\n"
        "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
        "SPHEQU: ITER= 12    ERROR= 7.0E-06 ERR 2= 5.0E-07\n"
        "SPHEQU: ENDING OF SPH CONVERGENCE AFTER   12 ITERATIONS.\n"
        "normal end of execution for donjon 5 Version 5.1.0\n"
    )

    evidence = _native_convergence(listing)

    assert evidence["final_rms_factor_update"] < evidence["epsilon"]
    assert evidence["final_max_factor_update"] > evidence["epsilon"]
    assert evidence["converged"] is True


def test_validates_converged_native_sph_without_empirical_factor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reference_h5 = root / "reference.h5"
        reference_ascii = root / "reference.macrolib.txt"
        sph_ascii = root / "sph.macrolib.txt"
        verify_ascii = root / "verify.macrolib.txt"
        result = root / "donjon.result"
        converter_receipt = root / "converter_summary.json"
        energy_coverage = root / "energy_coverage.json"
        summary = root / "physics_summary.json"

        reference = _mixture(total=1.0, scatter=0.1, nusigf=0.9, flux=10.0)
        corrected = _mixture(
            total=1.1,
            scatter=0.11,
            nusigf=0.99,
            flux=10.0 / 1.1,
            sph=1.1,
        )
        write_macrolib(
            [reference],
            np.array([1.0, 2.0]),
            reference_ascii,
            reference_keff=1.0,
            reference_kinf=1.0,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0]),
            sph_ascii,
            reference_keff=1.0,
            reference_kinf=1.0,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0]),
            verify_ascii,
            reference_keff=1.0,
        )
        with h5py.File(reference_h5, "w") as h5:
            h5.attrs["reference_keff"] = 1.0
            h5.attrs["reference_keff_std_dev"] = 0.01
            h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
            h5.create_group("mixtures").create_group("fuel")
            h5.create_dataset("openmc_volume_flux", data=[[10.0]])
            h5.create_dataset("openmc_volume_flux_std_dev", data=[[0.1]])
        result.write_text(
            "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 ;\n"
            "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
            "SPHEQU: ITER= 12    ERROR= 8.0E-07 ERR 2= 5.0E-07\n"
            "SPHEQU: ENDING OF SPH CONVERGENCE AFTER   12 ITERATIONS.\n"
            "normal end of execution for donjon 5 Version 5.1.0\n",
            encoding="utf-8",
        )
        execution_deck = _bind_clean_execution_deck(result)
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )
        _write_energy_coverage(energy_coverage)

        payload = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            output_json=summary,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
            execution_deck=execution_deck,
        )

        assert payload["quality"]["production_ready"] is True
        assert payload["acceptance_checks"]["adf_used"] is False
        assert payload["acceptance_checks"]["empirical_eigenvalue_multiplier_used"] is False
        assert payload["native_sph"]["iterations"] == 12
        assert payload["native_sph"]["scattering_moments_used"] == 2
        assert payload["native_sph"]["solver_family"] == "sn"
        assert payload["sph"]["kind"] == "dragon-native-sn"
        assert payload["component_balance"]["flux_max_relative_residual"] < 1.0e-12
        assert payload["acceptance_checks"]["converter_receipt_linked"] is True
        evidence_hashes = payload["handoff"]["evidence_sha256"]
        assert set(evidence_hashes) == {
            "augmented_hdf5_path",
            "reference_macrolib_path",
            "macrolib_ascii_path",
            "verification_macrolib_path",
            "result_listing_path",
            "energy_coverage_path",
            "converter_receipt_path",
            "execution_deck_path",
        }
        assert all(len(value) == 64 for value in evidence_hashes.values())
        assert summary.is_file()

        unproved_policy = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
        )
        assert unproved_policy["quality"]["production_ready"] is False
        assert (
            unproved_policy["acceptance_checks"][
                "empirical_eigenvalue_multiplier_used"
            ]
            is None
        )
        assert unproved_policy["acceptance_checks"]["adf_used"] is None
        assert (
            unproved_policy["forbidden_corrections_evidence"]["status"]
            == "not_provable"
        )

        baseline_listing = result.read_text(encoding="utf-8")
        bad_deck = root / "empirical.x2m"
        bad_deck_text = execution_deck.read_text(encoding="utf-8").replace(
            "LINKED_LIST", "REAL KEFF_FACTOR ;\nLINKED_LIST"
        )
        bad_deck.write_text(bad_deck_text, encoding="utf-8")
        result.write_text(bad_deck_text + baseline_listing, encoding="utf-8")
        empirical = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
            execution_deck=bad_deck,
        )
        assert empirical["quality"]["production_ready"] is False
        assert (
            empirical["acceptance_checks"][
                "empirical_eigenvalue_multiplier_used"
            ]
            is True
        )
        result.write_text(baseline_listing, encoding="utf-8")

        adf_deck = root / "adf.x2m"
        adf_deck_text = execution_deck.read_text(encoding="utf-8").replace(
            "LINKED_LIST", "REAL ADF ;\nLINKED_LIST"
        )
        adf_deck.write_text(adf_deck_text, encoding="utf-8")
        result.write_text(adf_deck_text + baseline_listing, encoding="utf-8")
        adf = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
            execution_deck=adf_deck,
        )
        assert adf["quality"]["production_ready"] is False
        assert adf["acceptance_checks"]["adf_used"] is True
        result.write_text(baseline_listing, encoding="utf-8")

        missing_coverage = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert missing_coverage["acceptance_checks"]["energy_coverage_passed"] is False
        assert missing_coverage["quality"]["production_ready"] is False
        assert missing_coverage["energy_coverage_validation"]["issues"] == [
            "energy coverage summary was not supplied"
        ]

        energy_coverage.write_text(
            json.dumps({"decision": "passed"}), encoding="utf-8"
        )
        decision_only = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
        )
        assert decision_only["quality"]["production_ready"] is False
        assert decision_only["energy_coverage_validation"]["self_consistent"] is False
        assert any(
            "scores must be an object" in issue
            for issue in decision_only["energy_coverage_validation"]["issues"]
        )

        _write_energy_coverage(energy_coverage)
        inconsistent_coverage = json.loads(
            energy_coverage.read_text(encoding="utf-8")
        )
        inconsistent_coverage["scores"]["absorption"]["outside_fraction"] = 0.25
        energy_coverage.write_text(
            json.dumps(inconsistent_coverage), encoding="utf-8"
        )
        inconsistent = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
        )
        assert inconsistent["quality"]["production_ready"] is False
        assert any(
            "outside_fraction does not equal" in issue
            for issue in inconsistent["energy_coverage_validation"]["issues"]
        )
        _write_energy_coverage(energy_coverage)

        with h5py.File(reference_h5, "a") as h5:
            del h5["openmc_volume_flux_std_dev"]
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )
        missing_flux_std = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
        )
        assert missing_flux_std["acceptance_checks"][
            "flux_uncertainty_evidence_present"
        ] is False
        assert missing_flux_std["acceptance_checks"][
            "flux_uncertainty_within_production_limit"
        ] is False
        assert missing_flux_std["quality"]["production_ready"] is False
        with h5py.File(reference_h5, "a") as h5:
            h5.create_dataset("openmc_volume_flux_std_dev", data=[[0.1]])
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )

        with h5py.File(reference_h5, "a") as h5:
            h5["openmc_volume_flux"][...] = [[11.0]]
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )
        mismatched_flux = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
        )
        assert mismatched_flux["acceptance_checks"][
            "reference_flux_matches_openmc_evidence"
        ] is False
        assert mismatched_flux["quality"]["production_ready"] is False
        with h5py.File(reference_h5, "a") as h5:
            h5["openmc_volume_flux"][...] = [[10.0]]

        with h5py.File(reference_h5, "a") as h5:
            h5["mixtures/fuel"].create_dataset("sph", data=[1.0])
        with pytest.raises(ValueError, match="SPH/NSPH payload"):
            validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
            )
        with h5py.File(reference_h5, "a") as h5:
            del h5["mixtures/fuel/sph"]
            h5["mixtures/fuel"].create_group("adf")
        with pytest.raises(ValueError, match="ADF payload"):
            validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
            )
        with h5py.File(reference_h5, "a") as h5:
            del h5["mixtures/fuel/adf"]

        reference_with_sph = root / "reference_with_sph.macrolib.txt"
        write_macrolib(
            [_mixture(total=1.0, scatter=0.1, nusigf=0.9, flux=10.0, sph=1.0)],
            np.array([1.0, 2.0]),
            reference_with_sph,
            reference_keff=1.0,
            reference_kinf=1.0,
        )
        with pytest.raises(ValueError, match="reference MACROLIB already contains"):
            validate_native_sph(
                reference_h5,
                reference_with_sph,
                sph_ascii,
                verify_ascii,
                result,
            )

        reference_with_adf = root / "reference_with_adf.macrolib.txt"
        write_macrolib(
            [
                _mixture(
                    total=1.0,
                    scatter=0.1,
                    nusigf=0.9,
                    flux=10.0,
                    adf={"FD_XMIN": np.array([1.0])},
                )
            ],
            np.array([1.0, 2.0]),
            reference_with_adf,
            reference_keff=1.0,
            reference_kinf=1.0,
        )
        with pytest.raises(ValueError, match="reference MACROLIB contains ADF"):
            validate_native_sph(
                reference_h5,
                reference_with_adf,
                sph_ascii,
                verify_ascii,
                result,
            )

        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )

        unlinked = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
        )
        assert unlinked["acceptance_checks"]["converter_receipt_linked"] is False
        assert unlinked["quality"]["production_ready"] is False
        assert unlinked["converter_receipt"]["issues"] == [
            "Converter receipt was not supplied"
        ]

        baseline_receipt = json.loads(converter_receipt.read_text(encoding="utf-8"))
        nonproduction_receipt = dict(baseline_receipt)
        nonproduction_receipt["production_requested"] = False
        nonproduction_receipt["preflight_policy"] = {
            "level": "engineering",
            "production_requested": False,
            "preflight_executed": True,
        }
        converter_receipt.write_text(
            json.dumps(nonproduction_receipt), encoding="utf-8"
        )
        nonproduction = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert nonproduction["quality"]["production_ready"] is False
        assert nonproduction["acceptance_checks"]["converter_receipt_linked"] is False
        assert any(
            "production_requested=true" in issue
            for issue in nonproduction["converter_receipt"]["issues"]
        )
        converter_receipt.write_text(
            json.dumps(baseline_receipt), encoding="utf-8"
        )

        relaxed_receipt = json.loads(json.dumps(baseline_receipt))
        relaxed_receipt["preflight_policy"]["effective_thresholds"][
            "scatter_row_balance_fail"
        ] = 0.5
        converter_receipt.write_text(
            json.dumps(relaxed_receipt), encoding="utf-8"
        )
        relaxed = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert relaxed["quality"]["production_ready"] is False
        assert relaxed["acceptance_checks"]["converter_receipt_linked"] is False
        assert any(
            "exceeds canonical maximum" in issue
            for issue in relaxed["converter_receipt"]["issues"]
        )
        converter_receipt.write_text(
            json.dumps(baseline_receipt), encoding="utf-8"
        )

        for invalid_value in (None, True):
            invalid_receipt = dict(baseline_receipt)
            if invalid_value is None:
                invalid_receipt.pop("physical_sph_required")
            else:
                invalid_receipt["physical_sph_required"] = invalid_value
            converter_receipt.write_text(
                json.dumps(invalid_receipt),
                encoding="utf-8",
            )
            invalid_link = validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
                converter_receipt_json=converter_receipt,
            )
            assert invalid_link["quality"]["production_ready"] is False
            assert invalid_link["acceptance_checks"]["converter_receipt_linked"] is False
            assert any(
                "physical_sph_required=false" in issue
                for issue in invalid_link["converter_receipt"]["issues"]
            )
        converter_receipt.write_text(
            json.dumps(baseline_receipt),
            encoding="utf-8",
        )

        invalid_preflights = (
            None,
            {
                "schema": "openmc2donjon.mgxs-input-contract.v1",
                "decision": "mgxs_input_contract_failed",
                "inputs": [{"ok": False}],
            },
        )
        for invalid_preflight in invalid_preflights:
            invalid_receipt = dict(baseline_receipt)
            invalid_receipt["preflight"] = invalid_preflight
            converter_receipt.write_text(
                json.dumps(invalid_receipt),
                encoding="utf-8",
            )
            invalid_link = validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
                converter_receipt_json=converter_receipt,
            )
            assert invalid_link["quality"]["production_ready"] is False
            assert invalid_link["acceptance_checks"]["converter_receipt_linked"] is False
            assert any(
                "preflight" in issue.lower()
                for issue in invalid_link["converter_receipt"]["issues"]
            )
        converter_receipt.write_text(
            json.dumps(baseline_receipt),
            encoding="utf-8",
        )

        # DRAGON 5.1 SNGMRE can exhaust MAXIT without emitting a failure
        # marker.  An explicit GMRES deck therefore cannot qualify merely
        # because the listing contains no known warning.
        baseline_listing = result.read_text(encoding="utf-8")
        result.write_text(
            baseline_listing.replace(
                "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 ;",
                "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 "
                "GMRES 20 MAXI 1000 EPSI 1.0E-8 ;",
            ),
            encoding="utf-8",
        )
        gmres = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert gmres["native_sph"]["one_speed_acceleration"] == "gmres"
        assert gmres["native_sph"]["one_speed_convergence_provable"] is False
        assert gmres["acceptance_checks"]["one_speed_convergence_provable"] is False
        assert gmres["quality"]["structural_passed"] is False
        assert gmres["quality"]["production_ready"] is False
        result.write_text(baseline_listing, encoding="utf-8")

        # A normal DONJON end and a converged SPH fixed point do not make an
        # unconverged final SN verification solve acceptable.
        result.write_text(
            result.read_text(encoding="utf-8").replace(
                "normal end of execution",
                "SNF: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.\n"
                "normal end of execution",
            ),
            encoding="utf-8",
        )
        rejected = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert rejected["native_sph"]["flux_nonconvergence_count"] == 1
        assert rejected["acceptance_checks"]["final_flux_solve_converged"] is False
        assert rejected["quality"]["structural_passed"] is False
        assert rejected["quality"]["production_ready"] is False

        # FLU2DR does not abort when the eigenvalue/flux outer iteration limit
        # is exhausted.  It writes this marker (three times in DRAGON 5.1) and
        # can still reach DONJON's normal end, so the listing must be rejected.
        result.write_text(
            result.read_text(encoding="utf-8")
            .replace("SNF: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.\n", "")
            .replace(
                "normal end of execution",
                "*** FLU2DR: CONVERGENCE NOT REACHED ***\n"
                "*** FLU2DR: CONVERGENCE NOT REACHED ***\n"
                "*** FLU2DR: CONVERGENCE NOT REACHED ***\n"
                "normal end of execution",
            ),
            encoding="utf-8",
        )
        outer_rejected = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert outer_rejected["native_sph"]["flux_nonconvergence_count"] == 3
        assert outer_rejected["acceptance_checks"]["final_flux_solve_converged"] is False
        assert outer_rejected["quality"]["structural_passed"] is False
        assert outer_rejected["quality"]["production_ready"] is False

        # Hexagonal DSA uses TRIFLV (PNFLV is the BIVAC alternative) for its
        # synthetic low-order correction.  Those solvers also return after a
        # failed one-speed iteration instead of aborting the DONJON run.
        result.write_text(
            result.read_text(encoding="utf-8")
            .replace("*** FLU2DR: CONVERGENCE NOT REACHED ***\n", "")
            .replace(
                "normal end of execution",
                "TRIFLV: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.\n"
                "normal end of execution",
            ),
            encoding="utf-8",
        )
        dsa_rejected = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert dsa_rejected["native_sph"]["flux_nonconvergence_count"] == 1
        assert dsa_rejected["acceptance_checks"]["final_flux_solve_converged"] is False
        assert dsa_rejected["quality"]["structural_passed"] is False
        assert dsa_rejected["quality"]["production_ready"] is False

        # DRAGON's internal negative-factor fallback is a hidden clipping
        # operation.  A listing containing it must never qualify even if the
        # reported fixed point and final transport solve both converge.
        result.write_text(
            result.read_text(encoding="utf-8")
            .replace(
                "TRIFLV: MAXIMUM NUMBER OF ONE-SPEED ITERATION REACHED.\n",
                "",
            )
            .replace(
                "normal end of execution",
                "Warning: negative SPH factor in group 3 and region 1 set to 1.0\n"
                "normal end of execution",
            ),
            encoding="utf-8",
        )
        clipped = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            converter_receipt_json=converter_receipt,
        )
        assert clipped["native_sph"]["negative_factor_correction_count"] == 1
        assert clipped["acceptance_checks"]["native_sph_factors_unmodified"] is False
        assert clipped["quality"]["structural_passed"] is False
        assert clipped["quality"]["production_ready"] is False

        with h5py.File(reference_h5, "a") as h5:
            h5.attrs["sph_applied"] = True
        with pytest.raises(ValueError, match="sph_applied=true"):
            validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
                converter_receipt_json=converter_receipt,
            )

        with h5py.File(reference_h5, "a") as h5:
            h5.attrs["sph_applied"] = False
            h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"
        with pytest.raises(ValueError, match="applied-SPH markers"):
            validate_native_sph(
                reference_h5,
                reference_ascii,
                sph_ascii,
                verify_ascii,
                result,
                converter_receipt_json=converter_receipt,
            )


def test_uses_exported_rate_balance_uncertainty_without_changing_keff() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reference_h5 = root / "reference.h5"
        reference_ascii = root / "reference.macrolib.txt"
        sph_ascii = root / "sph.macrolib.txt"
        verify_ascii = root / "verify.macrolib.txt"
        result = root / "donjon.result"
        converter_receipt = root / "converter_summary.json"
        energy_coverage = root / "energy_coverage.json"

        # The sampled reference balance and the deterministic result both
        # differ from the independently estimated CE eigenvalue by 1.5%.
        # A declared, conservative 1% balance-score uncertainty makes both
        # end-to-end comparisons valid two-sigma passes.  It is propagated
        # evidence, not a multiplier or a modification of either result.
        reference = _mixture(total=1.0, scatter=0.1, nusigf=0.9135, flux=10.0)
        corrected = _mixture(
            total=1.0,
            scatter=0.1,
            nusigf=0.9135,
            flux=10.0,
            sph=1.0,
        )
        write_macrolib(
            [reference],
            np.array([1.0, 2.0]),
            reference_ascii,
            reference_keff=1.0,
            reference_kinf=1.015,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0]),
            sph_ascii,
            reference_keff=1.0,
            reference_kinf=1.015,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0]),
            verify_ascii,
            reference_keff=1.015,
        )
        with h5py.File(reference_h5, "w") as h5:
            h5.attrs["reference_keff"] = 1.0
            h5.attrs["reference_keff_std_dev"] = 0.001
            h5.attrs["reference_rate_balance_tally_keff"] = 1.014
            h5.attrs["reference_rate_balance_std_dev"] = 0.01
            h5.attrs["reference_rate_balance_uncertainty_method"] = (
                "conservative-l1-score-bound-no-covariance"
            )
            h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
            h5.create_group("mixtures").create_group("fuel")
            h5.create_dataset("openmc_volume_flux", data=[[10.0]])
            h5.create_dataset("openmc_volume_flux_std_dev", data=[[0.1]])
        result.write_text(
            "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
            "SPHEQU: ITER= 2 ERROR= 8.0E-07 ERR 2= 5.0E-07\n"
            "SPHEQU: ENDING OF SPH CONVERGENCE AFTER 2 ITERATIONS.\n"
            "normal end of execution for donjon 5 Version 5.1.0\n",
            encoding="utf-8",
        )
        execution_deck = _bind_clean_execution_deck(result)
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )
        _write_energy_coverage(energy_coverage)

        payload = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
            execution_deck=execution_deck,
        )

        validation = payload["eigenvalue_validation"]
        assert payload["quality"]["production_ready"] is True
        assert validation["reference_rate_balance_keff"] == 1.015
        assert validation["reference_rate_balance_combined_std_dev"] == 0.011
        assert validation["donjon_keff"] == 1.015
        assert validation["donjon_combined_std_dev"] == 0.011
        assert validation["donjon_z"] < 2.0


def test_leaking_model_uses_finite_balance_not_collision_kinf() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reference_h5 = root / "reference.h5"
        reference_ascii = root / "reference.macrolib.txt"
        sph_ascii = root / "sph.macrolib.txt"
        verify_ascii = root / "verify.macrolib.txt"
        result = root / "donjon.result"
        converter_receipt = root / "converter_summary.json"
        energy_coverage = root / "energy_coverage.json"

        reference = _mixture(total=1.0, scatter=0.1, nusigf=0.9, flux=10.0)
        corrected = _mixture(
            total=1.0,
            scatter=0.1,
            nusigf=0.9,
            flux=10.0,
            sph=1.0,
        )
        write_macrolib(
            [reference],
            np.array([1.0, 2.0]),
            reference_ascii,
            reference_keff=1.0,
            reference_kinf=1.2,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0]),
            sph_ascii,
            reference_keff=1.0,
            reference_kinf=1.2,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0]),
            verify_ascii,
            reference_keff=1.0,
        )
        with h5py.File(reference_h5, "w") as h5:
            h5.attrs["reference_keff"] = 1.0
            h5.attrs["reference_keff_std_dev"] = 0.001
            h5.attrs["boundary_conditions"] = "radial vacuum; axial reflective"
            h5.attrs["reference_collision_balance_kinf"] = 1.2
            h5.attrs["reference_collision_balance_std_dev"] = 0.01
            h5.attrs["reference_finite_balance_keff"] = 1.0
            h5.attrs["reference_finite_balance_std_dev"] = 0.01
            h5.attrs["reference_leakage"] = 0.2
            h5.attrs["reference_leakage_std_dev"] = 0.001
            h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
            h5.create_group("mixtures").create_group("fuel")
            h5.create_dataset("openmc_volume_flux", data=[[10.0]])
            h5.create_dataset("openmc_volume_flux_std_dev", data=[[0.1]])
        result.write_text(
            "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 ;\n"
            "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
            "SPHEQU: ITER= 2 ERROR= 8.0E-07 ERR 2= 5.0E-07\n"
            "SPHEQU: ENDING OF SPH CONVERGENCE AFTER 2 ITERATIONS.\n"
            "normal end of execution for donjon 5 Version 5.1.0\n",
            encoding="utf-8",
        )
        execution_deck = _bind_clean_execution_deck(result)
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )
        _write_energy_coverage(energy_coverage)

        payload = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
            execution_deck=execution_deck,
        )

        validation = payload["eigenvalue_validation"]
        assert payload["quality"]["production_ready"] is True
        assert validation["reference_physical_balance_kind"] == "finite-domain-keff"
        assert validation["reference_collision_balance_kinf"] == 1.2
        assert validation["reference_physical_balance_keff"] == 1.0
        assert validation["reference_physical_balance_delta_pcm"] == 0.0
        assert payload["acceptance_checks"][
            "leakage_balance_available_when_required"
        ] is True


def test_rejects_component_flux_and_net_loss_residuals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reference_h5 = root / "reference.h5"
        reference_ascii = root / "reference.macrolib.txt"
        sph_ascii = root / "sph.macrolib.txt"
        verify_ascii = root / "verify.macrolib.txt"
        result = root / "donjon.result"
        converter_receipt = root / "converter_summary.json"
        energy_coverage = root / "energy_coverage.json"

        reference = _two_group_mixture(flux=np.array([10.0, 10.0]))
        corrected = _two_group_mixture(
            flux=np.array([10.0, 10.0]), sph=np.array([1.0, 1.0])
        )
        verification = _two_group_mixture(
            flux=np.array([10.0, 5.0]), sph=np.array([1.0, 1.0])
        )
        write_macrolib(
            [reference],
            np.array([1.0, 2.0, 3.0]),
            reference_ascii,
            reference_keff=1.0,
            reference_kinf=1.0,
        )
        write_macrolib(
            [corrected],
            np.array([1.0, 2.0, 3.0]),
            sph_ascii,
            reference_keff=1.0,
            reference_kinf=1.0,
        )
        write_macrolib(
            [verification],
            np.array([1.0, 2.0, 3.0]),
            verify_ascii,
            reference_keff=1.0,
        )
        with h5py.File(reference_h5, "w") as h5:
            h5.attrs["reference_keff"] = 1.0
            h5.attrs["reference_keff_std_dev"] = 0.001
            h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
            h5.create_group("mixtures").create_group("fuel")
            h5.create_dataset("openmc_volume_flux", data=[[10.0, 10.0]])
            h5.create_dataset(
                "openmc_volume_flux_std_dev", data=[[0.1, 0.1]]
            )
        result.write_text(
            "TRACK := SNT: GEOM :: EDIT 1 DIAM 1 SN 8 SCAT 2 ;\n"
            "EPSPH  1.0E-06   (CONVERGENCE CRITERION)\n"
            "SPHEQU: ITER= 2 ERROR= 8.0E-07 ERR 2= 5.0E-07\n"
            "SPHEQU: ENDING OF SPH CONVERGENCE AFTER 2 ITERATIONS.\n"
            "normal end of execution for donjon 5 Version 5.1.0\n",
            encoding="utf-8",
        )
        _write_converter_receipt(
            converter_receipt,
            input_path=reference_h5,
            output_path=reference_ascii,
        )
        _write_energy_coverage(energy_coverage)

        payload = validate_native_sph(
            reference_h5,
            reference_ascii,
            sph_ascii,
            verify_ascii,
            result,
            energy_coverage_json=energy_coverage,
            converter_receipt_json=converter_receipt,
        )

        assert payload["quality"]["production_ready"] is False
        assert payload["acceptance_checks"][
            "component_flux_equivalence_within_tolerance"
        ] is False
        assert payload["acceptance_checks"][
            "component_net_loss_equivalence_within_tolerance"
        ] is False
        balance = payload["component_balance"]
        assert balance["maximum_component_flux_relative_residual"] == pytest.approx(
            0.5
        )
        assert balance[
            "maximum_component_net_loss_relative_residual"
        ] == pytest.approx(0.25)
        assert balance["acceptance_relative_tolerance"] == 1.0e-4


def _two_group_mixture(
    *, flux: np.ndarray, sph: np.ndarray | None = None
) -> MixtureXS:
    return MixtureXS(
        name="fuel",
        total=np.array([1.0, 1.0]),
        absorption=np.array([0.9, 0.9]),
        fission=np.array([0.72, 0.0]),
        nu_fission=np.array([1.8, 0.0]),
        chi=np.array([1.0, 0.0]),
        scatter_matrix=np.array([[[0.1, 0.0], [0.0, 0.1]]]),
        fissionable=True,
        volume=1.0,
        flux_weight=np.asarray(flux, dtype=float),
        transport_total=np.array([1.0, 1.0]),
        sph=None if sph is None else np.asarray(sph, dtype=float),
    )


def _mixture(
    *,
    total: float,
    scatter: float,
    nusigf: float,
    flux: float,
    sph: float | None = None,
    adf: dict[str, np.ndarray] | None = None,
) -> MixtureXS:
    return MixtureXS(
        name="fuel",
        total=np.array([total]),
        absorption=np.array([total - scatter]),
        fission=np.array([nusigf / 2.5]),
        nu_fission=np.array([nusigf]),
        chi=np.array([1.0]),
        scatter_matrix=np.array([[[scatter]]]),
        fissionable=True,
        volume=1.0,
        flux_weight=np.array([flux]),
        transport_total=np.array([total]),
        adf=adf,
        sph=None if sph is None else np.array([sph]),
    )


def _write_converter_receipt(
    path: Path,
    *,
    input_path: Path,
    output_path: Path,
) -> None:
    openmc_provenance = _bind_complete_openmc_provenance(input_path)
    thresholds = effective_production_thresholds(
        scatter_row_balance_fail=None,
        transport_p1_fail=None,
        chi_sum_tolerance=None,
        uncertainty_warn=None,
        uncertainty_fail=None,
        uncertainty_production_fail=None,
        uncertainty_mean_abs_floor=1.0e-12,
    )
    path.write_text(
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
                "input_path": str(input_path.resolve()),
                "input_sha256": _sha256(input_path),
                "openmc_provenance": openmc_provenance,
                "output_path": str(output_path.resolve()),
                "output_sha256": _sha256(output_path),
            }
        ),
        encoding="utf-8",
    )


def _bind_complete_openmc_provenance(input_path: Path) -> dict[str, object]:
    source_dir = input_path.parent / ".openmc-source-fixture"
    source_dir.mkdir(exist_ok=True)
    recipe = source_dir / "export_recipe.py"
    geometry = source_dir / "geometry.xml"
    materials = source_dir / "materials.xml"
    settings = source_dir / "settings.xml"
    cross_sections = source_dir / "cross_sections.xml"
    library = source_dir / "U235.h5"
    statepoint = source_dir / "statepoint.20.h5"
    recipe.write_text("# complete test recipe\n", encoding="utf-8")
    geometry.write_text("<geometry/>\n", encoding="utf-8")
    settings.write_text(
        """<settings>
  <run_mode>eigenvalue</run_mode>
  <particles>1000</particles>
  <batches>20</batches>
  <inactive>5</inactive>
  <generations_per_batch>1</generations_per_batch>
  <seed>19</seed>
</settings>
""",
        encoding="utf-8",
    )
    library.write_bytes(b"test evaluated data\n")
    cross_sections.write_text(
        '<cross_sections><library materials="U235" path="U235.h5" '
        'type="neutron"/></cross_sections>\n',
        encoding="utf-8",
    )
    materials.write_text(
        """<materials>
  <cross_sections>cross_sections.xml</cross_sections>
  <material id="1"><nuclide name="U235"/></material>
</materials>
""",
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
    verified = write_openmc_provenance(input_path, record)
    return verified


def _bind_clean_execution_deck(result_listing: Path) -> Path:
    deck = result_listing.with_suffix(".x2m")
    deck_text = (
        "MODULE SPH: FLUD: OUT: END: ;\n"
        "LINKED_LIST MACROREF MACROSPH TRACK SYSTEM FLUX ;\n"
        "MACROSPH := SPH: MACROREF TRACK :: EDIT 0 MAXI 300 EPSI 1.0E-6 ;\n"
        "SYSTEM := OUT: MACROSPH TRACK :: EDIT 0 ;\n"
        "FLUX := FLUD: SYSTEM TRACK :: EDIT 0 ;\n"
        "SPH_ASC := MACROSPH ;\n"
        "END: ;\n"
    )
    deck.write_text(deck_text, encoding="utf-8")
    listing = result_listing.read_text(encoding="utf-8")
    result_listing.write_text(deck_text + listing, encoding="utf-8")
    return deck


def _write_energy_coverage(
    path: Path,
    *,
    outside_fraction: float = 0.0,
    max_outside_fraction: float = 0.005,
    ) -> None:
    retained = 1.0 - outside_fraction
    passed = outside_fraction <= max_outside_fraction
    path.write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.energy-coverage.v1",
                "decision": "passed" if passed else "rejected",
                "statepoint": "/tmp/statepoint.100.h5",
                "energy_mesh_id": "anl-24c-20mev",
                "full_energy_min_ev": 1.0e-5,
                "mg_energy_min_ev": 1.0e-5,
                "mg_energy_max_ev": 2.0e7,
                "full_energy_max_ev": 2.0e7,
                "max_outside_fraction": max_outside_fraction,
                "scores": {
                    score: {
                        "low_tail": outside_fraction,
                        "retained": retained,
                        "high_tail": 0.0,
                        "outside_fraction": outside_fraction,
                        "passed": passed,
                    }
                    for score in (
                        "absorption",
                        "fission",
                        "kappa-fission",
                        "nu-fission",
                    )
                },
            }
        ),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
