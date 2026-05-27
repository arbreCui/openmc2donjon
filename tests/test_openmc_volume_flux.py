from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

import h5py
import numpy as np

from openmc2donjon.constants import MGXS_DONJON_GROUP_ORDER
from openmc2donjon.openmc_volume_flux import (
    DATASET_NAME,
    DEFAULT_SOURCE_GROUP_ORDER,
    SCHEMA,
    STD_DEV_DATASET_NAME,
    export_openmc_volume_flux,
    reverse_openmc_energy_filter_flux,
    write_openmc_flux_hdf5,
    write_openmc_volume_flux_hdf5,
)


class OpenMCVolumeFluxTests(unittest.TestCase):
    def test_reverses_openmc_energy_filter_order(self) -> None:
        raw = np.array(
            [
                [[1.0], [2.0], [3.0]],
                [[4.0], [5.0], [6.0]],
            ]
        )

        values = reverse_openmc_energy_filter_flux(
            raw,
            mixture_count=2,
            energy_groups=3,
        )

        np.testing.assert_allclose(values, [[3.0, 2.0, 1.0], [6.0, 5.0, 4.0]])

    def test_writes_canonical_openmc_volume_flux_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            flux = np.array([[10.0, 20.0], [30.0, 40.0]])
            std_dev = np.array([[0.1, 0.2], [0.3, 0.4]])

            report = write_openmc_volume_flux_hdf5(
                path,
                flux,
                mixture_names=("ASM_A", "ASM_B"),
                std_dev=std_dev,
            )

            with h5py.File(path, "r") as h5:
                dataset = h5[DATASET_NAME]
                values = dataset[:]
                attrs = dict(dataset.attrs)
                std_dataset = h5[STD_DEV_DATASET_NAME]
                std_values = std_dataset[:]
                std_attrs = dict(std_dataset.attrs)

        self.assertEqual(report.dataset, DATASET_NAME)
        self.assertEqual(report.std_dev_dataset, STD_DEV_DATASET_NAME)
        self.assertEqual(report.mixture_names, ("ASM_A", "ASM_B"))
        self.assertEqual(report.energy_groups, 2)
        self.assertEqual(report.minimum, 10.0)
        self.assertEqual(report.maximum, 40.0)
        self.assertAlmostEqual(report.max_relative_std_dev or 0.0, 0.01)
        np.testing.assert_allclose(values, flux)
        np.testing.assert_allclose(std_values, std_dev)
        self.assertEqual(attrs["schema"], SCHEMA)
        self.assertEqual(attrs["group_order"], MGXS_DONJON_GROUP_ORDER)
        self.assertEqual(attrs["source_group_order"], DEFAULT_SOURCE_GROUP_ORDER)
        self.assertEqual(attrs["layout"], "[mixture, group]")
        self.assertEqual(
            tuple(_decode(value) for value in attrs["mixture_names"]),
            ("ASM_A", "ASM_B"),
        )
        self.assertEqual(std_attrs["schema"], SCHEMA)
        self.assertEqual(std_attrs["group_order"], MGXS_DONJON_GROUP_ORDER)
        self.assertEqual(std_attrs["source_group_order"], DEFAULT_SOURCE_GROUP_ORDER)

    def test_writes_custom_openmc_flux_dataset_for_mg_macro_flux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mg_flux.h5"
            flux = np.array([[1.0, 2.0], [3.0, 4.0]])

            report = write_openmc_flux_hdf5(
                path,
                flux,
                mixture_names=("FUEL", "MOD"),
                dataset_name="openmc_mg_flux",
                std_dev_dataset_name="openmc_mg_flux_std_dev",
            )

            with h5py.File(path, "r") as h5:
                dataset = h5["openmc_mg_flux"]
                values = dataset[:]
                attrs = dict(dataset.attrs)

        self.assertEqual(report.dataset, "openmc_mg_flux")
        self.assertIsNone(report.std_dev_dataset)
        np.testing.assert_allclose(values, flux)
        self.assertEqual(attrs["group_order"], MGXS_DONJON_GROUP_ORDER)
        self.assertEqual(
            tuple(_decode(value) for value in attrs["mixture_names"]),
            ("FUEL", "MOD"),
        )

    def test_exports_statepoint_tally_to_openmc_flux_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.10.h5"
            statepoint.write_bytes(b"fake")
            mgxs = tmp / "mgxs.h5"
            output = tmp / "ce_flux.h5"
            summary = tmp / "ce_flux_summary.json"
            _write_mgxs_metadata(mgxs)
            fake_openmc = _fake_openmc_module(
                mean=np.array([[1.0], [2.0], [3.0], [4.0]]),
                std_dev=np.array([[0.1], [0.2], [0.3], [0.4]]),
            )

            stream = io.StringIO()
            with _patched_openmc(fake_openmc), contextlib.redirect_stdout(stream):
                report = export_openmc_volume_flux(
                    statepoint,
                    output,
                    mgxs_h5=mgxs,
                    tally_name="ce_flux",
                    dataset_name="openmc_ce_flux",
                    summary_json=summary,
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(output, "r") as h5:
                values = h5["openmc_ce_flux"][:]
                std_values = h5["openmc_ce_flux_std_dev"][:]
                attrs = dict(h5["openmc_ce_flux"].attrs)

        self.assertEqual(report.dataset, "openmc_ce_flux")
        self.assertEqual(report.std_dev_dataset, "openmc_ce_flux_std_dev")
        self.assertEqual(report.statepoint, statepoint)
        self.assertEqual(report.tally_name, "ce_flux")
        self.assertIn("openmc2donjon_volume_flux_export_passed", stream.getvalue())
        np.testing.assert_allclose(values, [[2.0, 1.0], [4.0, 3.0]])
        np.testing.assert_allclose(std_values, [[0.2, 0.1], [0.4, 0.3]])
        self.assertEqual(attrs["group_order"], MGXS_DONJON_GROUP_ORDER)
        self.assertEqual(payload["decision"], "openmc2donjon_volume_flux_export_passed")
        self.assertEqual(payload["dataset"], "openmc_ce_flux")
        self.assertEqual(payload["tally_name"], "ce_flux")

    def test_rejects_nonpositive_or_mismatched_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"

            with self.assertRaisesRegex(ValueError, "must be positive"):
                write_openmc_volume_flux_hdf5(
                    path,
                    [[1.0, 0.0]],
                    mixture_names=("ASM_A",),
                )

            with self.assertRaisesRegex(ValueError, "mixture axis"):
                write_openmc_volume_flux_hdf5(
                    path,
                    [[1.0, 2.0]],
                    mixture_names=("ASM_A", "ASM_B"),
                )

            with self.assertRaisesRegex(ValueError, "non-negative"):
                write_openmc_volume_flux_hdf5(
                    path,
                    [[1.0, 2.0]],
                    mixture_names=("ASM_A",),
                    std_dev=[[0.0, -0.1]],
                )


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _write_mgxs_metadata(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        h5.create_dataset("mixture_names", data=np.asarray(("FUEL", "MOD"), dtype="S"))
        mixtures = h5.create_group("mixtures")
        mixtures.create_group("FUEL")
        mixtures.create_group("MOD")


def _fake_openmc_module(*, mean: np.ndarray, std_dev: np.ndarray):
    class FakeTally:
        def get_values(self, *, scores=None, value: str = "mean"):
            if scores != ["flux"]:
                raise AssertionError(f"unexpected scores: {scores!r}")
            if value == "mean":
                return mean
            if value == "std_dev":
                return std_dev
            raise AssertionError(f"unexpected value selector: {value!r}")

    class FakeStatePoint:
        def __init__(self, path: str) -> None:
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def get_tally(self, *, name: str):
            if name != "ce_flux":
                raise AssertionError(f"unexpected tally name: {name!r}")
            return FakeTally()

    return types.SimpleNamespace(StatePoint=FakeStatePoint)


@contextlib.contextmanager
def _patched_openmc(fake_openmc):
    previous = sys.modules.get("openmc")
    sys.modules["openmc"] = fake_openmc
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop("openmc", None)
        else:
            sys.modules["openmc"] = previous


if __name__ == "__main__":
    unittest.main()
