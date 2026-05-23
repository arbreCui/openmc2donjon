from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.constants import MGXS_DONJON_GROUP_ORDER
from openmc2donjon.openmc_volume_flux import (
    DATASET_NAME,
    DEFAULT_SOURCE_GROUP_ORDER,
    SCHEMA,
    STD_DEV_DATASET_NAME,
    reverse_openmc_energy_filter_flux,
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


if __name__ == "__main__":
    unittest.main()
