from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon import mgxs_input_contract as validator


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


if __name__ == "__main__":
    unittest.main()
