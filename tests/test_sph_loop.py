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


class SphLoopTests(unittest.TestCase):
    def test_cli_runs_configured_two_cycle_sph_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            solver = root / "fake_donjon_solver.py"
            postprocess = root / "fake_postprocess.py"
            config = root / "loop.json"
            summary = root / "loop_summary.json"
            bundle_dir = root / "sph_loop_bundle"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_fake_solver(solver)
            _write_fake_postprocess(postprocess)
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
                        "damping": 1.0,
                        "scalar_flux_map": {"fuel": 2, "moderator": 4},
                        "acceptance": {
                            "min_completed_iterations": 2,
                            "require_final_solve": True,
                            "max_sph_rel_change": 1.0,
                            "max_flux_ratio_residual": 1.0,
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
            self.assertTrue(payload["acceptance"]["passed"])
            self.assertEqual(len(payload["acceptance"]["checks"]), 8)
            self.assertEqual(payload["iterations"], 2)
            self.assertEqual(len(payload["solves"]), 3)
            self.assertEqual(len(payload["workflows"]), 2)
            self.assertEqual(len(payload["postprocesses"]), 2)
            self.assertEqual(payload["final_solve"]["iteration"], 2)
            self.assertEqual(len(payload["audit_rows"]), 3)
            self.assertEqual(payload["audit_rows"][0]["stage"], "iteration")
            self.assertEqual(payload["audit_rows"][0]["iteration"], 1)
            self.assertAlmostEqual(payload["audit_rows"][0]["keff"], 1.0)
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
            self.assertTrue(audit_csv.exists())
            self.assertTrue(audit_text.exists())
            with audit_csv.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["stage"] for row in rows], ["iteration", "iteration", "final"])
            self.assertEqual(rows[2]["keff"], "1.002")
            self.assertIn("OpenMC-to-DONJON SPH loop audit", audit_text.read_text(encoding="utf-8"))
            manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
            labels = {artifact["label"]: artifact for artifact in manifest["artifacts"]}
            self.assertEqual(
                set(labels),
                {
                    "sph-loop-config",
                    "sph-input-h5",
                    "sph-loop-final-ascii",
                    "sph-loop-final-sph-sidecar",
                    "sph-loop-summary",
                    "sph-loop-audit-csv",
                    "sph-loop-audit-text",
                },
            )
            self.assertEqual(labels["sph-loop-summary"]["summary_schema"], "openmc2donjon.sph-loop.v1")
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


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        _write_mixture(mixtures.create_group("fuel"), fissionable=True)
        _write_mixture(mixtures.create_group("moderator"), fissionable=False)


def _write_mixture(group, *, fissionable: bool) -> None:
    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["volume"] = 10.0
    group.create_dataset("total", data=np.array([0.6, 0.8]))
    group.create_dataset("transport_total", data=np.array([0.5, 0.7]))
    group.create_dataset("absorption", data=np.array([0.1, 0.2]))
    group.create_dataset("fission", data=np.array([0.01, 0.02]) if fissionable else np.zeros(2))
    group.create_dataset(
        "nu_fission",
        data=np.array([0.025, 0.05]) if fissionable else np.zeros(2),
    )
    group.create_dataset("chi", data=np.array([1.0, 0.0]) if fissionable else np.zeros(2))
    group.create_dataset(
        "scatter_matrix",
        data=np.asarray([[[0.3, 0.1], [0.0, 0.4]]]),
    )


def _write_reference_flux(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset(
            "openmc_volume_flux",
            data=np.asarray([[80.0, 800.0], [80.0, 800.0]]),
        )
        dataset.attrs["mixture_names"] = np.asarray(("fuel", "moderator"), dtype="S")


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


if __name__ == "__main__":
    unittest.main()
