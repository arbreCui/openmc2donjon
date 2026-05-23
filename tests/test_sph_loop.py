from __future__ import annotations

import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main
from openmc2donjon.macrolib import read_macrolib_ascii
from openmc2donjon.sph_loop import PASS_DECISION
from openmc2donjon.sph_loop_preflight import build_flux_map_preflight_report


class SphLoopTests(unittest.TestCase):
    def test_cli_runs_configured_two_cycle_sph_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            postprocess = root / "fake_postprocess.py"
            run_script = root / "run_sph_loop.sh"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            bundle_dir = root / "sph_loop_bundle"
            _write_mgxs(mgxs)
            _write_reference_flux(
                reference,
                std_dev=np.asarray([[0.8, 8.0], [0.8, 8.0]]),
            )
            _write_fake_solver(solver)
            _write_fake_postprocess(postprocess)
            run_script.write_text(
                "#!/usr/bin/env bash\n"
                "python -m openmc2donjon.cli run-sph-loop --config loop.json\n",
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 2,
                        "format": "macrolib",
                        "final_solve": True,
                        "run_script": "run_sph_loop.sh",
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {
                            "min_completed_iterations": 2,
                            "require_final_solve": True,
                            "max_sph_rel_change": 1.0,
                            "max_flux_ratio_residual": 1.0,
                            "require_reference_flux_std_dev": True,
                            "max_reference_flux_std_dev_rel": 0.02,
                            "sph_minimum_floor": 1.9,
                            "sph_maximum_ceiling": 2.1,
                            "max_keff_step_pcm": 200.0,
                            "max_final_keff_delta_pcm": 200.0,
                            "fail_on_violation": True,
                        },
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                        "postprocess": {
                            "command": [
                                sys.executable,
                                str(postprocess),
                                "--input",
                                "{workflow_ascii}",
                                "--output",
                                "{output}",
                                "--sph",
                                "{sph_sidecar}",
                                "--iteration",
                                "{iteration1}",
                            ],
                            "output": "corrected.macrolib.txt",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "run-sph-loop",
                        "--config",
                        str(config),
                        "--summary-json",
                        str(summary),
                        "--bundle-dir",
                        str(bundle_dir),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn(PASS_DECISION, stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], PASS_DECISION)
            self.assertTrue(payload["acceptance_enabled"])
            self.assertTrue(payload["acceptance_passed"])
            self.assertEqual(
                payload["acceptance_decision"],
                "openmc2donjon_sph_loop_acceptance_passed",
            )
            preflight = payload["flux_map_preflight"]
            self.assertTrue(preflight["passed"])
            self.assertEqual(preflight["map_kind"], "scalar_flux_map")
            self.assertEqual(preflight["mixture_count"], 2)
            self.assertEqual(preflight["energy_groups"], 2)
            self.assertTrue(preflight["mgxs_energy_bounds_present"])
            self.assertEqual(preflight["mgxs_energy_bounds_order"], "ascending")
            self.assertEqual(preflight["mgxs_energy_bounds_error_count"], 0)
            self.assertIsNone(preflight["mgxs_energy_mesh_id"])
            self.assertTrue(preflight["mgxs_declared_mixture_order"])
            self.assertEqual(preflight["mgxs_source_domain_indices"], [1, 2])
            self.assertEqual(preflight["mgxs_source_domain_order_errors"], [])
            self.assertEqual(preflight["mgxs_calculations"], 2)
            self.assertEqual(preflight["mgxs_volume_attributes"], 2)
            self.assertEqual(preflight["mgxs_volume_defaulted"], 0)
            self.assertEqual(preflight["mgxs_volume_nonpositive"], 0)
            self.assertEqual(preflight["mgxs_fissionable_calculations"], 1)
            self.assertEqual(preflight["mgxs_h_factor_datasets"], 1)
            self.assertEqual(preflight["mgxs_h_factor_missing"], 0)
            self.assertEqual(preflight["mgxs_h_factor_invalid"], 0)
            self.assertEqual(preflight["scalar_flux_ids"], [2, 4])
            self.assertEqual(preflight["reference_flux_shape"], [2, 2])
            self.assertEqual(preflight["reference_flux_group_order"], "mgxs_donjon")
            self.assertEqual(preflight["reference_flux_mixture_names"], ["fuel", "moderator"])
            self.assertEqual(preflight["errors"], [])
            metadata = payload["artifact_metadata"]
            self.assertEqual(metadata["reference_flux"]["group_order"], "mgxs_donjon")
            self.assertEqual(
                metadata["reference_flux"]["std_dev_dataset"],
                "openmc_volume_flux_std_dev",
            )
            self.assertAlmostEqual(
                metadata["reference_flux"]["std_dev_max_rel"],
                0.01,
            )
            self.assertEqual(
                metadata["reference_flux"]["mixture_names"],
                ["fuel", "moderator"],
            )
            self.assertEqual(len(metadata["workflows"]), 2)
            self.assertEqual(
                metadata["workflows"][0]["donjon_volume_flux"]["group_order"],
                "mgxs_donjon",
            )
            self.assertEqual(
                metadata["workflows"][0]["donjon_volume_flux"]["mixture_names"],
                ["fuel", "moderator"],
            )
            self.assertEqual(
                metadata["workflows"][0]["sph_sidecar"]["group_order"],
                "mgxs_donjon",
            )
            self.assertEqual(
                metadata["final_sph_sidecar"]["group_order"],
                "mgxs_donjon",
            )
            production_audit = payload["production_audit"]
            self.assertEqual(
                production_audit["reference"]["std_dev_dataset"],
                "openmc_volume_flux_std_dev",
            )
            self.assertTrue(production_audit["passed"])
            self.assertEqual(production_audit["errors"], [])
            self.assertEqual(
                production_audit["openmc_xs_policy"],
                "fixed base MGXS; only SPH/NSPH factors are iterated",
            )
            self.assertEqual(
                production_audit["reference"]["mixture_names"],
                ["fuel", "moderator"],
            )
            self.assertEqual(
                production_audit["flux_map"]["mixture_flux_map"],
                [
                    {"mixture": "fuel", "scalar_flux_id": 2},
                    {"mixture": "moderator", "scalar_flux_id": 4},
                ],
            )
            self.assertEqual(
                production_audit["flux_map"]["mgxs_source_domain_indices"],
                [1, 2],
            )
            self.assertTrue(
                production_audit["flux_map"]["mgxs_energy_bounds_present"]
            )
            self.assertIsNone(production_audit["flux_map"]["mgxs_energy_mesh_id"])
            self.assertEqual(production_audit["flux_map"]["mgxs_volume_defaulted"], 0)
            self.assertEqual(production_audit["flux_map"]["mgxs_h_factor_missing"], 0)
            self.assertEqual(production_audit["artifact_counts"]["workflows"], 2)
            self.assertTrue(payload["acceptance"]["passed"])
            self.assertEqual(len(payload["acceptance"]["checks"]), 10)
            self.assertTrue(
                _acceptance_passed(payload, "require_reference_flux_std_dev")
            )
            self.assertAlmostEqual(
                _acceptance_actual(payload, "max_reference_flux_std_dev_rel"),
                0.01,
            )
            self.assertEqual(
                payload["quality"]["initial_flux_ratio_max_residual"],
                1.0,
            )
            self.assertEqual(payload["quality"]["final_flux_ratio_max_residual"], 1.0)
            self.assertEqual(
                payload["quality"]["final_to_initial_flux_residual_ratio"],
                1.0,
            )
            self.assertFalse(payload["quality"]["clipping_observed"])
            self.assertEqual(payload["quality"]["final_clipped_count"], 0)
            self.assertIsInstance(payload["quality"]["final_worst_residual_bin"], dict)
            self.assertEqual(len(payload["quality"]["final_worst_residual_bins"]), 4)
            self.assertEqual(payload["quality"]["final_clipped_bins"], [])
            self.assertIn("worst_residual_bins", payload["convergence"][0])
            self.assertEqual(payload["iterations"], 2)
            self.assertEqual(len(payload["solves"]), 3)
            self.assertGreater(payload["solves"][0]["result_bytes"], 0)
            self.assertEqual(payload["solves"][0]["flux_vector_count"], 2)
            self.assertEqual(payload["solves"][0]["flux_unknown_count"], 4)
            self.assertAlmostEqual(payload["solves"][0]["keff"], 1.0)
            self.assertAlmostEqual(payload["solves"][1]["keff"], 1.001)
            self.assertEqual(len(payload["workflows"]), 2)
            self.assertEqual(len(payload["postprocesses"]), 2)
            self.assertGreater(payload["postprocesses"][0]["output_bytes"], 0)
            self.assertGreater(payload["postprocesses"][0]["block_count"], 0)
            self.assertEqual(payload["final_solve"]["iteration"], 2)
            self.assertAlmostEqual(payload["final_solve"]["keff"], 1.002)
            self.assertEqual(payload["final_solve"]["flux_vector_count"], 2)
            self.assertEqual(payload["final_solve"]["flux_unknown_count"], 4)
            self.assertEqual(len(payload["audit_rows"]), 3)
            self.assertEqual(payload["audit_rows"][0]["stage"], "iteration")
            self.assertEqual(payload["audit_rows"][0]["iteration"], 1)
            self.assertAlmostEqual(payload["audit_rows"][0]["keff"], 1.0)
            self.assertIn("worst_residual_mixture", payload["audit_rows"][0])
            self.assertIsNotNone(payload["audit_rows"][0]["worst_residual_group"])
            self.assertAlmostEqual(payload["audit_rows"][1]["sph_maximum"], 2.0)
            self.assertLessEqual(
                _acceptance_actual(payload, "max_final_keff_delta_pcm"),
                200.0,
            )
            self.assertEqual(payload["audit_rows"][2]["stage"], "final")
            self.assertEqual(payload["audit_rows"][2]["iteration"], 2)
            self.assertAlmostEqual(payload["audit_rows"][2]["keff"], 1.002)
            self.assertTrue((root / "loop_run/iter00_initial/out.macrolib.txt").exists())
            self.assertTrue((root / "loop_run/iter00_solve/solver.stdout.txt").exists())
            self.assertTrue((root / "loop_run/iter01_solve/solver.stdout.txt").exists())
            self.assertTrue((root / "loop_run/iter02_solve/solver.stdout.txt").exists())
            audit_csv = root / "sph_loop_audit.csv"
            audit_text = root / "sph_loop_audit.txt"
            self.assertEqual(Path(payload["audit_csv"]), audit_csv)
            self.assertEqual(Path(payload["audit_text"]), audit_text)
            self.assertEqual(Path(payload["bundle_manifest"]), bundle_dir / "manifest.json")
            self.assertEqual(Path(payload["run_script"]), run_script)
            self.assertTrue(audit_csv.exists())
            self.assertTrue(audit_text.exists())
            with audit_csv.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["stage"] for row in rows], ["iteration", "iteration", "final"])
            self.assertTrue(rows[0]["worst_residual_mixture"])
            self.assertTrue(rows[0]["worst_residual_group"])
            self.assertTrue(rows[0]["worst_residual_raw_update"])
            self.assertEqual(rows[2]["keff"], "1.002")
            audit_text_content = audit_text.read_text(encoding="utf-8")
            self.assertIn("OpenMC-to-DONJON SPH loop audit", audit_text_content)
            self.assertIn("Flux-map preflight: PASS", audit_text_content)
            self.assertIn("Artifact metadata:", audit_text_content)
            self.assertIn("iter1 donjon_volume_flux", audit_text_content)
            self.assertIn("group_order=mgxs_donjon", audit_text_content)
            self.assertIn("worst_bin", audit_text_content)
            self.assertIn("Final worst residual bins", audit_text_content)
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
            self.assertEqual(
                set(labels),
                {
                    "sph-loop-config",
                    "sph-loop-run-script",
                    "sph-input-h5",
                    "sph-loop-final-ascii",
                    "sph-loop-final-sph-sidecar",
                    "sph-loop-summary",
                    "sph-loop-audit-csv",
                    "sph-loop-audit-text",
                },
            )
            self.assertEqual(labels["sph-loop-summary"]["summary_schema"], "openmc2donjon.sph-loop.v1")
            self.assertTrue((bundle_dir / labels["sph-loop-run-script"]["bundled_path"]).exists())
            self.assertEqual(labels["sph-loop-summary"]["summary_decision"], PASS_DECISION)
            self.assertTrue(labels["sph-loop-summary"]["acceptance_passed"])
            self.assertEqual(
                labels["sph-loop-summary"]["acceptance_decision"],
                "openmc2donjon_sph_loop_acceptance_passed",
            )
            self.assertTrue((bundle_dir / labels["sph-loop-audit-csv"]["bundled_path"]).exists())

            final_sph = root / "loop_run/iter02_sph/next_sph.sidecar.h5"
            expected = np.asarray([[2.0, 2.0], [2.0, 2.0]])
            with h5py.File(final_sph, "r") as h5:
                np.testing.assert_allclose(h5["sph"][:], expected)
                self.assertEqual(h5.attrs["sph_kind"], "sph-loop-iter2")
                self.assertEqual(h5["sph"].attrs["group_order"], "mgxs_donjon")

            final_macrolib = read_macrolib_ascii(
                root / "loop_run/iter02_sph/corrected.macrolib.txt"
            )
            self.assertIsNotNone(final_macrolib.sph)
            np.testing.assert_allclose(final_macrolib.sph, expected)

    def test_convergence_tolerance_stops_loop_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 4,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "convergence": {
                            "sph_change_tolerance": 1.0e-12,
                            "flux_ratio_tolerance": 1.0e-12,
                            "min_iterations": 1,
                        },
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            rc = cli_main(
                [
                    "run-sph-loop",
                    "--config",
                    str(config),
                    "--summary-json",
                    str(summary),
                ]
            )

            self.assertEqual(rc, 0)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["iterations"], 4)
            self.assertEqual(payload["completed_iterations"], 1)
            self.assertTrue(payload["convergence_enabled"])
            self.assertTrue(payload["converged"])
            self.assertEqual(payload["stop_reason"], "converged")
            self.assertEqual(len(payload["workflows"]), 1)
            self.assertEqual(len(payload["solves"]), 2)
            self.assertEqual(payload["final_solve"]["iteration"], 1)
            self.assertEqual(len(payload["convergence"]), 1)
            self.assertEqual(payload["convergence"][0]["iteration"], 1)
            self.assertAlmostEqual(payload["convergence"][0]["sph_max_rel_change"], 0.0)
            self.assertAlmostEqual(
                payload["convergence"][0]["flux_ratio_max_residual"],
                0.0,
            )
            self.assertAlmostEqual(
                payload["quality"]["final_worst_residual_bin"]["residual"],
                0.0,
            )
            self.assertEqual(len(payload["audit_rows"]), 2)
            self.assertEqual(payload["audit_rows"][0]["stage"], "iteration")
            self.assertEqual(payload["audit_rows"][1]["stage"], "final")
            self.assertAlmostEqual(payload["audit_rows"][0]["keff"], 1.0)
            self.assertAlmostEqual(payload["audit_rows"][1]["keff"], 1.001)

    def test_acceptance_violation_can_fail_cli_after_writing_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {
                            "require_final_solve": True,
                            "max_final_keff_delta_pcm": 0.001,
                            "fail_on_violation": True,
                        },
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(
                        [
                            "run-sph-loop",
                            "--config",
                            str(config),
                            "--summary-json",
                            str(summary),
                        ]
                    )

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("acceptance criteria failed", stderr.getvalue())
            self.assertIn("max_final_keff_delta_pcm", stderr.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertTrue(payload["acceptance_enabled"])
            self.assertFalse(payload["acceptance_passed"])
            self.assertEqual(
                payload["acceptance_decision"],
                "openmc2donjon_sph_loop_acceptance_failed",
            )
            self.assertEqual(len(payload["audit_rows"]), 2)
            self.assertGreater(
                _acceptance_actual(payload, "max_final_keff_delta_pcm"),
                0.001,
            )

    def test_production_acceptance_preset_expands_to_hard_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "convergence": {
                            "sph_change_tolerance": 1.0e-12,
                            "flux_ratio_tolerance": 1.0e-12,
                            "min_iterations": 1,
                        },
                        "acceptance": {"preset": "production"},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            rc = cli_main(
                [
                    "run-sph-loop",
                    "--config",
                    str(config),
                    "--summary-json",
                    str(summary),
                ]
            )

            self.assertEqual(rc, 0)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertTrue(payload["acceptance_enabled"])
            self.assertTrue(payload["acceptance_passed"])
            self.assertEqual(
                payload["acceptance_decision"],
                "openmc2donjon_sph_loop_acceptance_passed",
            )
            check_names = {
                item["name"] for item in payload["acceptance"]["checks"]
            }
            self.assertEqual(
                check_names,
                {
                    "min_completed_iterations",
                    "require_final_solve",
                    "require_converged",
                    "require_artifact_metadata_alignment",
                    "require_production_audit",
                    "require_mgxs_explicit_volumes",
                    "require_mgxs_h_factor",
                    "require_mgxs_energy_bounds",
                    "require_mgxs_energy_bounds_consistency",
                    "max_mgxs_scatter_row_balance_rel",
                    "max_mgxs_chi_sum_error",
                    "require_mgxs_adf_face_consistency",
                    "max_mgxs_transport_p1_rel",
                    "max_sph_rel_change",
                    "max_flux_ratio_residual",
                    "max_final_to_initial_flux_residual_ratio",
                    "max_final_clipped_fraction",
                    "max_final_clipped_count",
                },
            )
            self.assertEqual(_acceptance_actual(payload, "max_final_clipped_count"), 0.0)
            self.assertLess(
                _acceptance_actual(payload, "max_mgxs_scatter_row_balance_rel"),
                1.0e-12,
            )
            self.assertEqual(
                _acceptance_actual(payload, "max_mgxs_chi_sum_error"),
                0.0,
            )
            self.assertEqual(
                _acceptance_actual(payload, "max_mgxs_transport_p1_rel"),
                0.0,
            )
            self.assertEqual(
                _acceptance_actual(payload, "max_final_to_initial_flux_residual_ratio"),
                0.0,
            )
            self.assertTrue(payload["production_audit"]["passed"])
            audit_checks = {
                item["name"]: item for item in payload["production_audit"]["checks"]
            }
            self.assertTrue(audit_checks["flux_map_preflight_passed"]["passed"])
            self.assertTrue(audit_checks["final_sph_sidecar_present"]["passed"])

    def test_production_acceptance_preset_rejects_missing_energy_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs, with_energy_bounds=False)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {"preset": "production"},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("/energy_bounds dataset is required", stderr.getvalue())
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_flux_map_preflight_rejects_state_energy_bounds_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "stateful_mgxs.h5"
            reference = root / "reference_flux.h5"
            _write_stateful_mgxs_with_state_bounds(mgxs, mismatch=True)
            _write_reference_flux(
                reference,
                mixture_names=("fuel",),
                values=np.asarray([[80.0, 800.0]]),
            )

            report = build_flux_map_preflight_report(
                input_h5=mgxs,
                reference_flux=f"{reference}::openmc_volume_flux",
                map_h5=None,
                scalar_flux_ids={"fuel": 2},
                scalar_flux_column=0,
                require_mgxs_energy_bounds=True,
                require_mgxs_energy_bounds_consistency=True,
            )

        self.assertFalse(report.passed)
        self.assertEqual(report.mgxs_energy_bounds_local_count, 2)
        self.assertEqual(report.mgxs_energy_bounds_consistency_error_count, 1)
        self.assertTrue(
            any("fuel/states/00000002/energy_bounds" in error for error in report.errors)
        )

    def test_flux_map_preflight_reports_nu_ratio_warning_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            with h5py.File(mgxs, "a") as h5:
                h5["mixtures/fuel/nu_fission"][:] = np.array([0.1, 0.03])

            report = build_flux_map_preflight_report(
                input_h5=mgxs,
                reference_flux=f"{reference}::openmc_volume_flux",
                map_h5=None,
                scalar_flux_ids={"fuel": 2, "moderator": 4},
                scalar_flux_column=0,
            )

        self.assertTrue(report.passed, report.errors)
        self.assertEqual(report.mgxs_nu_ratio_checked_bins, 2)
        self.assertEqual(report.mgxs_nu_ratio_warning_count, 1)
        self.assertTrue(
            any("nu_fission/fission" in warning for warning in report.warnings)
        )

    def test_acceptance_rejects_unknown_energy_mesh_when_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {
                            "require_known_mesh": True,
                            "fail_on_violation": True,
                        },
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("known energy mesh", stderr.getvalue())
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_production_acceptance_preset_fails_on_defaulted_volume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            _write_mgxs(mgxs, with_volume=False)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {"preset": "production"},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(
                        [
                            "run-sph-loop",
                            "--config",
                            str(config),
                            "--summary-json",
                            str(summary),
                        ]
                    )

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("require_mgxs_explicit_volumes", stderr.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["flux_map_preflight"]["mgxs_volume_defaulted"], 2)
            self.assertFalse(payload["acceptance_passed"])
            checks = {item["name"]: item for item in payload["acceptance"]["checks"]}
            self.assertFalse(checks["require_mgxs_explicit_volumes"]["passed"])

    def test_production_acceptance_preset_fails_on_missing_h_factor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            _write_mgxs(mgxs, with_h_factor=False)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": True,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {"preset": "production"},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(
                        [
                            "run-sph-loop",
                            "--config",
                            str(config),
                            "--summary-json",
                            str(summary),
                        ]
                    )

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("require_mgxs_h_factor", stderr.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["flux_map_preflight"]["mgxs_h_factor_missing"], 1)
            self.assertFalse(payload["acceptance_passed"])
            checks = {item["name"]: item for item in payload["acceptance"]["checks"]}
            self.assertFalse(checks["require_mgxs_h_factor"]["passed"])

    def test_production_acceptance_preset_fails_without_final_solve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_exact_donjon_solver.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_exact_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "final_solve": False,
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {"preset": "production"},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(
                        [
                            "run-sph-loop",
                            "--config",
                            str(config),
                            "--summary-json",
                            str(summary),
                        ]
                    )

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("acceptance criteria failed", stderr.getvalue())
            self.assertIn("require_final_solve", stderr.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertFalse(payload["acceptance_passed"])
            failed = [
                item["name"]
                for item in payload["acceptance"]["checks"]
                if not item["passed"]
            ]
            self.assertIn("require_final_solve", failed)

    def test_flux_map_preflight_rejects_duplicate_unknowns_before_solving(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 2},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("duplicate scalar flux id mapping", stderr.getvalue())
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_reference_flux_preflight_rejects_missing_mixture_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux_without_mixture_names(reference)
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("reference flux HDF5 must declare mixture_names", stderr.getvalue())
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_production_preflight_rejects_mgxs_source_domain_order_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs, source_domain_indices=(2, 1))
            _write_reference_flux(reference)
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {
                            "require_production_audit": True,
                            "fail_on_violation": True,
                        },
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn(
                "source_domain_index 2 does not match /mixture_names position 1",
                stderr.getvalue(),
            )
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_reference_flux_preflight_rejects_mixture_name_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference, mixture_names=("fuel", "wrong"))
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn(
                "reference flux mixture names do not match MGXS declared order",
                stderr.getvalue(),
            )
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_reference_flux_preflight_rejects_reordered_mixture_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference, mixture_names=("moderator", "fuel"))
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn(
                "reference flux mixture names do not match MGXS declared order",
                stderr.getvalue(),
            )
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_reference_flux_preflight_rejects_missing_group_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference, group_order=None)
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("reference flux HDF5 must declare group_order", stderr.getvalue())
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_reference_flux_preflight_rejects_shape_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(
                reference,
                values=np.asarray([[[80.0], [800.0]], [[80.0], [800.0]]]),
            )
            _write_fake_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn(
                "reference flux shape does not match MGXS mixture/group order",
                stderr.getvalue(),
            )
            self.assertFalse((root / "loop_run/iter00_solve").exists())

    def test_solver_contract_rejects_empty_flux_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "empty_result_solver.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_empty_result_solver(solver)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                            ],
                            "result": "donjon_flux.result",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("solver result contract failed for iteration 0", stderr.getvalue())
            self.assertFalse((root / "loop_run/iter01_sph").exists())

    def test_postprocess_contract_rejects_empty_ascii_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            postprocess = root / "empty_postprocess.py"
            config = root / "loop.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_fake_solver(solver)
            _write_empty_postprocess(postprocess)
            config.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.sph-loop-config.v1",
                        "input_h5": "mgxs.h5",
                        "output_dir": "loop_run",
                        "reference_flux": "reference_flux.h5::openmc_volume_flux",
                        "iterations": 1,
                        "format": "macrolib",
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "solver": {
                            "command": [
                                sys.executable,
                                str(solver),
                                "--macrolib",
                                "{ascii_input}",
                                "--result",
                                "{result}",
                                "--iteration",
                                "{iteration}",
                            ],
                            "result": "donjon_flux.result",
                        },
                        "postprocess": {
                            "command": [
                                sys.executable,
                                str(postprocess),
                                "--output",
                                "{output}",
                            ],
                            "output": "corrected.macrolib.txt",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    cli_main(["run-sph-loop", "--config", str(config)])

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("postprocess output contract failed for iteration 1", stderr.getvalue())
            self.assertTrue((root / "loop_run/iter01_sph/next_sph.sidecar.h5").exists())


def _write_mgxs(
    path: Path,
    *,
    source_domain_indices: tuple[int, int] = (1, 2),
    with_volume: bool = True,
    with_h_factor: bool = True,
    with_energy_bounds: bool = True,
) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        if with_energy_bounds:
            h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        h5.create_dataset("mixture_names", data=np.asarray(["fuel", "moderator"], dtype="S"))
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        moderator = mixtures.create_group("moderator")
        fuel.attrs["source_domain_index"] = source_domain_indices[0]
        fuel.attrs["source_domain_id"] = 101
        fuel.attrs["source_domain_type"] = "cell"
        moderator.attrs["source_domain_index"] = source_domain_indices[1]
        moderator.attrs["source_domain_id"] = 102
        moderator.attrs["source_domain_type"] = "cell"
        _write_mixture(
            fuel,
            fissionable=True,
            with_volume=with_volume,
            with_h_factor=with_h_factor,
        )
        _write_mixture(
            moderator,
            fissionable=False,
            with_volume=with_volume,
            with_h_factor=with_h_factor,
        )


def _write_stateful_mgxs_with_state_bounds(path: Path, *, mismatch: bool) -> None:
    root_bounds = np.array([1.0e-5, 1.0, 1.0e7])
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=root_bounds)
        h5.create_dataset("mixture_names", data=np.asarray(["fuel"], dtype="S"))
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["source_domain_index"] = 1
        fuel.attrs["source_domain_id"] = 101
        fuel.attrs["source_domain_type"] = "cell"
        fuel.attrs["volume"] = 10.0
        states = fuel.create_group("states")
        for index in range(1, 3):
            state = states.create_group(f"{index:08d}")
            state_bounds = root_bounds.copy()
            if mismatch and index == 2:
                state_bounds[1] = 0.9
            state.create_dataset("energy_bounds", data=state_bounds)
            _write_mixture(state, fissionable=True)


def _write_mixture(
    group,
    *,
    fissionable: bool,
    with_volume: bool = True,
    with_h_factor: bool = True,
) -> None:
    group.attrs["fissionable"] = bool(fissionable)
    if with_volume:
        group.attrs["volume"] = 10.0
    group.create_dataset("total", data=np.array([0.5, 0.6]))
    group.create_dataset("transport_total", data=np.array([0.5, 0.7]))
    group.create_dataset("absorption", data=np.array([0.1, 0.2]))
    group.create_dataset("fission", data=np.array([0.01, 0.02]) if fissionable else np.zeros(2))
    group.create_dataset(
        "nu_fission",
        data=np.array([0.025, 0.05]) if fissionable else np.zeros(2),
    )
    if fissionable and with_h_factor:
        group.create_dataset("kappa_fission", data=np.array([3.2e-12, 3.1e-12]))
    group.create_dataset("chi", data=np.array([1.0, 0.0]) if fissionable else np.zeros(2))
    group.create_dataset(
        "scatter_matrix",
        data=np.asarray([[[0.3, 0.1], [0.0, 0.4]]]),
    )


def _write_reference_flux(
    path: Path,
    *,
    mixture_names: tuple[str, ...] = ("fuel", "moderator"),
    group_order: str | None = "mgxs_donjon",
    values: np.ndarray | None = None,
    std_dev: np.ndarray | None = None,
) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset(
            "openmc_volume_flux",
            data=(
                np.asarray([[80.0, 800.0], [80.0, 800.0]])
                if values is None
                else np.asarray(values)
            ),
        )
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        if group_order is not None:
            dataset.attrs["group_order"] = group_order
        if std_dev is not None:
            std_dataset = h5.create_dataset(
                "openmc_volume_flux_std_dev",
                data=np.asarray(std_dev),
            )
            std_dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
            if group_order is not None:
                std_dataset.attrs["group_order"] = group_order


def _write_reference_flux_without_mixture_names(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset(
            "openmc_volume_flux",
            data=np.asarray([[80.0, 800.0], [80.0, 800.0]]),
        )
        dataset.attrs["group_order"] = "mgxs_donjon"


def _write_fake_solver(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macrolib", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args()
    if not Path(args.macrolib).exists():
        raise SystemExit(f"missing macrolib input: {args.macrolib}")
    if args.iteration == 0:
        group1 = (1.0, 40.0, 3.0, 80.0)
        group2 = (10.0, 400.0, 30.0, 800.0)
    else:
        group1 = (1.0, 80.0, 3.0, 40.0)
        group2 = (10.0, 800.0, 30.0, 400.0)
    write_flux_dump(Path(args.result), group1, group2)
    print(f"fake DONJON solve iteration={args.iteration} macrolib={args.macrolib}")
    print(f"OPENMC2DONJON FAKE SPH LOOP K-EFFECTIVE {1.0 + 0.001 * args.iteration:.6f}")
    return 0


def write_flux_dump(path: Path, group1: tuple[float, ...], group2: tuple[float, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, values in enumerate((group1, group2), start=1):
        tag = f"{index:08d}"
        lines.append(header(1, 0, 0, -1, tag))
        lines.append(header(1, 0, 2, len(values), tag))
        lines.append("".join(f"{value:16.8E}" for value in values))
    path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")


def header(level: int, flags: int, type_code: int, count: int, trailing: str) -> str:
    return f"-> {level:7d}{flags:8d}{type_code:8d}{count:8d}                                 <-   {trailing}"


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip(),
        encoding="utf-8",
    )


def _write_exact_fake_solver(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macrolib", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args()
    if not Path(args.macrolib).exists():
        raise SystemExit(f"missing macrolib input: {args.macrolib}")
    write_flux_dump(Path(args.result))
    print(f"fake exact DONJON solve iteration={args.iteration} macrolib={args.macrolib}")
    print(f"OPENMC2DONJON FAKE EXACT SPH LOOP K-EFFECTIVE {1.0 + 0.001 * args.iteration:.6f}")
    return 0


def write_flux_dump(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, values in enumerate(((1.0, 80.0, 3.0, 80.0), (10.0, 800.0, 30.0, 800.0)), start=1):
        tag = f"{index:08d}"
        lines.append(header(1, 0, 0, -1, tag))
        lines.append(header(1, 0, 2, len(values), tag))
        lines.append("".join(f"{value:16.8E}" for value in values))
    path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")


def header(level: int, flags: int, type_code: int, count: int, trailing: str) -> str:
    return f"-> {level:7d}{flags:8d}{type_code:8d}{count:8d}                                 <-   {trailing}"


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip(),
        encoding="utf-8",
    )


def _write_fake_postprocess(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sph", required=True)
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args()
    if not Path(args.sph).exists():
        raise SystemExit(f"missing sph sidecar: {args.sph}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.input, output)
    print(f"fake postprocess iteration={args.iteration} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip(),
        encoding="utf-8",
    )


def _write_empty_result_solver(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--macrolib", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    if not Path(args.macrolib).exists():
        raise SystemExit(f"missing macrolib input: {args.macrolib}")
    Path(args.result).parent.mkdir(parents=True, exist_ok=True)
    Path(args.result).write_text("", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip(),
        encoding="utf-8",
    )


def _write_empty_postprocess(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip(),
        encoding="utf-8",
    )


def _acceptance_actual(payload: dict[str, object], name: str) -> float:
    acceptance = payload["acceptance"]
    if not isinstance(acceptance, dict):
        raise AssertionError("acceptance payload is not a JSON object")
    checks = acceptance["checks"]
    if not isinstance(checks, list):
        raise AssertionError("acceptance checks are not a JSON array")
    for item in checks:
        if isinstance(item, dict) and item.get("name") == name:
            value = item.get("actual")
            if not isinstance(value, (int, float)):
                raise AssertionError(f"acceptance check {name!r} has no numeric actual")
            return float(value)
    raise AssertionError(f"missing acceptance check {name!r}")


def _acceptance_passed(payload: dict[str, object], name: str) -> bool:
    acceptance = payload["acceptance"]
    if not isinstance(acceptance, dict):
        raise AssertionError("acceptance payload is not a JSON object")
    checks = acceptance["checks"]
    if not isinstance(checks, list):
        raise AssertionError("acceptance checks are not a JSON array")
    for item in checks:
        if isinstance(item, dict) and item.get("name") == name:
            value = item.get("passed")
            if not isinstance(value, bool):
                raise AssertionError(f"acceptance check {name!r} has no boolean passed")
            return value
    raise AssertionError(f"missing acceptance check {name!r}")


if __name__ == "__main__":
    unittest.main()
