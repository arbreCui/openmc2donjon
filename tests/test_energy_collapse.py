from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from openmc2donjon.energy_collapse import collapse_energy_groups


class EnergyCollapseTests(unittest.TestCase):
    def test_preserves_vector_and_scattering_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.h5"
            output = Path(tmp) / "collapsed.h5"
            _write_fixture(source)
            collapse_energy_groups(
                source,
                output,
                groups=((1,), (2, 3)),
                energy_group_structure="test-2g",
            )

            with h5py.File(source, "r") as original, h5py.File(output, "r") as collapsed:
                fine_flux = original["openmc_volume_flux"][0]
                coarse_flux = collapsed["openmc_volume_flux"][0]
                fine_abs = original["mixtures/fuel/absorption"][:]
                coarse_abs = collapsed["mixtures/fuel/absorption"][:]
                self.assertAlmostEqual(
                    float(np.dot(fine_abs, fine_flux)),
                    float(np.dot(coarse_abs, coarse_flux)),
                )

                fine_scat = original["mixtures/fuel/scatter_matrix"][0]
                coarse_scat = collapsed["mixtures/fuel/scatter_matrix"][0]
                fine_rates = fine_scat * fine_flux[:, np.newaxis]
                expected = np.asarray(
                    [
                        [fine_rates[0, 0], np.sum(fine_rates[0, 1:])],
                        [np.sum(fine_rates[1:, 0]), np.sum(fine_rates[1:, 1:])],
                    ]
                )
                np.testing.assert_allclose(
                    coarse_scat * coarse_flux[:, np.newaxis], expected
                )
                np.testing.assert_allclose(
                    collapsed["energy_bounds"][:], [1.0e-5, 1.0, 1.0e7]
                )
                np.testing.assert_allclose(
                    collapsed["mixtures/fuel/chi"][:], [0.6, 0.4]
                )
                self.assertEqual(collapsed.attrs["energy_groups"], 2)

    def test_requires_exact_ordered_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.h5"
            _write_fixture(source)
            with self.assertRaisesRegex(ValueError, "cover every"):
                collapse_energy_groups(
                    source,
                    Path(tmp) / "bad.h5",
                    groups=((1,), (3,)),
                )


def _write_fixture(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 3
        h5.attrs["energy_group_count"] = 3
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=[1.0e-5, 0.1, 1.0, 1.0e7])
        h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
        flux = h5.create_dataset("openmc_volume_flux", data=[[2.0, 3.0, 5.0]])
        flux.attrs["group_order"] = "mgxs_donjon"
        flux.attrs["mixture_names"] = np.asarray(["fuel"], dtype="S")
        std = h5.create_dataset("openmc_volume_flux_std_dev", data=[[0.2, 0.3, 0.5]])
        std.attrs["group_order"] = "mgxs_donjon"
        std.attrs["mixture_names"] = np.asarray(["fuel"], dtype="S")
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["volume"] = 1.0
        fuel.create_dataset("total", data=[0.5, 0.6, 0.7])
        fuel.create_dataset("transport_total", data=[0.4, 0.5, 0.6])
        fuel.create_dataset("absorption", data=[0.1, 0.2, 0.4])
        fuel.create_dataset("fission", data=[0.02, 0.03, 0.04])
        fuel.create_dataset("nu_fission", data=[0.05, 0.07, 0.09])
        fuel.create_dataset("kappa_fission", data=[1.0, 2.0, 3.0])
        fuel.create_dataset("chi", data=[0.6, 0.3, 0.1])
        fuel.create_dataset(
            "scatter_matrix",
            data=[[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]],
        )


if __name__ == "__main__":
    unittest.main()
