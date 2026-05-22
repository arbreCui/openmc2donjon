from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main
from openmc2donjon.sph_loop_scaffold import create_sph_loop_scaffold


class SphLoopScaffoldTests(unittest.TestCase):
    def test_writes_reference_flux_map_and_loop_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs_library.h5"
            reference = root / "openmc_reference.h5"
            solve_template = root / "solve.x2m.in"
            out = root / "sph_inputs"
            _write_mgxs(mgxs)
            _write_reference_h5(reference)
            solve_template.write_text("SEQ_ASCII MAC :: FILE '{macrolib}' ;\n", encoding="utf-8")

            report = create_sph_loop_scaffold(
                mgxs,
                out,
                reference_flux=f"{reference}::openmc_volume_flux",
                solve_template=solve_template,
                scalar_flux_ids={"FUEL": 2, "MOD": 4},
                python_bin="python3",
            )

            self.assertEqual(report.scalar_flux_ids, (2, 4))
            self.assertEqual(report.reference_flux_dataset, "openmc_volume_flux")
            with h5py.File(out / "reference_flux.h5", "r") as h5:
                self.assertEqual(h5.attrs["schema"], "openmc2donjon.reference-flux.v1")
                np.testing.assert_allclose(
                    h5["openmc_volume_flux"][:],
                    [[80.0, 800.0], [120.0, 600.0]],
                )
                np.testing.assert_array_equal(
                    h5["mixture_names"][:],
                    np.asarray(["FUEL", "MOD"], dtype="S"),
                )
            with h5py.File(out / "flux_map.h5", "r") as h5:
                self.assertEqual(h5.attrs["schema"], "openmc2donjon.low-order-flux-map.v1")
                np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])

            config = json.loads((out / "loop_config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["schema"], "openmc2donjon.sph-loop-config.v1")
            self.assertEqual(config["input_h5"], str(mgxs))
            self.assertEqual(config["map_h5"], str(out / "flux_map.h5"))
            self.assertEqual(
                config["reference_flux"],
                f"{out / 'reference_flux.h5'}::openmc_volume_flux",
            )
            self.assertIn(str(solve_template), config["solver"]["command"])

    def test_requires_scalar_flux_map_or_explicit_sequential_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs_library.h5"
            reference = root / "reference.csv"
            solve_template = root / "solve.x2m.in"
            _write_mgxs(mgxs)
            _write_reference_csv(reference)
            solve_template.write_text("dummy {macrolib}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "scalar flux map is required"):
                create_sph_loop_scaffold(
                    mgxs,
                    root / "out",
                    reference_flux=reference,
                    solve_template=solve_template,
                )

    def test_cli_writes_scaffold_from_csv_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs_library.h5"
            reference = root / "reference.csv"
            solve_template = root / "solve.x2m.in"
            out = root / "sph_inputs"
            summary = out / "scaffold_summary.json"
            _write_mgxs(mgxs)
            _write_reference_csv(reference)
            solve_template.write_text("dummy {macrolib}\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "make-sph-loop-scaffold",
                        str(mgxs),
                        "--output-dir",
                        str(out),
                        "--reference-flux",
                        str(reference),
                        "--solve-template",
                        str(solve_template),
                        "--sequential-scalar-flux-map",
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("openmc2donjon_sph_loop_scaffold_passed", stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertTrue(payload["sequential_scalar_flux_map"])
            self.assertEqual(payload["scalar_flux_ids"], [1, 2])
            self.assertTrue(payload["warnings"])
            self.assertTrue((out / "reference_flux.h5").exists())
            self.assertTrue((out / "flux_map.h5").exists())
            self.assertTrue((out / "loop_config.json").exists())


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        mixtures.create_group("FUEL")
        mixtures.create_group("MOD")


def _write_reference_h5(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset(
            "openmc_volume_flux",
            data=np.array([[120.0, 600.0], [80.0, 800.0]], dtype=float),
        )
        dataset.attrs["mixture_names"] = np.asarray(["MOD", "FUEL"], dtype="S")


def _write_reference_csv(path: Path) -> None:
    path.write_text(
        "mixture,group,openmc_volume_flux\n"
        "FUEL,1,80.0\n"
        "FUEL,2,800.0\n"
        "MOD,1,120.0\n"
        "MOD,2,600.0\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
