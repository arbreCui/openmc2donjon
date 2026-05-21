from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main
from openmc2donjon.sph_iteration import create_sph_update_table


class SphIterationTests(unittest.TestCase):
    def test_cli_builds_damped_sph_update_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.h5"
            previous_sph = root / "previous_sph.csv"
            table = root / "next_sph.csv"
            sidecar = root / "next_sph.h5"
            summary = root / "summary.json"
            write_mgxs(mgxs)
            reference_flux.write_text(
                "\n".join(
                    [
                        "mixture,group,reference_flux",
                        "moderator,2,1.44",
                        "fuel,1,1.21",
                        "moderator,1,0.64",
                        "fuel,2,0.81",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            previous_sph.write_text(
                "mixture,g1,g2\nfuel,1.0,1.1\nmoderator,0.9,1.0\n",
                encoding="utf-8",
            )
            with h5py.File(low_order_flux, "w") as h5:
                data = np.array([[1.0, 1.0], [1.0, 1.0]])
                dataset = h5.create_dataset("volume_flux", data=data)
                dataset.attrs["mixture_names"] = np.asarray(("fuel", "moderator"), dtype="S")

            self.assertEqual(
                cli_main(
                    [
                        "make-sph-update-table",
                        str(mgxs),
                        "-o",
                        str(table),
                        "--reference-flux",
                        str(reference_flux),
                        "--low-order-flux",
                        f"{low_order_flux}::volume_flux",
                        "--previous-sph",
                        str(previous_sph),
                        "--damping",
                        "0.5",
                        "--summary-json",
                        str(summary),
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        "make-sph-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "table",
                        "--table",
                        str(table),
                    ]
                ),
                0,
            )

            expected = np.array(
                [
                    [1.0 * np.sqrt(1.21), 1.1 * np.sqrt(0.81)],
                    [0.9 * np.sqrt(0.64), 1.0 * np.sqrt(1.44)],
                ]
            )
            with h5py.File(sidecar, "r") as h5:
                np.testing.assert_allclose(h5["sph"][:], expected)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "openmc2donjon_sph_iteration_table_passed")
            self.assertEqual(payload["formula"], "next_sph = previous_sph * (reference_flux / low_order_flux) ** damping")
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["clipped_count"], 0)

    def test_rejects_nonpositive_low_order_flux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.csv"
            table = root / "next_sph.csv"
            write_mgxs(mgxs)
            reference_flux.write_text(
                "mixture,group,flux\nfuel,1,1.0\nfuel,2,1.0\nmoderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )
            low_order_flux.write_text(
                "mixture,group,flux\nfuel,1,1.0\nfuel,2,0.0\nmoderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "low-order flux values must be positive"):
                create_sph_update_table(
                    mgxs,
                    table,
                    reference_flux=reference_flux,
                    low_order_flux=low_order_flux,
                )

    def test_cli_accepts_mesh_shaped_hdf5_flux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            flux = root / "mesh_flux.h5"
            table = root / "next_sph.csv"
            sidecar = root / "next_sph.h5"
            write_mgxs(mgxs)
            with h5py.File(flux, "w") as h5:
                names = np.asarray([["moderator", "fuel"]], dtype="S")
                h5.create_dataset("mixture_names", data=names)
                h5.create_dataset(
                    "reference_flux",
                    data=np.asarray([[[4.0, 9.0], [16.0, 25.0]]]),
                )
                h5.create_dataset(
                    "low_order_flux",
                    data=np.asarray([[[1.0, 1.0], [1.0, 1.0]]]),
                )

            self.assertEqual(
                cli_main(
                    [
                        "make-sph-update-table",
                        str(mgxs),
                        "-o",
                        str(table),
                        "--reference-flux",
                        f"{flux}::reference_flux",
                        "--low-order-flux",
                        f"{flux}::low_order_flux",
                        "--damping",
                        "0.5",
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        "make-sph-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "table",
                        "--table",
                        str(table),
                    ]
                ),
                0,
            )

            expected = np.asarray([[4.0, 5.0], [2.0, 3.0]])
            with h5py.File(sidecar, "r") as h5:
                np.testing.assert_allclose(h5["sph"][:], expected)


def write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        for name in ("fuel", "moderator"):
            group = mixtures.create_group(name)
            group.attrs["fissionable"] = name == "fuel"
            group.attrs["volume"] = 1.0
            group.create_dataset("total", data=np.ones(2))
            group.create_dataset("absorption", data=np.full(2, 0.1))
            group.create_dataset("fission", data=np.zeros(2))
            group.create_dataset("nu_fission", data=np.zeros(2))
            group.create_dataset("chi", data=np.zeros(2))
            group.create_dataset("scatter_matrix", data=np.zeros((1, 2, 2)))


if __name__ == "__main__":
    unittest.main()
