from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.sph_loop_convergence import build_convergence_report


class SphLoopConvergenceTests(unittest.TestCase):
    def test_builds_convergence_metrics_from_sph_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            previous_sph = root / "previous_sph.h5"
            current_sph = root / "current_sph.h5"
            _write_mgxs(mgxs)
            _write_sph_sidecar(previous_sph, [[1.0, 1.0], [1.0, 1.1]])
            _write_sph_sidecar(current_sph, [[1.1, 1.0], [0.9, 1.21]])
            _write_sph_summary(root, raw_min=0.8, raw_max=1.3)

            report = build_convergence_report(
                SimpleNamespace(sph_sidecar=current_sph, output_dir=root),
                input_h5=mgxs,
                previous_sph=previous_sph,
                iteration=2,
                sph_change_tolerance=0.11,
                flux_ratio_tolerance=0.31,
                min_iterations=2,
            )

            self.assertEqual(report.iteration, 2)
            self.assertAlmostEqual(report.sph_max_abs_change, 0.11)
            self.assertAlmostEqual(report.sph_max_rel_change, 0.1)
            self.assertAlmostEqual(report.flux_ratio_max_residual, 0.3)
            self.assertTrue(report.converged)

    def test_uses_unity_previous_sph_and_respects_min_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            current_sph = root / "current_sph.h5"
            _write_mgxs(mgxs)
            _write_sph_sidecar(current_sph, [[1.02, 1.0], [1.0, 0.98]])
            _write_sph_summary(root, raw_min=0.99, raw_max=1.01)

            report = build_convergence_report(
                SimpleNamespace(sph_sidecar=current_sph, output_dir=root),
                input_h5=mgxs,
                previous_sph=None,
                iteration=1,
                sph_change_tolerance=0.05,
                flux_ratio_tolerance=0.05,
                min_iterations=2,
            )

            self.assertAlmostEqual(report.sph_max_abs_change, 0.02)
            self.assertAlmostEqual(report.sph_max_rel_change, 0.02)
            self.assertAlmostEqual(report.flux_ratio_max_residual, 0.01)
            self.assertFalse(report.converged)


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        for name in ("fuel", "moderator"):
            group = mixtures.create_group(name)
            group.attrs["fissionable"] = name == "fuel"
            group.attrs["volume"] = 1.0


def _write_sph_sidecar(path: Path, values: list[list[float]]) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["schema"] = "openmc2donjon.sph-sidecar.v1"
        dataset = h5.create_dataset("sph", data=np.asarray(values, dtype=float))
        dataset.attrs.create(
            "mixture_names",
            np.asarray(("fuel", "moderator"), dtype=h5py.string_dtype("utf-8")),
        )


def _write_sph_summary(path: Path, *, raw_min: float, raw_max: float) -> None:
    (path / "next_sph_summary.json").write_text(
        json.dumps(
            {
                "raw_update_minimum": raw_min,
                "raw_update_maximum": raw_max,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
