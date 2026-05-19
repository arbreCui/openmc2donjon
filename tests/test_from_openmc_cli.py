from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py

from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_cli import build_parser, main as from_openmc_main
from openmc2donjon.from_openmc_summary import (
    FROM_OPENMC_SUMMARY_SCHEMA,
    validate_from_openmc_summary_v1,
)


def assert_from_openmc_summary_v1(
    case: unittest.TestCase,
    payload: dict[str, object],
) -> None:
    case.assertEqual(validate_from_openmc_summary_v1(payload), [])


class FromOpenMCCliTests(unittest.TestCase):
    def test_version_option(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            build_parser().parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), "openmc2donjon-from-openmc 0.1.2")

    def test_recipe_to_multicompo_with_kept_hdf5(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        recipe = repo_root / "examples/recipe_export_smoke/minimal_recipe.py"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            statepoint = tmp / "statepoint.fake.h5"
            hdf5 = tmp / "mgxs.h5"
            output = tmp / "out.mcompo.txt"
            summary = tmp / "summary.json"
            statepoint.write_text("fake statepoint\n", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = from_openmc_main(
                    [
                        "--recipe",
                        str(recipe),
                        "--statepoint",
                        str(statepoint),
                        "--keep-hdf5",
                        str(hdf5),
                        "-o",
                        str(output),
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("preflight OK: mixtures=2", stream.getvalue())
            self.assertTrue(hdf5.exists())
            self.assertTrue(output.exists())
            self.assertTrue(summary.exists())

            with h5py.File(hdf5, "r") as h5:
                self.assertEqual(sorted(h5["mixtures"]), ["FUEL_A", "MOD_A"])
                self.assertEqual(h5.attrs["domain_mode"], "recipe_smoke")

            blocks = lcm_ascii.read_lcm_ascii(output)
            names = [block.name for block in blocks if block.name]
            self.assertEqual(names[0], "SIGNATURE")

            payload = json.loads(summary.read_text(encoding="utf-8"))
            assert_from_openmc_summary_v1(self, payload)
            self.assertEqual(payload["schema"], FROM_OPENMC_SUMMARY_SCHEMA)
            self.assertEqual(payload["package_version"], "0.1.2")
            self.assertEqual(payload["recipe"], str(recipe.resolve()))
            self.assertEqual(payload["statepoint"], str(statepoint.resolve()))
            self.assertTrue(payload["loaded_statepoint"])
            self.assertEqual(payload["format"], "multicompo")
            self.assertEqual(payload["hdf5"], str(hdf5))
            self.assertTrue(payload["hdf5_kept"])
            self.assertEqual(payload["output"], str(output))
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["legendre_order"], 0)
            self.assertEqual(payload["mixture_count"], 2)
            self.assertEqual(payload["mixture_names"], ["FUEL_A", "MOD_A"])
            self.assertEqual(payload["state_points"], 1)
            self.assertEqual(payload["burnup_axis"], {"present": False})
            self.assertIsNone(payload["selected_mixtures"])
            self.assertEqual(payload["root_name"], "CPO")
            self.assertIsNone(payload["single_point_burnup"])
            self.assertIsNone(payload["h_factor_default"])


if __name__ == "__main__":
    unittest.main()
