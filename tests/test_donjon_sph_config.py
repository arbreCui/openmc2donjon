from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from openmc2donjon.cli import main as cli_main
from openmc2donjon.donjon_sph_config import build_donjon_sph_loop_config


class DonjonSphConfigTests(unittest.TestCase):
    def test_builder_writes_packaged_runner_contract(self) -> None:
        config = build_donjon_sph_loop_config(
            input_h5="mgxs_library.h5",
            output_dir="sph_loop",
            solve_template="solve_lflux_dump.x2m.in",
            flux_map="flux_map.h5",
            python_bin="/usr/bin/python3",
            case_id_prefix="case",
            stage_prefix="stage",
            iterations=3,
            sph_change_tolerance=1.0e-4,
            flux_ratio_tolerance=5.0e-4,
            min_iterations=2,
            fail_on_nonconvergence=True,
            acceptance={
                "min_completed_iterations": 3,
                "max_final_keff_delta_pcm": 5.0,
                "fail_on_violation": True,
            },
        )

        self.assertEqual(config["schema"], "openmc2donjon.sph-loop-config.v1")
        self.assertEqual(config["reference_flux"], "flux_map.h5::openmc_volume_flux")
        self.assertEqual(config["map_h5"], "flux_map.h5")
        self.assertEqual(config["iterations"], 3)
        self.assertEqual(
            config["convergence"],
            {
                "sph_change_tolerance": 1.0e-4,
                "flux_ratio_tolerance": 5.0e-4,
                "min_iterations": 2,
                "fail_on_nonconvergence": True,
            },
        )
        self.assertEqual(
            config["acceptance"],
            {
                "min_completed_iterations": 3,
                "max_final_keff_delta_pcm": 5.0,
                "fail_on_violation": True,
            },
        )
        self.assertTrue(config["final_solve"])
        self.assertEqual(config["solver"]["result"], "donjon_flux.result")
        solver = " ".join(config["solver"]["command"])
        postprocess = " ".join(config["postprocess"]["command"])
        self.assertIn("-m openmc2donjon.donjon_deck_runner solve", solver)
        self.assertIn("-m openmc2donjon.donjon_deck_runner apply", postprocess)
        self.assertIn("solve_lflux_dump.x2m.in", solver)
        self.assertIn("apply_nsph_mac.x2m.in", postprocess)
        self.assertIn("/tmp/stage_solve_iter{iteration}", config["solver"]["command"])
        self.assertIn("/tmp/stage_apply_iter{iteration1}", config["postprocess"]["command"])

    def test_cli_writes_config_with_explicit_reference_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            output = tmp / "loop.json"
            solve_template = tmp / "solve.x2m.in"
            solve_template.write_text("UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;\n")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "make-donjon-sph-loop-config",
                        "--output",
                        str(output),
                        "--output-dir",
                        str(tmp / "loop"),
                        "--mgxs",
                        str(tmp / "mgxs.h5"),
                        "--solve-template",
                        str(solve_template),
                        "--flux-map",
                        str(tmp / "flux_map.h5"),
                        "--reference-flux",
                        f"{tmp / 'reference.h5'}::phi",
                        "--python-bin",
                        "/usr/bin/python3",
                        "--iterations",
                        "1",
                        "--flux-ratio-tolerance",
                        "1e-3",
                        "--sph-change-tolerance",
                        "2e-3",
                        "--acceptance-min-completed-iterations",
                        "1",
                        "--acceptance-require-final-solve",
                        "--acceptance-max-final-keff-delta-pcm",
                        "5.0",
                        "--fail-on-acceptance-violation",
                        "--no-final-solve",
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("DONJON SPH loop config", stream.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["reference_flux"], f"{tmp / 'reference.h5'}::phi")
            self.assertFalse(payload["final_solve"])
            self.assertEqual(payload["iterations"], 1)
            self.assertEqual(payload["convergence"]["flux_ratio_tolerance"], 1.0e-3)
            self.assertEqual(payload["convergence"]["sph_change_tolerance"], 2.0e-3)
            self.assertEqual(payload["acceptance"]["min_completed_iterations"], 1)
            self.assertTrue(payload["acceptance"]["require_final_solve"])
            self.assertEqual(payload["acceptance"]["max_final_keff_delta_pcm"], 5.0)
            self.assertTrue(payload["acceptance"]["fail_on_violation"])
            self.assertEqual(payload["input_h5"], str(tmp / "mgxs.h5"))
            self.assertIn("openmc2donjon.donjon_deck_runner", payload["solver"]["command"])


if __name__ == "__main__":
    unittest.main()
