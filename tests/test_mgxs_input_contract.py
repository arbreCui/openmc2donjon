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


def write_one_state_payload(
    group: h5py.Group,
    *,
    total: list[float],
    fissionable: bool,
) -> None:
    group.attrs["fissionable"] = fissionable
    group.attrs["scatter_axes"] = "moment,from,to"
    group.attrs["volume"] = 1.0
    group.create_dataset("total", data=np.array(total))
    group.create_dataset("absorption", data=np.array([0.05, 0.08]))
    group.create_dataset("fission", data=np.array([0.01, 0.015]))
    group.create_dataset("nu_fission", data=np.array([0.025, 0.03]))
    group.create_dataset("chi", data=np.array([1.0, 0.0]))
    group.create_dataset("transport_total", data=np.array(total))
    group.create_dataset(
        "scatter_matrix",
        data=np.array([[[0.2, 0.04], [0.0, 0.3]]]),
    )


if __name__ == "__main__":
    unittest.main()
