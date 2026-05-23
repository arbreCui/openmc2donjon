from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main
from openmc2donjon.openmc_sph_loop_handoff import prepare_openmc_sph_loop_handoff
from openmc2donjon.sph_loop_plan import build_sph_loop_plan


EXPECTED_ENTRYPOINT_REFERENCE_FLUX = np.asarray(
    [
        [617.96762, 156.844407],
        [47.4604219, 4.87293612],
    ],
    dtype=float,
)


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
                    EXPECTED_ENTRYPOINT_REFERENCE_FLUX,
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
            self.assertEqual(loop_config["flux_normalization"], "none")
            self.assertEqual(loop_config["acceptance"]["min_completed_iterations"], 2)
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
            self.assertIn("openmc-sph-loop-statepoint", labels)
            self.assertIn("openmc-sph-loop-solve-template", labels)
            self.assertIn("openmc-sph-loop-apply-template", labels)
            self.assertEqual(
                labels["openmc-sph-loop-config"]["bundled_path"],
                "loop_config.json",
            )
            self.assertEqual(
                labels["openmc-sph-loop-run-script"]["bundled_path"],
                "run_sph_loop.sh",
            )
            self.assertIn("openmc-sph-loop-summary", labels)
            self.assertIn("openmc-sph-loop-check-summary", labels)

            bundle_config = json.loads(
                (bundle_dir / "loop_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(bundle_config["input_h5"], "mgxs_library.h5")
            self.assertEqual(bundle_config["output_dir"], "sph_loop")
            self.assertEqual(bundle_config["flux_normalization"], "none")
            self.assertEqual(
                bundle_config["reference_flux"],
                "reference_flux.h5::openmc_volume_flux",
            )
            self.assertEqual(bundle_config["map_h5"], "flux_map.h5")
            self.assertEqual(bundle_config["run_script"], "run_sph_loop.sh")
            self.assertEqual(
                _command_option(bundle_config["solver"]["command"], "--deck-template"),
                "solve_template.x2m.in",
            )
            self.assertEqual(
                _command_option(
                    bundle_config["postprocess"]["command"],
                    "--deck-template",
                ),
                "apply_template.x2m.in",
            )
            self.assertEqual(
                bundle_config["solver"]["command"][:3],
                [
                    "python3",
                    "-m",
                    "openmc2donjon.donjon_deck_runner",
                ],
            )
            self.assertTrue((bundle_dir / "run_sph_loop.sh").exists())
            self.assertNotIn(
                str(run_dir),
                (bundle_dir / "run_sph_loop.sh").read_text(encoding="utf-8"),
            )

            relocated = tmp / "relocated_bundle"
            shutil.copytree(bundle_dir, relocated)
            plan = build_sph_loop_plan(relocated / "loop_config.json")
            self.assertEqual(plan.input_h5, relocated / "mgxs_library.h5")
            self.assertEqual(plan.map_h5, relocated / "flux_map.h5")
            self.assertEqual(
                plan.reference_flux,
                f"{relocated / 'reference_flux.h5'}::openmc_volume_flux",
            )
            self.assertEqual(plan.loop_dir, relocated / "sph_loop")
            self.assertEqual(plan.run_script, relocated / "run_sph_loop.sh")

    def test_production_handoff_defaults_loop_acceptance_preset(self) -> None:
        root = _repo_root()
        recipe = root / "examples/openmc_sph_loop_entrypoint/export_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            solve_template = tmp / "solve.x2m.in"
            run_dir = tmp / "handoff"
            bundle_dir = run_dir / "bundle"
            solve_template.write_text(
                "SEQ_ASCII MAC :: FILE '{macrolib}' ;\n",
                encoding="utf-8",
            )

            report = prepare_openmc_sph_loop_handoff(
                recipe=recipe,
                no_load_statepoint=True,
                run_dir=run_dir,
                solve_template=solve_template,
                scalar_flux_ids={"FUEL_A": 2, "MOD_A": 4},
                production=True,
                python_bin="python3",
                bundle_dir=bundle_dir,
            )

            self.assertEqual(report.check_summary_json, run_dir / "check_summary.json")
            check_summary = json.loads(report.check_summary_json.read_text(encoding="utf-8"))
            self.assertTrue(check_summary["inputs"][0]["openmc_volume_flux"]["present"])
            self.assertEqual(
                check_summary["inputs"][0]["openmc_volume_flux"]["group_order"],
                "mgxs_donjon",
            )
            loop_config = json.loads(report.scaffold.loop_config.read_text(encoding="utf-8"))
            self.assertEqual(loop_config["flux_normalization"], "auto")
            self.assertEqual(loop_config["acceptance"], {"preset": "production"})
            plan = build_sph_loop_plan(report.scaffold.loop_config)
            self.assertTrue(
                plan.normalized_acceptance["require_artifact_metadata_alignment"]
            )
            self.assertTrue(plan.normalized_acceptance["require_production_audit"])
            self.assertTrue(
                plan.normalized_acceptance["require_mgxs_explicit_volumes"]
            )
            self.assertTrue(plan.normalized_acceptance["require_mgxs_h_factor"])
            self.assertTrue(plan.normalized_acceptance["require_final_solve"])
            with h5py.File(report.mgxs_h5, "r") as h5:
                np.testing.assert_allclose(
                    h5["mixtures/FUEL_A/kappa_fission"][:],
                    [3.2e-12, 3.1e-12],
                )

            bundle_config = json.loads(
                (bundle_dir / "loop_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(bundle_config["acceptance"], {"preset": "production"})
            self.assertEqual(bundle_config["flux_normalization"], "auto")

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
            bundle_config = json.loads(
                (bundle_dir / "loop_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(bundle_config["input_h5"], "mgxs_library.h5")
            self.assertEqual(bundle_config["map_h5"], "flux_map.h5")
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

    def test_require_h_factor_defaults_flux_normalization_to_auto(self) -> None:
        root = _repo_root()
        recipe = root / "examples/openmc_sph_loop_entrypoint/export_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            solve_template = tmp / "solve.x2m.in"
            run_dir = tmp / "handoff"
            solve_template.write_text("dummy {macrolib}\n", encoding="utf-8")

            prepare_openmc_sph_loop_handoff(
                recipe=recipe,
                no_load_statepoint=True,
                run_dir=run_dir,
                solve_template=solve_template,
                scalar_flux_ids={"FUEL_A": 2, "MOD_A": 4},
                check=False,
                require_h_factor=True,
                python_bin="python3",
            )

            loop_config = json.loads(
                (run_dir / "sph_loop_inputs/loop_config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(loop_config["flux_normalization"], "auto")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _command_option(command: list[str], option: str) -> str | None:
    for index, value in enumerate(command[:-1]):
        if value == option:
            return command[index + 1]
    return None


if __name__ == "__main__":
    unittest.main()
