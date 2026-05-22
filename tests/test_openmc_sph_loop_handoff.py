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
from openmc2donjon.openmc_sph_loop_handoff import prepare_openmc_sph_loop_handoff


class OpenMCSphLoopHandoffTests(unittest.TestCase):
    def test_prepare_handoff_exports_converts_and_scaffolds(self) -> None:
        root = _repo_root()
        recipe = root / "examples/openmc_sph_loop_entrypoint/export_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            solve_template = tmp / "solve.x2m.in"
            run_dir = tmp / "handoff"
            bundle_dir = run_dir / "delivery_bundle"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")
            solve_template.write_text(
                "SEQ_ASCII MAC :: FILE '{macrolib}' ;\n",
                encoding="utf-8",
            )

            report = prepare_openmc_sph_loop_handoff(
                recipe=recipe,
                statepoint=statepoint,
                run_dir=run_dir,
                solve_template=solve_template,
                scalar_flux_ids={"FUEL_A": 2, "MOD_A": 4},
                scatter_row_balance_fail=1.0e-12,
                acceptance={"min_completed_iterations": 2},
                python_bin="python3",
                bundle_dir=bundle_dir,
            )

            self.assertEqual(report.mgxs_h5, run_dir / "mgxs_library.h5")
            self.assertEqual(report.ascii_output, run_dir / "out.macrolib.txt")
            self.assertEqual(report.solve_template, solve_template)
            self.assertEqual(report.bundle_manifest, bundle_dir / "manifest.json")
            self.assertTrue(report.ascii_output.exists())
            self.assertEqual(report.scaffold.scalar_flux_ids, (2, 4))
            self.assertEqual(
                report.scaffold.run_script,
                run_dir / "sph_loop_inputs/run_sph_loop.sh",
            )
            self.assertTrue(report.scaffold.run_script.exists())
            with h5py.File(report.mgxs_h5, "r") as h5:
                np.testing.assert_allclose(
                    h5["openmc_volume_flux"][:],
                    [[80.0, 800.0], [120.0, 600.0]],
                )
            summary = json.loads(
                (run_dir / "openmc_sph_loop_handoff_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                summary["decision"],
                "openmc2donjon_openmc_sph_loop_handoff_passed",
            )
            self.assertEqual(
                summary["loop_config"],
                str(run_dir / "sph_loop_inputs/loop_config.json"),
            )
            self.assertEqual(summary["solve_template"], str(solve_template))
            self.assertEqual(summary["bundle_manifest"], str(bundle_dir / "manifest.json"))
            self.assertEqual(summary["scalar_flux_ids"], [2, 4])
            self.assertEqual(
                summary["run_script"],
                str(run_dir / "sph_loop_inputs/run_sph_loop.sh"),
            )
            self.assertEqual(
                summary["run_command"][-2:],
                ["--config", str(run_dir / "sph_loop_inputs/loop_config.json")],
            )
            loop_config = json.loads(
                (run_dir / "sph_loop_inputs/loop_config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                loop_config["run_script"],
                str(run_dir / "sph_loop_inputs/run_sph_loop.sh"),
            )
            self.assertEqual(loop_config["acceptance"]["min_completed_iterations"], 2)
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            labels = {artifact["label"] for artifact in manifest["artifacts"]}
            self.assertIn("openmc-sph-loop-statepoint", labels)
            self.assertIn("openmc-sph-loop-solve-template", labels)
            self.assertIn("openmc-sph-loop-config", labels)
            self.assertIn("openmc-sph-loop-run-script", labels)
            self.assertIn("openmc-sph-loop-summary", labels)
            self.assertIn("openmc-sph-loop-check-summary", labels)

    def test_cli_prepare_handoff_supports_sequential_flux_map(self) -> None:
        root = _repo_root()
        recipe = root / "examples/openmc_sph_loop_entrypoint/export_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            solve_template = tmp / "solve.x2m.in"
            run_dir = tmp / "handoff"
            bundle_dir = run_dir / "bundle"
            solve_template.write_text("dummy {macrolib}\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "prepare-openmc-sph-loop",
                        "--recipe",
                        str(recipe),
                        "--no-load-statepoint",
                        "--run-dir",
                        str(run_dir),
                        "--solve-template",
                        str(solve_template),
                        "--sequential-scalar-flux-map",
                        "--acceptance-max-final-to-initial-flux-residual-ratio",
                        "0.5",
                        "--acceptance-max-final-clipped-fraction",
                        "1.0",
                        "--no-check",
                        "--bundle-dir",
                        str(bundle_dir),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn(
                "openmc2donjon_openmc_sph_loop_handoff_passed",
                stream.getvalue(),
            )
            payload = json.loads(
                (run_dir / "openmc_sph_loop_handoff_summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(payload["scalar_flux_ids"], [1, 2])
            self.assertEqual(payload["bundle_manifest"], str(bundle_dir / "manifest.json"))
            self.assertTrue((run_dir / "sph_loop_inputs/reference_flux.h5").exists())
            self.assertTrue((run_dir / "sph_loop_inputs/flux_map.h5").exists())
            self.assertTrue((run_dir / "sph_loop_inputs/loop_config.json").exists())
            self.assertTrue((run_dir / "sph_loop_inputs/run_sph_loop.sh").exists())
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            labels = {artifact["label"] for artifact in manifest["artifacts"]}
            self.assertIn("openmc-sph-loop-run-script", labels)
            self.assertIn("openmc-sph-loop-config", labels)
            self.assertIn("openmc-sph-loop-summary", labels)
            self.assertNotIn("openmc-sph-loop-check-summary", labels)
            loop_config = json.loads(
                (run_dir / "sph_loop_inputs/loop_config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                loop_config["acceptance"]["max_final_to_initial_flux_residual_ratio"],
                0.5,
            )
            self.assertEqual(loop_config["acceptance"]["max_final_clipped_fraction"], 1.0)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
