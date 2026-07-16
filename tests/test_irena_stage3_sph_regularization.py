from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "irena30_sph_stage3_fullcore"
    / "regularize_sph_table.py"
)
SPEC = importlib.util.spec_from_file_location("irena30_regularize_sph_table", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_ring1_table(path: Path, *, omit: str | None = None) -> None:
    mixtures = ["R0P00_INT"] + [
        f"R1P{position:02d}_{'DSDF' if position % 2 == 0 else 'INT'}"
        for position in range(6)
    ]
    factors = {
        "R1P00_DSDF": 1.0,
        "R1P02_DSDF": 2.0,
        "R1P04_DSDF": 8.0,
    }
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mixture", "group", "sph"))
        for mixture in mixtures:
            if mixture == omit:
                continue
            for group in (1, 2):
                writer.writerow((mixture, group, factors.get(mixture, 1.0)))


class IrenaStage3SphRegularizationTests(unittest.TestCase):
    def test_symmetry_orbit_uses_120_degree_rotation(self) -> None:
        self.assertEqual(MODULE.symmetry_orbit("R0P00_INT"), "R0_CENTER_INT")
        self.assertEqual(MODULE.symmetry_orbit("R3P01_INT"), "R3O01_INT")
        self.assertEqual(MODULE.symmetry_orbit("R3P07_INT"), "R3O01_INT")
        self.assertEqual(MODULE.symmetry_orbit("R3P13_INT"), "R3O01_INT")

    def test_geometric_mean_is_broadcast_without_global_scaling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "raw.csv"
            output = root / "tied.csv"
            summary = root / "summary.json"
            _write_ring1_table(source)

            payload = MODULE.regularize_sph_table(
                source,
                output,
                summary_json=summary,
            )

            self.assertEqual(payload["mixture_count"], 7)
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["orbit_count"], 3)
            self.assertAlmostEqual(
                payload["input_max_within_orbit_relative_spread"], 7.0
            )
            rows = list(csv.DictReader(output.open(encoding="utf-8")))
            values = {
                (row["mixture"], int(row["group"])): float(row["sph"])
                for row in rows
            }
            expected = 2.0 ** (4.0 / 3.0)
            for position in (0, 2, 4):
                for group in (1, 2):
                    self.assertAlmostEqual(
                        values[(f"R1P{position:02d}_DSDF", group)], expected
                    )
            self.assertNotIn("global_scale", json.loads(summary.read_text()))

    def test_rejects_incomplete_orbits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "raw.csv"
            _write_ring1_table(source, omit="R1P04_DSDF")
            with self.assertRaisesRegex(ValueError, "expected 3"):
                MODULE.regularize_sph_table(source, root / "out.csv")


if __name__ == "__main__":
    unittest.main()
