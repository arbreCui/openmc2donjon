from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon import mgxs_input_contract as validator
from openmc2donjon.energy_groups import energy_bounds_sha256, load_energy_mesh


class MgxsInputContractTests(unittest.TestCase):
    def test_validates_multistate_burnup_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multi.h5"
            write_multistate_fixture(path)

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=True,
                require_volume=True,
                expected_adf_faces=None,
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.mixtures, 1)
        self.assertEqual(report.stateful_mixtures, 1)
        self.assertEqual(report.state_points, 2)
        self.assertEqual(report.calculations, 2)
        self.assertEqual(report.burnup_axis_path, "/state_points/BURN")
        self.assertEqual(report.burnup_axis_values, 2)
        self.assertEqual(report.transport_total_datasets, 2)
        self.assertEqual(report.transport_total_derivable, 2)
        self.assertEqual(report.fissionable_mixtures, 1)
        self.assertEqual(report.scatter_axes, ["moment,from,to"])

    def test_multistate_requires_burnup_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing_burn.h5"
            write_multistate_fixture(path, burnup_values=None)

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
            )

        self.assertFalse(report.ok)
        self.assertIn("multi-state HDF5 requires a BURN axis", report.issues)

    def test_burnup_axis_length_must_match_state_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad_burn.h5"
            write_multistate_fixture(path, burnup_values=[0.0])

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
            )

        self.assertFalse(report.ok)
        self.assertIn("BURN axis length must match number of states: 1 != 2", report.issues)

    def test_all_mixtures_must_have_same_state_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mixed_states.h5"
            write_multistate_fixture(path)
            with h5py.File(path, "a") as h5:
                moderator = h5["mixtures"].create_group("moderator")
                write_one_state_payload(moderator, total=[0.3, 0.4], fissionable=False)

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
            )

        self.assertFalse(report.ok)
        self.assertIn(
            "all mixtures must contain the same number of state points; got [2, 1]",
            report.issues,
        )

    def test_rejects_unsupported_state_point_axis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "unsupported_axis.h5"
            write_multistate_fixture(path)
            with h5py.File(path, "a") as h5:
                h5["state_points"].create_dataset("BORON", data=np.array([500.0, 600.0]))

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
            )

        self.assertFalse(report.ok)
        self.assertIn(
            "unsupported /state_points axis/axes: BORON; only BURN is supported",
            report.issues,
        )

    def test_rejects_multiple_burnup_axis_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "duplicate_burn.h5"
            write_multistate_fixture(path)
            with h5py.File(path, "a") as h5:
                h5.create_dataset("burnup_values", data=np.array([0.0, 10.0]))

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
            )

        self.assertFalse(report.ok)
        self.assertIn(
            "multiple BURN axis definitions found: /state_points/BURN, /burnup_values",
            report.issues,
        )

    def test_scatter_row_balance_records_balanced_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "balanced.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
                scatter_row_balance_warn=1.0e-6,
                scatter_row_balance_fail=1.0e-3,
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.warnings, [])
        self.assertIsNotNone(report.scatter_row_balance_max_abs)
        self.assertIsNotNone(report.scatter_row_balance_max_rel)
        self.assertLess(float(report.scatter_row_balance_max_abs), 1.0e-15)
        self.assertLess(float(report.scatter_row_balance_max_rel), 1.0e-15)
        self.assertTrue((report.scatter_row_balance_worst or "").startswith("fuel: group="))

    def test_scatter_row_balance_warns_above_warn_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "noisy.h5"
            write_single_state_fixture(path, total=[0.5, 0.7])

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
                scatter_row_balance_warn=0.1,
            )

        self.assertTrue(report.ok, report.issues)
        self.assertAlmostEqual(report.scatter_row_balance_max_rel or 0.0, 0.457142857)
        self.assertTrue(
            any("scatter row-balance max relative residual" in item for item in report.warnings)
        )

    def test_scatter_row_balance_fails_above_fail_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad_balance.h5"
            write_single_state_fixture(path, total=[0.5, 0.7])

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
                scatter_row_balance_fail=0.1,
            )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("exceeds fail threshold" in item for item in report.issues)
        )

    def test_production_preflight_fails_unbalanced_scatter_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad_balance.h5"
            summary = Path(tmpdir) / "summary.json"
            write_single_state_fixture(path, total=[0.5, 0.7])
            append_production_metadata(path)

            ok = validator.run_preflight(
                [path],
                production=True,
                uncertainty_warn=None,
                summary_json=summary,
            )

            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertFalse(ok)
        self.assertTrue(
            any(
                "scatter row-balance max relative residual" in issue
                for issue in payload["inputs"][0]["issues"]
            )
        )

    def test_scatter_row_balance_uses_declared_moment_last_axes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "moment_last.h5"
            p0 = np.array([[0.2, 0.04], [0.0, 0.3]])
            p1 = np.array([[0.01, 0.0], [0.0, 0.02]])
            scatter = np.stack((p0, p1), axis=2)
            write_single_state_fixture(
                path,
                total=[0.29, 0.38],
                legendre_order=1,
                scatter_axes="G_in,G_out,moment",
                scatter=scatter,
            )

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
                scatter_row_balance_fail=1.0e-12,
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.scatter_axes, ["G_in,G_out,moment"])
        self.assertIsNotNone(report.scatter_row_balance_max_rel)
        self.assertLess(float(report.scatter_row_balance_max_rel), 1.0e-15)

    def test_local_energy_bounds_must_match_root_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "local_bounds.h5"
            write_multistate_fixture(path)
            with h5py.File(path, "a") as h5:
                root = h5["energy_bounds"][:]
                h5["mixtures/fuel"].create_dataset("energy_bounds", data=root)

            matching_report = validator.validate_input(
                path,
                require_energy_bounds_consistency=True,
            )

            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel/states/00000002"].create_dataset(
                    "energy_bounds",
                    data=np.array([1.0e-5, 0.9, 1.0e7]),
                )

            mismatch_report = validator.validate_input(
                path,
                require_energy_bounds_consistency=True,
            )

        self.assertTrue(matching_report.ok, matching_report.issues)
        self.assertEqual(matching_report.energy_bounds_local_count, 1)
        self.assertFalse(mismatch_report.ok)
        self.assertEqual(mismatch_report.energy_bounds_local_count, 2)
        self.assertTrue(
            any("differs from /energy_bounds" in issue for issue in mismatch_report.issues)
        )

    def test_chi_sum_gate_applies_only_to_fissionable_calculations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad_chi.h5"
            moderator = Path(tmpdir) / "moderator_chi.h5"
            write_single_state_fixture(bad, total=[0.29, 0.38])
            write_single_state_fixture(moderator, total=[0.29, 0.38])
            with h5py.File(bad, "a") as h5:
                h5["mixtures/fuel/chi"][:] = np.array([0.8, 0.0])
            with h5py.File(moderator, "a") as h5:
                h5["mixtures/fuel"].attrs["fissionable"] = False
                h5["mixtures/fuel/chi"][:] = np.array([0.0, 0.0])

            bad_report = validator.validate_input(
                bad,
                chi_sum_tolerance=1.0e-6,
            )
            moderator_report = validator.validate_input(
                moderator,
                chi_sum_tolerance=1.0e-6,
            )

        self.assertFalse(bad_report.ok)
        self.assertEqual(bad_report.chi_checked, 1)
        self.assertAlmostEqual(bad_report.chi_sum_max_abs_error or 0.0, 0.2)
        self.assertTrue(any("chi sum error" in issue for issue in bad_report.issues))
        self.assertTrue(moderator_report.ok, moderator_report.issues)
        self.assertEqual(moderator_report.chi_checked, 0)

    def test_nu_ratio_outlier_warns_without_failing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nu_outlier.h5"
            summary = Path(tmpdir) / "summary.json"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel/nu_fission"][:] = np.array([0.1, 0.03])

            report = validator.validate_input(path)
            ok = validator.run_preflight([path], summary_json=summary)
            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertTrue(report.ok, report.issues)
        self.assertTrue(ok)
        self.assertEqual(report.nu_ratio_checked_bins, 2)
        self.assertAlmostEqual(report.nu_ratio_max or 0.0, 10.0)
        self.assertEqual(report.nu_ratio_warning_count, 1)
        self.assertEqual(
            payload["inputs"][0]["physics_checks"]["nu_ratio_warning_count"],
            1,
        )
        self.assertTrue(
            any("nu_fission/fission" in warning for warning in report.warnings)
        )

    def test_adf_face_consistency_gate_fails_when_only_some_calculations_have_adf(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "adf_faces.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                fuel = h5["mixtures/fuel"]
                adf = fuel.create_dataset("adf", data=np.ones((2, 2)))
                adf.attrs["face_names"] = np.asarray(["left", "right"], dtype="S")
                moderator = h5["mixtures"].create_group("moderator")
                write_one_state_payload(
                    moderator,
                    total=[0.29, 0.38],
                    fissionable=False,
                )

            report = validator.validate_input(
                path,
                require_adf_face_consistency=True,
            )

        self.assertFalse(report.ok)
        self.assertTrue(report.adf_face_consistency_checked)
        self.assertEqual(report.adf_face_consistency_errors, 1)
        self.assertTrue(any("ADF faces" in issue for issue in report.issues))

    def test_transport_total_p1_gate_compares_explicit_and_derived_transport(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad_transport.h5"
            good = Path(tmpdir) / "good_transport.h5"
            p0 = np.array([[0.2, 0.04], [0.0, 0.3]])
            p1 = np.array([[0.01, 0.02], [0.03, 0.04]])
            scatter = np.stack((p0, p1), axis=0)
            write_single_state_fixture(
                bad,
                total=[0.29, 0.38],
                legendre_order=1,
                scatter=scatter,
            )
            write_single_state_fixture(
                good,
                total=[0.29, 0.38],
                legendre_order=1,
                scatter=scatter,
            )
            with h5py.File(good, "a") as h5:
                h5["mixtures/fuel/transport_total"][:] = np.array([0.26, 0.31])

            bad_report = validator.validate_input(
                bad,
                transport_p1_fail=5.0e-2,
            )
            good_report = validator.validate_input(
                good,
                transport_p1_fail=5.0e-2,
            )

        self.assertFalse(bad_report.ok)
        self.assertEqual(bad_report.transport_p1_checked, 1)
        self.assertGreater(bad_report.transport_p1_max_rel or 0.0, 5.0e-2)
        self.assertTrue(
            any("transport_total/P1" in issue for issue in bad_report.issues)
        )
        self.assertTrue(good_report.ok, good_report.issues)
        self.assertEqual(good_report.transport_p1_checked, 1)
        self.assertIsNotNone(good_report.transport_p1_max_rel)
        self.assertLess(float(good_report.transport_p1_max_rel), 1.0e-12)

    def test_missing_volume_is_reported_before_it_becomes_default_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing_volume.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                del h5["mixtures/fuel"].attrs["volume"]

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.volume_attributes, 0)
        self.assertEqual(report.volume_defaulted, 1)
        self.assertTrue(
            any("default volume 1.0" in warning for warning in report.warnings)
        )

    def test_require_h_factor_gates_groupwise_kappa_fission_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing_h_factor.h5"
            present = Path(tmpdir) / "present_h_factor.h5"
            write_single_state_fixture(missing, total=[0.29, 0.38])
            write_single_state_fixture(present, total=[0.29, 0.38])
            with h5py.File(present, "a") as h5:
                h5["mixtures/fuel"].create_dataset(
                    "kappa_fission",
                    data=np.array([3.2e-12, 3.1e-12]),
                )

            missing_report = validator.validate_input(
                missing,
                require_h_factor=True,
            )
            present_report = validator.validate_input(
                present,
                require_h_factor=True,
            )

        self.assertFalse(missing_report.ok)
        self.assertTrue(
            any("H-FACTOR/kappa_fission" in issue for issue in missing_report.issues)
        )
        self.assertEqual(missing_report.h_factor_datasets, 0)
        self.assertTrue(present_report.ok, present_report.issues)
        self.assertEqual(present_report.h_factor_datasets, 1)

    def test_require_h_factor_allows_nonfissionable_mixture_without_h_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "moderator.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].attrs["fissionable"] = False

            report = validator.validate_input(path, require_h_factor=True)

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.fissionable_mixtures, 0)
        self.assertEqual(report.h_factor_datasets, 0)

    def test_require_mixture_order_gates_declared_names_and_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "order.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])

            missing_report = validator.validate_input(
                path,
                require_mixture_order=True,
            )

            with h5py.File(path, "a") as h5:
                h5.create_dataset(
                    "mixture_names",
                    data=np.asarray(["fuel"], dtype="S"),
                )

            missing_index_report = validator.validate_input(
                path,
                require_mixture_order=True,
            )

            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].attrs["source_domain_index"] = 2

            wrong_index_report = validator.validate_input(
                path,
                require_mixture_order=True,
            )

            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].attrs["source_domain_index"] = 1

            valid_report = validator.validate_input(
                path,
                require_mixture_order=True,
            )

        self.assertFalse(missing_report.ok)
        self.assertIn(
            "/mixture_names dataset is required to declare DONJON mixture order",
            missing_report.issues,
        )
        self.assertFalse(missing_index_report.ok)
        self.assertIn(
            "mixture fuel: source_domain_index attribute is required",
            missing_index_report.issues,
        )
        self.assertFalse(wrong_index_report.ok)
        self.assertIn(
            "mixture fuel: source_domain_index 2 does not match declared mixture order position 1",
            wrong_index_report.issues,
        )
        self.assertTrue(valid_report.ok, valid_report.issues)
        self.assertTrue(valid_report.declared_mixture_order)
        self.assertEqual(valid_report.source_domain_indices, 1)

    def test_production_domain_provenance_requires_mode_and_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "domain_provenance.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
                fuel = h5["mixtures/fuel"]
                fuel.attrs["source_domain_index"] = 1
                fuel.create_dataset(
                    "kappa_fission",
                    data=np.array([3.2e-12, 3.1e-12]),
                )

            missing_report = validator.validate_input(
                path,
                require_mixture_order=True,
                require_domain_mode=True,
                require_source_domain_metadata=True,
                require_transport_dataset=True,
                require_volume=True,
                require_h_factor=True,
            )

            with h5py.File(path, "a") as h5:
                h5.attrs["domain_mode"] = "assembly"
                h5["mixtures/fuel"].attrs["source_domain_id"] = 101
                h5["mixtures/fuel"].attrs["source_domain_type"] = "cell"

            valid_report = validator.validate_input(
                path,
                require_mixture_order=True,
                require_domain_mode=True,
                require_source_domain_metadata=True,
                require_transport_dataset=True,
                require_volume=True,
                require_h_factor=True,
            )

        self.assertFalse(missing_report.ok)
        self.assertIn(
            "/attrs domain_mode is required for production handoff provenance",
            missing_report.issues,
        )
        self.assertIn(
            "mixture fuel: source_domain_id attribute is required",
            missing_report.issues,
        )
        self.assertIn(
            "mixture fuel: source_domain_type attribute is required",
            missing_report.issues,
        )
        self.assertTrue(valid_report.ok, valid_report.issues)
        self.assertEqual(valid_report.domain_mode, "assembly")
        self.assertEqual(valid_report.source_domain_metadata, 1)

    def test_openmc_volume_flux_contract_validates_reference_flux_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "reference_flux.h5"
            bad = Path(tmpdir) / "bad_reference_flux.h5"
            missing = Path(tmpdir) / "missing_reference_flux.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            write_single_state_fixture(bad, total=[0.29, 0.38])
            write_single_state_fixture(missing, total=[0.29, 0.38])
            append_openmc_volume_flux(path)
            append_openmc_volume_flux(
                bad,
                values=np.array([[10.0, -1.0]]),
                group_order="openmc_native",
                mixture_names=("moderator",),
            )

            valid_report = validator.validate_input(
                path,
                require_openmc_volume_flux=True,
            )
            bad_report = validator.validate_input(
                bad,
                require_openmc_volume_flux=True,
            )
            missing_report = validator.validate_input(
                missing,
                require_openmc_volume_flux=True,
            )

        self.assertTrue(valid_report.ok, valid_report.issues)
        self.assertTrue(valid_report.openmc_volume_flux_present)
        self.assertEqual(valid_report.openmc_volume_flux_shape, (1, 2))
        self.assertEqual(valid_report.openmc_volume_flux_group_order, "mgxs_donjon")
        self.assertEqual(valid_report.openmc_volume_flux_mixture_names, 1)
        self.assertFalse(bad_report.ok)
        self.assertTrue(
            any("group_order must be 'mgxs_donjon'" in item for item in bad_report.issues)
        )
        self.assertIn("/openmc_volume_flux values must be positive", bad_report.issues)
        self.assertTrue(
            any("mixture_names must match" in item for item in bad_report.issues)
        )
        self.assertFalse(missing_report.ok)
        self.assertIn("/openmc_volume_flux dataset is required", missing_report.issues)

    def test_openmc_volume_flux_contract_validates_std_dev(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "flux_std_dev.h5"
            write_single_state_fixture(path, total=[0.5, 0.7])
            append_openmc_volume_flux(
                path,
                values=np.array([[10.0, 20.0]]),
                std_dev=np.array([[0.1, 6.0]]),
            )

            report = validator.validate_input(
                path,
                require_openmc_volume_flux=True,
                uncertainty=validator.UncertaintyConfig(warn_threshold=0.05),
            )

        self.assertTrue(report.ok, report.issues)
        self.assertTrue(report.openmc_volume_flux_std_dev_present)
        self.assertEqual(report.openmc_volume_flux_std_dev_shape, (1, 2))
        self.assertAlmostEqual(report.openmc_volume_flux_std_dev_max_rel or 0.0, 0.3)
        self.assertIn("g=2", report.openmc_volume_flux_std_dev_worst or "")
        self.assertTrue(
            any("volume-flux statistical uncertainty" in item for item in report.warnings)
        )

    def test_energy_group_identity_gate_accepts_matching_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "c5g7.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                bounds = h5["energy_bounds"][:]
                h5.attrs["energy_group_structure"] = "C5G7-2g-test"
                h5.attrs["energy_bounds_sha256"] = energy_bounds_sha256(bounds)

            report = validator.validate_input(
                path,
                expected_energy_group_structure="C5G7-2g-test",
                expected_energy_bounds=[1.0e-5, 1.0, 1.0e7],
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.energy_group_structure, "C5G7-2g-test")
        self.assertEqual(
            report.energy_bounds_sha256,
            energy_bounds_sha256([1.0e-5, 1.0, 1.0e7]),
        )

    def test_energy_group_identity_identifies_known_mesh(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "casmo7.h5"
            write_known_mesh_fixture(path, mesh_id="casmo_7")

            report = validator.validate_input(path)

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.energy_mesh_id, "casmo_7")
        self.assertEqual(report.energy_mesh_name, "CASMO-7")
        self.assertAlmostEqual(report.energy_mesh_tolerance or 0.0, 1.0e-6)
        self.assertFalse(
            any("known energy mesh" in warning for warning in report.warnings)
        )

    def test_unknown_energy_mesh_can_warn_or_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "unknown_mesh.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])

            warning_report = validator.validate_input(
                path,
                warn_unknown_energy_mesh=True,
            )
            hard_report = validator.validate_input(
                path,
                require_known_energy_mesh=True,
            )

        self.assertTrue(warning_report.ok, warning_report.issues)
        self.assertTrue(
            any("did not match a bundled known energy mesh" in item for item in warning_report.warnings)
        )
        self.assertFalse(hard_report.ok)
        self.assertTrue(
            any("does not match a bundled known energy mesh" in item for item in hard_report.issues)
        )

    def test_energy_group_identity_gate_rejects_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wrong_bounds.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])
            with h5py.File(path, "a") as h5:
                h5.attrs["energy_group_structure"] = "C5G7-2g-test"
                h5.attrs["energy_bounds_sha256"] = "bad-digest"

            report = validator.validate_input(
                path,
                expected_energy_group_structure="WIMS-2g-test",
                expected_energy_bounds=[1.0e-5, 0.625, 1.0e7],
                expected_energy_bounds_sha256="also-wrong",
            )

        self.assertFalse(report.ok)
        self.assertTrue(
            any("energy_bounds_sha256 does not match" in item for item in report.issues)
        )
        self.assertTrue(
            any("energy_group_structure mismatch" in item for item in report.issues)
        )
        self.assertTrue(
            any("/energy_bounds SHA-256 mismatch" in item for item in report.issues)
        )
        self.assertTrue(
            any("/energy_bounds differ" in item for item in report.issues)
        )

    def test_uncertainty_warns_for_high_relative_std_dev(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "uncertain.h5"
            write_single_state_fixture(path, total=[0.5, 0.7])
            with h5py.File(path, "a") as h5:
                fuel = h5["mixtures/fuel"]
                fuel.create_dataset("total_std_dev", data=np.array([0.001, 0.14]))
                fuel.create_dataset(
                    "scatter_matrix_std_dev",
                    data=np.zeros((1, 2, 2)),
                )

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
                uncertainty=validator.UncertaintyConfig(warn_threshold=0.05),
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.uncertainty_datasets, 2)
        self.assertEqual(report.uncertainty_expected_datasets, 7)
        self.assertAlmostEqual(report.uncertainty_max_rel or 0.0, 0.2)
        self.assertTrue((report.uncertainty_worst or "").startswith("fuel: total g=2"))
        self.assertTrue(
            any("statistical uncertainty" in item for item in report.warnings)
        )
        self.assertTrue(report.uncertainty_top)

    def test_uncertainty_can_fail_and_validates_std_dev_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad_uncertainty.h5"
            write_single_state_fixture(path, total=[0.5, 0.7])
            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].create_dataset(
                    "absorption_std_dev",
                    data=np.array([0.01]),
                )
                h5["mixtures/fuel"].create_dataset(
                    "total_std_dev",
                    data=np.array([0.001, 0.14]),
                )

            report = validator.validate_input(
                path,
                require_adf=False,
                require_transport_dataset=False,
                require_volume=False,
                expected_adf_faces=None,
                uncertainty=validator.UncertaintyConfig(fail_threshold=0.1),
            )

        self.assertFalse(report.ok)
        self.assertTrue(any("absorption_std_dev shape" in item for item in report.issues))
        self.assertTrue(any("exceeds fail threshold" in item for item in report.issues))

    def test_uncertainty_production_fail_ignores_higher_scatter_moments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "p1_uncertain.h5"
            scatter = np.array(
                [
                    [[0.2, 0.04], [0.01, 0.3]],
                    [[0.01, 0.02], [0.03, 0.01]],
                ]
            )
            write_single_state_fixture(
                path,
                total=[0.5, 0.7],
                legendre_order=1,
                scatter=scatter,
            )
            with h5py.File(path, "a") as h5:
                std = np.zeros((2, 2, 2), dtype=float)
                std[0] = np.array([[0.0005, 0.0005], [0.0005, 0.0005]])
                std[1, 1, 1] = 0.5
                h5["mixtures/fuel"].create_dataset("scatter_matrix_std_dev", data=std)

            report = validator.validate_input(
                path,
                uncertainty=validator.UncertaintyConfig(
                    warn_threshold=0.05,
                    production_fail_threshold=0.1,
                ),
            )

        self.assertTrue(report.ok, report.issues)
        self.assertGreater(report.uncertainty_max_rel or 0.0, 10.0)
        self.assertLess(report.uncertainty_production_max_rel or 1.0, 0.1)
        self.assertIn("moment=1", report.uncertainty_worst or "")
        self.assertNotIn("moment=1", report.uncertainty_production_worst or "")
        self.assertTrue(any("statistical uncertainty" in item for item in report.warnings))

    def test_uncertainty_production_fail_gates_primary_xs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "primary_uncertain.h5"
            write_single_state_fixture(path, total=[0.5, 0.7])
            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].create_dataset(
                    "total_std_dev",
                    data=np.array([0.001, 0.14]),
                )

            report = validator.validate_input(
                path,
                uncertainty=validator.UncertaintyConfig(
                    warn_threshold=0.05,
                    production_fail_threshold=0.1,
                ),
            )

        self.assertFalse(report.ok)
        self.assertAlmostEqual(report.uncertainty_production_max_rel or 0.0, 0.2)
        self.assertTrue(
            any("exceeds production fail threshold" in item for item in report.issues)
        )

    def test_production_uncertainty_warns_when_std_dev_coverage_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing_std_dev.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])

            report = validator.validate_input(
                path,
                uncertainty=validator.UncertaintyConfig(
                    warn_threshold=0.05,
                    production_fail_threshold=1.0,
                ),
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.uncertainty_expected_datasets, 7)
        self.assertEqual(report.uncertainty_datasets, 0)
        self.assertTrue(
            any("std_dev coverage incomplete" in item for item in report.warnings)
        )

    def test_uncertainty_can_require_full_std_dev_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing_required_std_dev.h5"
            write_single_state_fixture(path, total=[0.29, 0.38])

            report = validator.validate_input(
                path,
                uncertainty=validator.UncertaintyConfig(
                    warn_threshold=None,
                    require_coverage=True,
                ),
            )

        self.assertFalse(report.ok)
        self.assertEqual(report.uncertainty_expected_datasets, 7)
        self.assertEqual(report.uncertainty_datasets, 0)
        self.assertTrue(
            any("std_dev coverage incomplete" in item for item in report.issues)
        )

    def test_uncertainty_coverage_ignores_synthetic_nonfission_placeholders(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "moderator_std_dev.h5"
            write_nonfission_zero_std_dev_fixture(path)

            report = validator.validate_input(
                path,
                uncertainty=validator.UncertaintyConfig(
                    warn_threshold=None,
                    require_coverage=True,
                ),
            )

        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.uncertainty_expected_datasets, 4)
        self.assertEqual(report.uncertainty_datasets, 4)


def write_multistate_fixture(
    path: Path,
    *,
    burnup_values: tuple[float, ...] | list[float] | None = (0.0, 10.0),
) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        if burnup_values is not None:
            state_points = h5.create_group("state_points")
            state_points.create_dataset("BURN", data=np.array(burnup_values))

        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["volume"] = 1.0
        states = fuel.create_group("states")
        for index, total in enumerate(([0.5, 0.7], [0.8, 0.9]), start=1):
            state = states.create_group(f"{index:08d}")
            write_one_state_payload(state, total=total, fissionable=True)


def write_single_state_fixture(
    path: Path,
    *,
    total: list[float],
    legendre_order: int = 0,
    scatter_axes: str = "moment,from,to",
    scatter: np.ndarray | None = None,
) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = legendre_order
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = scatter_axes
        fuel.attrs["volume"] = 1.0
        write_one_state_payload(
            fuel,
            total=total,
            fissionable=True,
            scatter_axes=scatter_axes,
            scatter=scatter,
        )


def write_known_mesh_fixture(path: Path, *, mesh_id: str) -> None:
    mesh = load_energy_mesh(mesh_id)
    bounds = mesh.boundaries_descending[::-1]
    ngroups = mesh.n_groups
    total = np.linspace(0.2, 0.8, ngroups)
    absorption = np.linspace(0.02, 0.08, ngroups)
    scatter = np.zeros((1, ngroups, ngroups))
    scatter[0, np.arange(ngroups), np.arange(ngroups)] = total - absorption

    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = ngroups
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=bounds)
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["volume"] = 1.0
        fuel.create_dataset("total", data=total)
        fuel.create_dataset("absorption", data=absorption)
        fuel.create_dataset("fission", data=np.linspace(0.01, 0.02, ngroups))
        fuel.create_dataset("nu_fission", data=np.linspace(0.025, 0.05, ngroups))
        chi = np.zeros(ngroups)
        chi[0] = 1.0
        fuel.create_dataset("chi", data=chi)
        fuel.create_dataset("transport_total", data=total)
        fuel.create_dataset("scatter_matrix", data=scatter)


def write_one_state_payload(
    group: h5py.Group,
    *,
    total: list[float],
    fissionable: bool,
    scatter_axes: str = "moment,from,to",
    scatter: np.ndarray | None = None,
) -> None:
    group.attrs["fissionable"] = fissionable
    group.attrs["scatter_axes"] = scatter_axes
    group.attrs["volume"] = 1.0
    group.create_dataset("total", data=np.array(total))
    group.create_dataset("absorption", data=np.array([0.05, 0.08]))
    group.create_dataset("fission", data=np.array([0.01, 0.015]))
    group.create_dataset("nu_fission", data=np.array([0.025, 0.03]))
    group.create_dataset("chi", data=np.array([1.0, 0.0]))
    group.create_dataset("transport_total", data=np.array(total))
    group.create_dataset(
        "scatter_matrix",
        data=(
            np.array([[[0.2, 0.04], [0.0, 0.3]]])
            if scatter is None
            else scatter
        ),
    )


def write_nonfission_zero_std_dev_fixture(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        moderator = mixtures.create_group("moderator")
        moderator.attrs["fissionable"] = False
        moderator.attrs["scatter_axes"] = "moment,from,to"
        moderator.attrs["volume"] = 1.0
        moderator.create_dataset("total", data=np.array([0.29, 0.38]))
        moderator.create_dataset("absorption", data=np.array([0.05, 0.08]))
        moderator.create_dataset("fission", data=np.zeros(2))
        moderator.create_dataset("nu_fission", data=np.zeros(2))
        moderator.create_dataset("chi", data=np.zeros(2))
        moderator.create_dataset("transport_total", data=np.array([0.29, 0.38]))
        moderator.create_dataset(
            "scatter_matrix",
            data=np.array([[[0.2, 0.04], [0.0, 0.3]]]),
        )
        moderator.create_dataset("total_std_dev", data=np.zeros(2))
        moderator.create_dataset("absorption_std_dev", data=np.zeros(2))
        moderator.create_dataset("transport_total_std_dev", data=np.zeros(2))
        moderator.create_dataset(
            "scatter_matrix_std_dev",
            data=np.zeros((1, 2, 2)),
        )


def append_openmc_volume_flux(
    path: Path,
    *,
    values: np.ndarray | None = None,
    std_dev: np.ndarray | None = None,
    group_order: str = "mgxs_donjon",
    mixture_names: tuple[str, ...] = ("fuel",),
) -> None:
    with h5py.File(path, "a") as h5:
        dataset = h5.create_dataset(
            "openmc_volume_flux",
            data=np.array([[10.0, 20.0]]) if values is None else values,
        )
        dataset.attrs["group_order"] = group_order
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        dataset.attrs["source_group_order"] = "unit_test"
        if std_dev is not None:
            std_dataset = h5.create_dataset("openmc_volume_flux_std_dev", data=std_dev)
            std_dataset.attrs["group_order"] = group_order
            std_dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
            std_dataset.attrs["source_group_order"] = "unit_test"


def append_production_metadata(path: Path) -> None:
    with h5py.File(path, "a") as h5:
        h5.attrs["domain_mode"] = "assembly"
        h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
        fuel = h5["mixtures/fuel"]
        fuel.attrs["source_domain_index"] = 1
        fuel.attrs["source_domain_id"] = 101
        fuel.attrs["source_domain_type"] = "cell"
        fuel.create_dataset("kappa_fission", data=np.array([3.2e-12, 3.1e-12]))


if __name__ == "__main__":
    unittest.main()
