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
                    "--helper",
                    str(tmp / "helper.py"),
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
        self.assertEqual(payload["solver"]["result"], "donjon_flux.result")
        self.assertIn("{ascii_input}", payload["solver"]["command"])
        self.assertIn("{result}", payload["solver"]["command"])
        self.assertIn("{workflow_ascii}", payload["postprocess"]["command"])
        self.assertIn("{output}", payload["postprocess"]["command"])
        self.assertEqual(payload["postprocess"]["output"], "corrected_pn.macrolib.txt")

    def test_run_script_is_the_user_facing_entrypoint(self) -> None:
        root = _repo_root()
        run_sh = root / "examples/donjon_openmc2donjon/c5g7_sph_loop/run.sh"
        text = run_sh.read_text(encoding="utf-8")
        self.assertIn("make_config.py", text)
        self.assertIn("run-sph-loop", text)
        self.assertIn("sph_loop_summary.json", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
