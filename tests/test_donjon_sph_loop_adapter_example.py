from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import numpy as np


class DonjonSphLoopAdapterExampleTests(unittest.TestCase):
    def test_make_inputs_writes_flux_map_and_reference(self) -> None:
        root = _repo_root()
        script = root / "examples/donjon_sph_loop_adapter/make_inputs.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            subprocess.run(
                [sys.executable, str(script), "--output-dir", str(out)],
                check=True,
                cwd=root,
            )

            with h5py.File(out / "mgxs_library.h5", "r") as h5:
                self.assertEqual(h5.attrs["domain_mode"], "donjon_sph_loop_adapter")
                self.assertEqual(tuple(h5["mixtures"].keys()), ("ASM_LEFT", "ASM_RIGHT"))
                self.assertIn("transport_total", h5["mixtures/ASM_LEFT"])
                np.testing.assert_allclose(h5["energy_bounds"][:], [1.0e-5, 1.0, 1.0e7])

            with h5py.File(out / "flux_map.h5", "r") as h5:
                self.assertEqual(h5.attrs["schema"], "openmc2donjon.donjon-flux-map.v1")
                np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])

            with h5py.File(out / "reference_expected.h5", "r") as h5:
                np.testing.assert_allclose(h5["expected_sph"][:], np.full((2, 2), np.sqrt(2.0)))

    def test_make_config_writes_generic_run_sph_loop_contract(self) -> None:
        root = _repo_root()
        script = root / "examples/donjon_sph_loop_adapter/make_config.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = tmp / "config.json"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output",
                    str(config),
                    "--output-dir",
                    str(tmp / "loop"),
                    "--mgxs",
                    str(tmp / "mgxs.h5"),
                    "--reference-flux",
                    str(tmp / "reference_flux.h5"),
                    "--flux-map",
                    str(tmp / "flux_map.h5"),
                    "--driver",
                    str(root / "examples/donjon_sph_loop_adapter/fake_donjon_driver.py"),
                    "--python-bin",
                    sys.executable,
                ],
                check=True,
                cwd=root,
            )

            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "openmc2donjon.sph-loop-config.v1")
            self.assertEqual(payload["format"], "macrolib")
            self.assertEqual(payload["iterations"], 2)
            self.assertEqual(payload["damping"], 0.5)
            self.assertEqual(payload["solver"]["result"], "donjon_flux.result")
            self.assertIn("{ascii_input}", payload["solver"]["command"])
            self.assertIn("{result}", payload["solver"]["command"])
            self.assertIn("{workflow_ascii}", payload["postprocess"]["command"])
            self.assertIn("{sph_sidecar}", payload["postprocess"]["command"])
            self.assertEqual(payload["postprocess"]["output"], "corrected.macrolib.txt")

    def test_make_real_config_writes_donjon_deck_runner_contract(self) -> None:
        root = _repo_root()
        script = root / "examples/donjon_sph_loop_adapter/make_real_config.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = tmp / "real_config.json"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output",
                    str(config),
                    "--output-dir",
                    str(tmp / "loop"),
                    "--mgxs",
                    str(tmp / "mgxs.h5"),
                    "--reference-flux",
                    str(tmp / "reference_flux.h5"),
                    "--flux-map",
                    str(tmp / "flux_map.h5"),
                    "--donjon-root",
                    str(tmp / "Donjon"),
                    "--python-bin",
                    sys.executable,
                    "--case-id-prefix",
                    "case",
                ],
                check=True,
                cwd=root,
            )

            payload = json.loads(config.read_text(encoding="utf-8"))
            solver = payload["solver"]["command"]
            postprocess = payload["postprocess"]["command"]
            self.assertIn("donjon_deck_runner.py", " ".join(solver))
            self.assertIn("solve_lflux_dump.x2m.in", " ".join(solver))
            self.assertIn("apply_nsph_mac.x2m.in", " ".join(postprocess))
            self.assertIn("case_solve_iter{iteration}", solver)
            self.assertIn("case_apply_iter{iteration1}", postprocess)
            self.assertIn("{solve_dir}/donjon_stage", solver)
            self.assertIn("{workflow_dir}/donjon_stage", postprocess)

    def test_donjon_deck_runner_dry_run_renders_apply_deck(self) -> None:
        root = _repo_root()
        runner = root / "examples/donjon_sph_loop_adapter/donjon_deck_runner.py"
        template = (
            root
            / "examples/donjon_sph_loop_adapter/templates/apply_nsph_mac.x2m.in"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            macrolib = tmp / "input.macrolib.txt"
            output = tmp / "corrected.macrolib.txt"
            donjon_root = tmp / "Donjon"
            work_dir = tmp / "stage"
            case_id = "dry_case"
            macrolib.write_text("dummy macrolib\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(runner),
                    "apply",
                    "--dry-run",
                    "--donjon-root",
                    str(donjon_root),
                    "--deck-template",
                    str(template),
                    "--macrolib",
                    str(macrolib),
                    "--output",
                    str(output),
                    "--iteration",
                    "2",
                    "--case-id",
                    case_id,
                    "--work-dir",
                    str(work_dir),
                ],
                check=True,
                cwd=root,
            )

            deck = (
                donjon_root
                / "data/openmc2donjon/case_runs/donjon_sph_loop_adapter/dry_case.x2m"
            )
            staged = work_dir / "dry_case.macrolib.txt"
            self.assertTrue(deck.exists())
            self.assertTrue(staged.exists())
            text = deck.read_text(encoding="utf-8")
            self.assertIn("DSPH:", text)
            self.assertIn("MAC:", text)
            self.assertIn(str(staged), text)
            self.assertIn("dry_case.corrected.macrolib.txt", text)

    def test_smoke_script_exercises_loop_driver(self) -> None:
        root = _repo_root()
        text = (root / "examples/donjon_sph_loop_adapter/run_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("run-sph-loop", text)
        self.assertIn("openmc2donjon_sph_loop_passed", text)
        self.assertIn("donjon_volume_flux_h5", text)
        self.assertIn("corrected.macrolib.txt", text)
        self.assertIn("scalar_flux_ids", text)
        self.assertIn("make_real_config.py", text)
        self.assertIn("donjon_deck_runner.py", text)
        self.assertIn("--dry-run", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
