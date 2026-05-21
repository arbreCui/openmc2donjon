from __future__ import annotations

import contextlib
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
            config = root / "loop.json"
            summary = root / "loop_summary.json"
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
                        "iterations": 2,
                        "format": "macrolib",
                        "damping": 1.0,
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

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
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
            self.assertIn(PASS_DECISION, stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], PASS_DECISION)
            self.assertEqual(payload["iterations"], 2)
            self.assertEqual(len(payload["solves"]), 2)
            self.assertEqual(len(payload["workflows"]), 2)
            self.assertTrue((root / "loop_run/iter00_initial/out.macrolib.txt").exists())
            self.assertTrue((root / "loop_run/iter00_solve/solver.stdout.txt").exists())
            self.assertTrue((root / "loop_run/iter01_solve/solver.stdout.txt").exists())

            final_sph = root / "loop_run/iter02_sph/next_sph.sidecar.h5"
            expected = np.asarray([[2.0, 2.0], [2.0, 2.0]])
            with h5py.File(final_sph, "r") as h5:
                np.testing.assert_allclose(h5["sph"][:], expected)
                self.assertEqual(h5.attrs["sph_kind"], "sph-loop-iter2")

            final_macrolib = read_macrolib_ascii(root / "loop_run/iter02_sph/out.macrolib.txt")
            self.assertIsNotNone(final_macrolib.sph)
            np.testing.assert_allclose(final_macrolib.sph, expected)


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


if __name__ == "__main__":
    unittest.main()
