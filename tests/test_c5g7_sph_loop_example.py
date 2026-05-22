from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class C5G7SphLoopExampleTests(unittest.TestCase):
    def test_make_config_writes_reusable_sph_loop_config(self) -> None:
        root = _repo_root()
        script = root / "examples/donjon_openmc2donjon/c5g7_sph_loop/make_config.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = tmp / "c5g7_sph_loop_config.json"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output",
                    str(config),
                    "--output-dir",
                    str(tmp / "sph_loop"),
                    "--mgxs",
                    str(tmp / "mgxs.h5"),
                    "--reference-flux",
                    str(tmp / "reference_flux.h5"),
                    "--donjon-root",
                    str(tmp / "Donjon"),
                    "--driver",
                    str(tmp / "donjon_deck_runner.py"),
                    "--solve-template",
                    str(tmp / "solve_lflux_dump.x2m.in"),
                    "--apply-template",
                    str(tmp / "apply_nsph_mac.x2m.in"),
                    "--python-bin",
                    sys.executable,
                    "--damping",
                    "0.25",
                    "--run-tag",
                    "unit_tag",
                ],
                check=True,
                text=True,
                capture_output=True,
            )

            payload = json.loads(config.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], "openmc2donjon.sph-loop-config.v1")
        self.assertEqual(payload["iterations"], 2)
        self.assertTrue(payload["final_solve"])
        self.assertEqual(payload["format"], "macrolib")
        self.assertEqual(payload["damping"], 0.25)
        self.assertEqual(payload["reference_flux"], f"{tmp / 'reference_flux.h5'}::openmc_volume_flux")
        self.assertEqual(payload["map_h5"], str(tmp / "reference_flux.h5"))
        self.assertTrue(payload["acceptance"]["fail_on_violation"])
        self.assertEqual(
            payload["acceptance"]["max_final_to_initial_flux_residual_ratio"],
            1.25,
        )
        self.assertEqual(payload["acceptance"]["max_final_clipped_fraction"], 0.0)
        self.assertEqual(payload["acceptance"]["max_final_clipped_count"], 0)
        self.assertEqual(payload["acceptance"]["max_final_keff_delta_pcm"], 5.0)
        self.assertEqual(payload["acceptance"]["max_keff_step_pcm"], 5.0)
        self.assertEqual(payload["solver"]["result"], "donjon_flux.result")
        self.assertIn("donjon_deck_runner.py", " ".join(payload["solver"]["command"]))
        self.assertIn("solve_lflux_dump.x2m.in", " ".join(payload["solver"]["command"]))
        self.assertIn("apply_nsph_mac.x2m.in", " ".join(payload["postprocess"]["command"]))
        self.assertIn("{ascii_input}", payload["solver"]["command"])
        self.assertIn("{result}", payload["solver"]["command"])
        self.assertIn("{workflow_ascii}", payload["postprocess"]["command"])
        self.assertIn("{output}", payload["postprocess"]["command"])
        self.assertIn("/tmp/odj_c5g7_sph_solve_iter{iteration}", payload["solver"]["command"])
        self.assertIn("/tmp/odj_c5g7_sph_apply_iter{iteration1}", payload["postprocess"]["command"])
        self.assertEqual(payload["postprocess"]["output"], "corrected_pn.macrolib.txt")

    def test_solve_template_is_c5g7_assembly_wise_deck(self) -> None:
        root = _repo_root()
        template = (
            root
            / "examples/donjon_openmc2donjon/c5g7_sph_loop/templates/solve_lflux_dump.x2m.in"
        )
        text = template.read_text(encoding="utf-8")

        self.assertIn("CAR2D 3 3", text)
        self.assertIn("TRIVAT:", text)
        self.assertIn("TRIVAA:", text)
        self.assertIn("FLUD:", text)
        self.assertIn("UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;", text)
        self.assertIn("OPENMC2DONJON C5G7 FIXED OPENMC SPH LOOP ITER", text)

    def test_run_script_is_the_user_facing_entrypoint(self) -> None:
        root = _repo_root()
        run_sh = root / "examples/donjon_openmc2donjon/c5g7_sph_loop/run.sh"
        text = run_sh.read_text(encoding="utf-8")
        self.assertIn("make_config.py", text)
        self.assertIn("run-sph-loop", text)
        self.assertIn("solve_lflux_dump.x2m.in", text)
        self.assertIn("sph_loop_summary.json", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
