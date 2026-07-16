from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.mixture_collapse import collapse_components


class MixtureCollapseTests(unittest.TestCase):
    def test_preserves_vector_and_scatter_reaction_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.h5"
            output = Path(tmp) / "components.h5"
            _write_source(source)

            collapse_components(
                source,
                output,
                groups=(("CENTER", ("A",)), ("RING", ("B", "C"))),
            )

            with h5py.File(source, "r") as original, h5py.File(output, "r") as collapsed:
                flux = np.asarray(original["openmc_volume_flux"])[1:]
                total = np.stack(
                    [np.asarray(original["mixtures"][name]["total"]) for name in ("B", "C")]
                )
                scatter = np.stack(
                    [
                        np.asarray(original["mixtures"][name]["scatter_matrix"])
                        for name in ("B", "C")
                    ]
                )
                ring_flux = np.asarray(collapsed["openmc_volume_flux"])[1]
                ring = collapsed["mixtures"]["RING"]

                np.testing.assert_allclose(ring_flux, flux.sum(axis=0))
                np.testing.assert_allclose(
                    np.asarray(ring["total"]) * ring_flux,
                    np.sum(total * flux, axis=0),
                )
                np.testing.assert_allclose(
                    np.asarray(ring["scatter_matrix"])[0] * ring_flux[:, np.newaxis],
                    np.sum(scatter[:, 0] * flux[:, :, np.newaxis], axis=0),
                )
                expected_total_std = np.sum(0.01 * total * flux, axis=0) / ring_flux
                np.testing.assert_allclose(
                    np.asarray(ring["total_std_dev"]),
                    expected_total_std,
                )
                self.assertIn("scatter_matrix_std_dev", ring)
                self.assertIn("chi_std_dev", ring)
                self.assertEqual(
                    ring["total_std_dev"].attrs["component_uncertainty_method"],
                    "conservative-l1-source-xs-bound-no-covariance",
                )
                self.assertEqual(float(ring.attrs["volume"]), 5.0)
                self.assertEqual(tuple(collapsed["mixture_names"].asstr()[:]), ("CENTER", "RING"))

    def test_requires_exact_source_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.h5"
            _write_source(source)
            with self.assertRaisesRegex(ValueError, "exactly once"):
                collapse_components(
                    source,
                    Path(tmp) / "bad.h5",
                    groups=(("ONLY", ("A", "B")),),
                )


def _write_source(path: Path) -> None:
    names = ("A", "B", "C")
    flux = np.asarray([[1.0, 2.0], [2.0, 4.0], [3.0, 5.0]])
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0, 1.0e7])
        h5.create_dataset("mixture_names", data=np.asarray(names, dtype="S"))
        flux_ds = h5.create_dataset("openmc_volume_flux", data=flux)
        flux_ds.attrs["mixture_names"] = np.asarray(names, dtype="S")
        flux_std = h5.create_dataset("openmc_volume_flux_std_dev", data=0.1 * flux)
        flux_std.attrs["mixture_names"] = np.asarray(names, dtype="S")
        mixtures = h5.create_group("mixtures")
        for index, name in enumerate(names):
            group = mixtures.create_group(name)
            group.attrs["volume"] = float(index + 1)
            group.attrs["source_domain_index"] = index + 1
            group.attrs["fissionable"] = True
            total = np.asarray([1.0 + index, 2.0 + index])
            for dataset in (
                "total",
                "transport_total",
                "absorption",
                "fission",
                "nu_fission",
                "kappa_fission",
            ):
                group.create_dataset(dataset, data=total)
                group.create_dataset(f"{dataset}_std_dev", data=0.01 * total)
            group.create_dataset("chi", data=[1.0, 0.0])
            group.create_dataset("chi_std_dev", data=[0.01, 0.0])
            group.create_dataset(
                "scatter_matrix",
                data=[[[0.1 + index, 0.2], [0.0, 0.3 + index]]],
            )
            group.create_dataset(
                "scatter_matrix_std_dev",
                data=[[[0.01, 0.01], [0.0, 0.01]]],
            )
