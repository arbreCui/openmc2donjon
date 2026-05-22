from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from openmc2donjon.sph_loop_plan import build_sph_loop_plan


class SphLoopPlanTests(unittest.TestCase):
    def test_resolves_paths_and_normalizes_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            config_dir.mkdir()
            config = config_dir / "loop.json"
            _write_config(
                config,
                {
                    "input_h5": "data/mgxs.h5",
                    "output_dir": "runs/sph",
                    "reference_flux": "flux/reference.h5::openmc_volume_flux",
                    "map_h5": "flux/map.h5",
                    "iterations": 3,
                    "format": "multicompo",
                    "root_name": "CPO",
                    "h_factor_default": "1.25",
                    "damping": 0.4,
                    "clip_min": 0.5,
                    "clip_max": 2.0,
                    "sph_kind": "case-sph",
                    "sph_real": False,
                    "sph_applied": True,
                    "source_label": "case label",
                    "kn_column": 2,
                    "list_offset": 1,
                    "final_solve": True,
                    "run_script": "run_sph_loop.sh",
                    "convergence": {
                        "sph_change_tolerance": "0.02",
                        "flux_ratio_tolerance": 0.03,
                        "min_iterations": 2,
                        "fail_on_nonconvergence": True,
                    },
                    "acceptance": {
                        "min_completed_iterations": "2",
                        "require_final_solve": True,
                        "max_final_keff_delta_pcm": "5.0",
                        "fail_on_violation": True,
                    },
                    "postprocess": {
                        "command": ["python", "post.py"],
                        "output": "corrected.macrolib.txt",
                    },
                },
            )

            plan = build_sph_loop_plan(
                config,
                summary_json="summaries/loop.json",
                bundle_dir="bundle",
                bundle_manifest_name="bundle.json",
            )

            self.assertEqual(plan.config_path, config)
            self.assertEqual(plan.base_dir, config_dir)
            self.assertEqual(plan.input_h5, config_dir / "data/mgxs.h5")
            self.assertEqual(plan.loop_dir, config_dir / "runs/sph")
            self.assertEqual(
                plan.reference_flux,
                f"{config_dir / 'flux/reference.h5'}::openmc_volume_flux",
            )
            self.assertEqual(plan.map_h5, config_dir / "flux/map.h5")
            self.assertEqual(plan.scalar_flux_ids, None)
            self.assertEqual(plan.scalar_flux_column, 1)
            self.assertEqual(plan.list_offset, 1)
            self.assertEqual(plan.iterations, 3)
            self.assertEqual(plan.output_format, "multicompo")
            self.assertEqual(plan.root_name, "CPO")
            self.assertEqual(plan.h_factor_default, 1.25)
            self.assertEqual(plan.damping, 0.4)
            self.assertEqual(plan.clip_min, 0.5)
            self.assertEqual(plan.clip_max, 2.0)
            self.assertEqual(plan.sph_kind, "case-sph")
            self.assertFalse(plan.sph_real)
            self.assertTrue(plan.sph_applied)
            self.assertEqual(plan.source_label, "case label")
            self.assertTrue(plan.run_final_solve)
            self.assertEqual(plan.sph_change_tolerance, 0.02)
            self.assertEqual(plan.flux_ratio_tolerance, 0.03)
            self.assertTrue(plan.convergence_enabled)
            self.assertEqual(plan.min_iterations, 2)
            self.assertTrue(plan.fail_on_nonconvergence)
            self.assertEqual(
                plan.normalized_acceptance["max_final_keff_delta_pcm"],
                5.0,
            )
            self.assertTrue(plan.normalized_acceptance["fail_on_violation"])
            self.assertEqual(plan.summary_path, config_dir / "summaries/loop.json")
            self.assertEqual(
                plan.audit_csv,
                config_dir / "summaries/sph_loop_audit.csv",
            )
            self.assertEqual(
                plan.audit_text,
                config_dir / "summaries/sph_loop_audit.txt",
            )
            self.assertEqual(plan.bundle_dir, config_dir / "bundle")
            self.assertEqual(plan.bundle_manifest, config_dir / "bundle/bundle.json")
            self.assertEqual(plan.run_script, config_dir / "run_sph_loop.sh")
            self.assertEqual(plan.solver["command"], ["python", "solve.py"])
            self.assertIsNotNone(plan.postprocessor)

    def test_output_dir_override_is_resolved_from_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "loop.json"
            _write_config(config)

            plan = build_sph_loop_plan(config, output_dir="override_loop")

            self.assertEqual(plan.loop_dir, Path.cwd() / "override_loop")
            self.assertEqual(plan.summary_path, Path.cwd() / "override_loop/sph_loop_summary.json")

    def test_rejects_bad_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "loop.json"
            _write_config(config, {"format": "bad"})

            with self.assertRaisesRegex(ValueError, "format must be"):
                build_sph_loop_plan(config)

    def test_rejects_min_iterations_above_iteration_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "loop.json"
            _write_config(
                config,
                {
                    "iterations": 1,
                    "convergence": {"min_iterations": 2},
                },
            )

            with self.assertRaisesRegex(
                ValueError,
                "convergence.min_iterations must be <= iterations",
            ):
                build_sph_loop_plan(config)

    def test_rejects_map_h5_with_scalar_flux_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "loop.json"
            _write_config(
                config,
                {
                    "map_h5": "map.h5",
                    "scalar_flux_map": {"fuel": 1},
                },
            )

            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                build_sph_loop_plan(config)


def _write_config(path: Path, extra: dict[str, object] | None = None) -> None:
    payload: dict[str, object] = {
        "schema": "openmc2donjon.sph-loop-config.v1",
        "input_h5": "mgxs.h5",
        "output_dir": "sph_loop",
        "reference_flux": "reference.h5::openmc_volume_flux",
        "iterations": 1,
        "solver": {
            "command": ["python", "solve.py"],
            "result": "donjon_flux.result",
        },
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
