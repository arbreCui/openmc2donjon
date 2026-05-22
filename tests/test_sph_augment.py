from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon import mgxs_input_contract as validator
from openmc2donjon.cli import main as cli_main
from openmc2donjon.macrolib import extract_sph_from_macrolib_ascii, read_macrolib_ascii
from openmc2donjon.sph_augment import augment_hdf5_with_sph, create_table_sph_sidecar


class SphAugmentTests(unittest.TestCase):
    def test_cli_creates_augments_and_converts_sph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            sidecar = root / "sph.h5"
            augmented = root / "with_sph.h5"
            macrolib = root / "out.macrolib.txt"
            extracted_sidecar = root / "sph_from_macrolib.h5"
            extracted_summary = root / "sph_from_macrolib.summary.json"
            write_mgxs_fixture(mgxs)

            self.assertEqual(
                cli_main(
                    [
                        "make-sph-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--value",
                        "1.25",
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        "augment-sph",
                        str(mgxs),
                        "--sph-source",
                        str(sidecar),
                        "-o",
                        str(augmented),
                        "--sph-real",
                        "false",
                        "--sph-applied",
                        "false",
                    ]
                ),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        str(augmented),
                        "--format",
                        "macrolib",
                        "-o",
                        str(macrolib),
                        "--check",
                        "--require-sph",
                    ]
                ),
                0,
            )

            with h5py.File(sidecar, "r") as h5:
                self.assertEqual(h5.attrs["schema"], "openmc2donjon.sph-sidecar.v1")
                np.testing.assert_allclose(h5["sph"][:], np.full((2, 2), 1.25))
                self.assertEqual(h5["sph"].attrs["group_order"], "mgxs_donjon")
            with h5py.File(augmented, "r") as h5:
                self.assertEqual(h5.attrs["sph_kind"], "unity")
                self.assertFalse(bool(h5.attrs["sph_real"]))
                self.assertFalse(bool(h5.attrs["sph_applied"]))
                np.testing.assert_allclose(h5["mixtures/fuel/sph"][:], [1.25, 1.25])
                np.testing.assert_allclose(h5["mixtures/moderator/sph"][:], [1.25, 1.25])

            parsed = read_macrolib_ascii(macrolib)
            self.assertEqual(parsed.state_vector[13], 1)
            np.testing.assert_allclose(parsed.sph, np.full((2, 2), 1.25))

            self.assertEqual(
                cli_main(
                    [
                        "make-sph-sidecar",
                        str(mgxs),
                        "-o",
                        str(extracted_sidecar),
                        "--mode",
                        "macrolib",
                        "--macrolib",
                        str(macrolib),
                        "--summary-json",
                        str(extracted_summary),
                    ]
                ),
                0,
            )
            with h5py.File(extracted_sidecar, "r") as h5:
                self.assertEqual(h5.attrs["sph_kind"], "macrolib-nsph")
                self.assertTrue(bool(h5.attrs["sph_real"]))
                self.assertEqual(h5.attrs["source_macrolib"], str(macrolib))
                np.testing.assert_allclose(h5["sph"][:], np.full((2, 2), 1.25))
                self.assertEqual(h5["sph"].attrs["group_order"], "mgxs_donjon")
            self.assertIn(
                "openmc2donjon_sph_sidecar_passed",
                extracted_summary.read_text(encoding="utf-8"),
            )
            self.assertIn("mgxs_donjon", extracted_summary.read_text(encoding="utf-8"))

    def test_check_rejects_partial_sph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "partial.h5"
            write_mgxs_fixture(path)
            with h5py.File(path, "a") as h5:
                h5["mixtures/fuel"].create_dataset("sph", data=np.array([1.0, 1.0]))

            report = validator.validate_input(path, require_sph=True)

        self.assertFalse(report.ok)
        self.assertTrue(any("SPH data" in issue for issue in report.issues))

    def test_extracts_sph_from_dragon_macrolib_without_energy_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = root / "dragon_sph.macrolib.txt"
            sidecar = root / "sph_from_dragon.h5"
            write_mgxs_fixture(mgxs)
            write_dragon_sph_macrolib_fixture(macrolib)

            values = extract_sph_from_macrolib_ascii(macrolib)
            np.testing.assert_allclose(values, [[1.10, 0.90], [0.95, 1.05]])

            self.assertEqual(
                cli_main(
                    [
                        "make-sph-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "macrolib",
                        "--macrolib",
                        str(macrolib),
                    ]
                ),
                0,
            )
            with h5py.File(sidecar, "r") as h5:
                self.assertEqual(h5.attrs["sph_kind"], "macrolib-nsph")
                np.testing.assert_allclose(h5["sph"][:], values)

    def test_cli_creates_sph_sidecar_from_external_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            long_table = root / "sph_long.csv"
            wide_table = root / "sph_wide.csv"
            long_sidecar = root / "sph_long.h5"
            wide_sidecar = root / "sph_wide.h5"
            summary = root / "sph_table.summary.json"
            write_mgxs_fixture(mgxs)
            long_table.write_text(
                "\n".join(
                    [
                        "mixture,group,sph",
                        "moderator,2,1.05",
                        "fuel,1,1.10",
                        "moderator,1,0.95",
                        "fuel,2,0.90",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            wide_table.write_text(
                "mixture,g1,g2\nfuel,1.10,0.90\nmoderator,0.95,1.05\n",
                encoding="utf-8",
            )

            self.assertEqual(
                cli_main(
                    [
                        "make-sph-sidecar",
                        str(mgxs),
                        "-o",
                        str(long_sidecar),
                        "--mode",
                        "table",
                        "--table",
                        str(long_table),
                        "--sph-kind",
                        "external-sph",
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
                        str(wide_sidecar),
                        "--mode",
                        "table",
                        "--table",
                        str(wide_table),
                    ]
                ),
                0,
            )

            expected = np.array([[1.10, 0.90], [0.95, 1.05]])
            for path in (long_sidecar, wide_sidecar):
                with h5py.File(path, "r") as h5:
                    np.testing.assert_allclose(h5["sph"][:], expected)
                    self.assertEqual(h5["sph"].attrs["group_order"], "mgxs_donjon")
                    expected_source = long_table if path == long_sidecar else wide_table
                    self.assertEqual(h5.attrs["source_table"], str(expected_source))
            with h5py.File(long_sidecar, "r") as h5:
                self.assertEqual(h5.attrs["sph_kind"], "external-sph")
                self.assertTrue(bool(h5.attrs["sph_real"]))
                self.assertFalse(bool(h5.attrs["sph_applied"]))
            self.assertIn("openmc2donjon_sph_sidecar_passed", summary.read_text(encoding="utf-8"))

    def test_external_sph_wide_table_requires_contiguous_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            table = root / "sph_bad.csv"
            sidecar = root / "sph_bad.h5"
            write_mgxs_fixture(mgxs)
            table.write_text(
                "mixture,g2,g3\nfuel,1.10,0.90\nmoderator,0.95,1.05\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "contiguous group columns"):
                create_table_sph_sidecar(
                    input_h5=mgxs,
                    output_h5=sidecar,
                    table=table,
                )

    def test_augment_rejects_sph_sidecar_with_wrong_group_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            sidecar = root / "bad_sph.h5"
            output = root / "with_sph.h5"
            write_mgxs_fixture(mgxs)
            with h5py.File(sidecar, "w") as h5:
                dataset = h5.create_dataset("sph", data=np.ones((2, 2)))
                dataset.attrs["mixture_names"] = np.asarray(
                    ("fuel", "moderator"),
                    dtype="S",
                )
                dataset.attrs["group_order"] = "ascending_energy"

            with self.assertRaisesRegex(
                ValueError,
                "/sph group_order must be 'mgxs_donjon'",
            ):
                augment_hdf5_with_sph(
                    mgxs,
                    sph_source=sidecar,
                    output_h5=output,
                )


def write_mgxs_fixture(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        write_mixture(
            mixtures.create_group("fuel"),
            fissionable=True,
            total=np.array([0.5, 0.8]),
            absorption=np.array([0.1, 0.2]),
            fission=np.array([0.03, 0.04]),
            nu_fission=np.array([0.07, 0.08]),
            chi=np.array([1.0, 0.0]),
        )
        write_mixture(
            mixtures.create_group("moderator"),
            fissionable=False,
            total=np.array([0.3, 0.4]),
            absorption=np.array([0.02, 0.03]),
            fission=np.zeros(2),
            nu_fission=np.zeros(2),
            chi=np.zeros(2),
        )


def write_dragon_sph_macrolib_fixture(path: Path) -> None:
    state = [0] * 40
    state[0] = 2
    state[1] = 2
    state[2] = 1
    state[3] = 1
    state[13] = 1
    blocks = [
        lcm_ascii.block(1, "GROUP", 10, count=2),
        lcm_ascii.list_item(2, 1),
        lcm_ascii.block(3, "NSPH", 2, [1.10, 0.95]),
        lcm_ascii.control(-3),
        lcm_ascii.list_item(2, 2),
        lcm_ascii.block(3, "NSPH", 2, [0.90, 1.05]),
        lcm_ascii.control(-3),
        lcm_ascii.block(1, "STATE-VECTOR", 1, state),
        lcm_ascii.string_block(1, "SIGNATURE", "L_MACROLIB", width=12),
        lcm_ascii.control(-1),
    ]
    lcm_ascii.write_lcm_ascii(blocks, path)


def write_mixture(
    group,
    *,
    fissionable: bool,
    total: np.ndarray,
    absorption: np.ndarray,
    fission: np.ndarray,
    nu_fission: np.ndarray,
    chi: np.ndarray,
) -> None:
    group.attrs["fissionable"] = fissionable
    group.attrs["volume"] = 1.0
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=fission)
    group.create_dataset("nu_fission", data=nu_fission)
    group.create_dataset("chi", data=chi)
    group.create_dataset(
        "scatter_matrix",
        data=np.array(
            [
                [
                    [0.10, 0.05],
                    [0.00, 0.20],
                ]
            ]
        ),
    )
    group.create_dataset("transport_total", data=total)


if __name__ == "__main__":
    unittest.main()
