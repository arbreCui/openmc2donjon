from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.lcm_ascii import read_lcm_ascii
from openmc2donjon.sph_loop_plan import build_sph_loop_plan


class SphLoopMinicaseExampleTests(unittest.TestCase):
    def test_make_inputs_writes_user_case_and_config(self) -> None:
        root = _repo_root()
        script = root / "examples/sph_loop_minicase/make_inputs.py"
        driver = root / "examples/sph_loop_minicase/fake_low_order_solver.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            case_dir = Path(tmpdir) / "case"
            config = case_dir / "loop_config.json"
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output-dir",
                    str(case_dir),
                    "--config",
                    str(config),
                    "--driver",
                    str(driver),
                    "--python-bin",
                    sys.executable,
                ],
                check=True,
                cwd=root,
            )

            with h5py.File(case_dir / "inputs/mgxs_library.h5", "r") as h5:
                self.assertEqual(h5.attrs["domain_mode"], "assembly-wise")
                self.assertEqual(
                    tuple(h5["mixtures"].keys()),
                    ("FUEL_ASM", "REFL_ASM"),
                )
                self.assertIn("transport_total", h5["mixtures/FUEL_ASM"])
                np.testing.assert_allclose(
                    h5["energy_bounds"][:],
                    [1.0e-5, 1.0, 1.0e7],
                )

            with h5py.File(case_dir / "inputs/flux_map.h5", "r") as h5:
                self.assertEqual(
                    h5.attrs["schema"],
                    "openmc2donjon.low-order-flux-map.v1",
                )
                np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])

            with h5py.File(case_dir / "expected_sph.h5", "r") as h5:
                np.testing.assert_allclose(
                    h5["expected_sph"][:],
                    np.full((2, 2), np.sqrt(2.0)),
                )

            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "openmc2donjon.sph-loop-config.v1")
            self.assertEqual(payload["format"], "macrolib")
            self.assertEqual(payload["iterations"], 2)
            self.assertEqual(payload["damping"], 0.5)
            self.assertEqual(payload["solver"]["result"], "low_order_flux.result")
            self.assertIn("{ascii_input}", payload["solver"]["command"])
            self.assertIn("{result}", payload["solver"]["command"])
            self.assertIn("{workflow_ascii}", payload["postprocess"]["command"])
            self.assertIn("{sph_sidecar}", payload["postprocess"]["command"])

            plan = build_sph_loop_plan(config)
            self.assertEqual(plan.input_h5, case_dir / "inputs/mgxs_library.h5")
            self.assertEqual(plan.map_h5, case_dir / "inputs/flux_map.h5")
            self.assertTrue(plan.convergence_enabled)
            self.assertTrue(plan.fail_on_nonconvergence)
            self.assertTrue(plan.run_final_solve)
            self.assertEqual(plan.normalized_acceptance["min_completed_iterations"], 2)
            self.assertEqual(plan.normalized_acceptance["require_converged"], True)

    def test_fake_low_order_solver_writes_parseable_lflux_dump(self) -> None:
        root = _repo_root()
        driver = root / "examples/sph_loop_minicase/fake_low_order_solver.py"
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{root / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            macrolib = tmp / "input.macrolib.txt"
            result = tmp / "low_order_flux.result"
            macrolib.write_text("dummy macrolib\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(driver),
                    "solve",
                    "--macrolib",
                    str(macrolib),
                    "--result",
                    str(result),
                    "--iteration",
                    "0",
                ],
                check=True,
                cwd=root,
                env=env,
            )

            blocks = read_lcm_ascii(result)
            self.assertEqual(blocks[0].name, "SIGNATURE")
            self.assertEqual(blocks[0].data.strip(), "L_FLUX")
            payloads = [
                block.data
                for block in blocks
                if block.name is None and block.type_code == 2 and block.count == 4
            ]
            self.assertEqual(len(payloads), 2)
            np.testing.assert_allclose(payloads[0], [1.0, 40.0, 3.0, 60.0])
            np.testing.assert_allclose(payloads[1], [10.0, 400.0, 30.0, 300.0])

    def test_smoke_script_is_the_runnable_user_entrypoint(self) -> None:
        root = _repo_root()
        text = (root / "examples/sph_loop_minicase/run_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("make_inputs.py", text)
        self.assertIn("run-sph-loop", text)
        self.assertIn("validate-bundle", text)
        self.assertIn("corrected.macrolib.txt", text)
        self.assertIn("openmc2donjon minimal SPH loop minicase: PASS", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
