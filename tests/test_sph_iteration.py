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
            self.assertEqual(
                payload["formula"],
                "next_sph = previous_sph * "
                "(reference_flux / normalized_low_order_flux) ** damping",
            )
            self.assertEqual(payload["flux_normalization"], "none")
            self.assertEqual(payload["normalization_factor"], 1.0)
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["clipped_count"], 0)
            self.assertEqual(payload["clipped_bins"], [])
            self.assertEqual(payload["diagnostic_bin_limit"], 10)
            worst = payload["worst_residual_bins"][0]
            self.assertEqual(worst["mixture"], "moderator")
            self.assertEqual(worst["group"], 2)
            self.assertAlmostEqual(worst["raw_update"], 1.44)
            self.assertAlmostEqual(worst["residual"], 0.44)

    def test_power_normalization_scales_low_order_flux_with_h_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.csv"
            table = root / "next_sph.csv"
            summary = root / "summary.json"
            write_mgxs(
                mgxs,
                h_factor={
                    "fuel": np.asarray([10.0, 100.0]),
                    "moderator": np.asarray([1.0, 1.0]),
                },
            )
            reference_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,10.0\nfuel,2,20.0\n"
                "moderator,1,30.0\nmoderator,2,40.0\n",
                encoding="utf-8",
            )
            low_order_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,1.0\nfuel,2,1.0\n"
                "moderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            report = create_sph_update_table(
                mgxs,
                table,
                reference_flux=reference_flux,
                low_order_flux=low_order_flux,
                flux_normalization="power",
                summary_json=summary,
            )

            factor = (10.0 * 10.0 + 20.0 * 100.0 + 30.0 + 40.0) / (10.0 + 100.0 + 1.0 + 1.0)
            expected = np.asarray([[10.0 / factor, 20.0 / factor], [30.0 / factor, 40.0 / factor]])
            self.assertAlmostEqual(report.normalization_factor, factor)
            self.assertEqual(report.flux_normalization, "power")
            rows = table.read_text(encoding="utf-8").strip().splitlines()[1:]
            actual = np.asarray([float(row.split(",")[2]) for row in rows]).reshape(2, 2)
            np.testing.assert_allclose(actual, expected, rtol=1.0e-11)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["flux_normalization"], "power")
            self.assertAlmostEqual(payload["normalization_factor"], factor)
            self.assertEqual(payload["normalization_weight_source"], "H-FACTOR/kappa_fission")
            self.assertAlmostEqual(payload["reference_normalization_integral"], 2170.0)
            self.assertAlmostEqual(payload["low_order_normalization_integral"], 112.0)

    def test_power_normalization_requires_h_factor(self) -> None:
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
                "mixture,group,flux\nfuel,1,1.0\nfuel,2,1.0\nmoderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "requires group-wise H-FACTOR"):
                create_sph_update_table(
                    mgxs,
                    table,
                    reference_flux=reference_flux,
                    low_order_flux=low_order_flux,
                    flux_normalization="power",
                )

    def test_power_normalization_allows_missing_nonfissionable_h_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.csv"
            table = root / "next_sph.csv"
            write_mgxs(
                mgxs,
                h_factor={
                    "fuel": np.asarray([10.0, 100.0]),
                },
            )
            reference_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,10.0\nfuel,2,20.0\n"
                "moderator,1,30.0\nmoderator,2,40.0\n",
                encoding="utf-8",
            )
            low_order_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,1.0\nfuel,2,1.0\n"
                "moderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            report = create_sph_update_table(
                mgxs,
                table,
                reference_flux=reference_flux,
                low_order_flux=low_order_flux,
                flux_normalization="power",
            )

            factor = (10.0 * 10.0 + 20.0 * 100.0) / (10.0 + 100.0)
            expected = np.asarray(
                [
                    [10.0 / factor, 20.0 / factor],
                    [30.0 / factor, 40.0 / factor],
                ]
            )
            self.assertAlmostEqual(report.normalization_factor, factor)
            self.assertAlmostEqual(report.reference_normalization_integral, 2100.0)
            self.assertAlmostEqual(report.low_order_normalization_integral, 110.0)
            rows = table.read_text(encoding="utf-8").strip().splitlines()[1:]
            actual = np.asarray([float(row.split(",")[2]) for row in rows]).reshape(2, 2)
            np.testing.assert_allclose(actual, expected, rtol=1.0e-11)

    def test_auto_normalization_resolves_to_power_when_h_factor_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.csv"
            table = root / "next_sph.csv"
            summary = root / "summary.json"
            write_mgxs(
                mgxs,
                h_factor={
                    "fuel": np.asarray([10.0, 100.0]),
                    "moderator": np.asarray([1.0, 1.0]),
                },
            )
            reference_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,10.0\nfuel,2,20.0\n"
                "moderator,1,30.0\nmoderator,2,40.0\n",
                encoding="utf-8",
            )
            low_order_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,1.0\nfuel,2,1.0\n"
                "moderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            report = create_sph_update_table(
                mgxs,
                table,
                reference_flux=reference_flux,
                low_order_flux=low_order_flux,
                flux_normalization="auto",
                summary_json=summary,
            )

            self.assertEqual(report.flux_normalization, "power")
            self.assertEqual(
                report.normalization_weight_source,
                "H-FACTOR/kappa_fission (auto)",
            )
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["flux_normalization"], "power")
            self.assertEqual(
                payload["normalization_weight_source"],
                "H-FACTOR/kappa_fission (auto)",
            )

    def test_auto_normalization_requires_h_factor(self) -> None:
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
                "mixture,group,flux\nfuel,1,1.0\nfuel,2,1.0\nmoderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "auto flux normalization requires"):
                create_sph_update_table(
                    mgxs,
                    table,
                    reference_flux=reference_flux,
                    low_order_flux=low_order_flux,
                    flux_normalization="auto",
                )

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

    def test_rejects_hdf5_flux_with_wrong_group_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.h5"
            table = root / "next_sph.csv"
            write_mgxs(mgxs)
            reference_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,1.0\nfuel,2,1.0\n"
                "moderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )
            with h5py.File(low_order_flux, "w") as h5:
                dataset = h5.create_dataset(
                    "low_order_flux",
                    data=np.asarray([[1.0, 1.0], [1.0, 1.0]]),
                )
                dataset.attrs["mixture_names"] = np.asarray(
                    ("fuel", "moderator"),
                    dtype="S",
                )
                dataset.attrs["group_order"] = "ascending_energy"

            with self.assertRaisesRegex(
                ValueError,
                "low-order flux: group_order must be 'mgxs_donjon'",
            ):
                create_sph_update_table(
                    mgxs,
                    table,
                    reference_flux=reference_flux,
                    low_order_flux=f"{low_order_flux}::low_order_flux",
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

    def test_summary_records_clipped_bins(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.csv"
            table = root / "next_sph.csv"
            summary = root / "summary.json"
            write_mgxs(mgxs)
            reference_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,3.0\nfuel,2,1.0\n"
                "moderator,1,1.0\nmoderator,2,2.0\n",
                encoding="utf-8",
            )
            low_order_flux.write_text(
                "mixture,group,flux\n"
                "fuel,1,1.0\nfuel,2,1.0\n"
                "moderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

            report = create_sph_update_table(
                mgxs,
                table,
                reference_flux=reference_flux,
                low_order_flux=low_order_flux,
                clip_max=1.5,
                summary_json=summary,
            )

            self.assertEqual(report.clipped_count, 2)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["clipped_count"], 2)
            clipped = payload["clipped_bins"][0]
            self.assertEqual(clipped["mixture"], "fuel")
            self.assertEqual(clipped["group"], 1)
            self.assertAlmostEqual(clipped["unclipped_sph"], 3.0)
            self.assertAlmostEqual(clipped["sph"], 1.5)
            self.assertTrue(clipped["clipped"])

    def test_cli_accepts_previous_sph_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            previous = root / "previous_sph.h5"
            reference_flux = root / "reference_flux.csv"
            low_order_flux = root / "low_order_flux.csv"
            table = root / "next_sph.csv"
            write_mgxs(mgxs)
            with h5py.File(previous, "w") as h5:
                dataset = h5.create_dataset(
                    "sph",
                    data=np.asarray([[1.1, 1.2], [0.9, 1.0]]),
                )
                dataset.attrs["mixture_names"] = np.asarray(("fuel", "moderator"), dtype="S")
            reference_flux.write_text(
                "mixture,group,flux\nfuel,1,4.0\nfuel,2,9.0\nmoderator,1,16.0\nmoderator,2,25.0\n",
                encoding="utf-8",
            )
            low_order_flux.write_text(
                "mixture,group,flux\nfuel,1,1.0\nfuel,2,1.0\nmoderator,1,1.0\nmoderator,2,1.0\n",
                encoding="utf-8",
            )

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
                        str(low_order_flux),
                        "--previous-sph",
                        str(previous),
                        "--damping",
                        "0.5",
                    ]
                ),
                0,
            )

            rows = table.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(rows[0], "mixture,group,sph")
            self.assertIn("fuel,1,2.2", rows)
            self.assertIn("fuel,2,3.6", rows)
            self.assertIn("moderator,1,3.6", rows)
            self.assertIn("moderator,2,5", rows)


def write_mgxs(path: Path, *, h_factor: dict[str, np.ndarray] | None = None) -> None:
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
            if h_factor and name in h_factor:
                group.create_dataset("kappa_fission", data=np.asarray(h_factor[name], dtype=float))


if __name__ == "__main__":
    unittest.main()
