from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest

import h5py

from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_cli import build_parser, main as from_openmc_main


FROM_OPENMC_SUMMARY_V1_KEYS = {
    "burnup_axis",
    "energy_groups",
    "format",
    "h_factor_default",
    "hdf5",
    "hdf5_kept",
    "legendre_order",
    "loaded_statepoint",
    "mixture_count",
    "mixture_names",
    "output",
    "package_version",
    "recipe",
    "root_name",
    "schema",
    "selected_mixtures",
    "single_point_burnup",
    "state_points",
    "statepoint",
}


def assert_from_openmc_summary_v1(
    case: unittest.TestCase,
    payload: dict[str, Any],
) -> None:
    case.assertEqual(set(payload), FROM_OPENMC_SUMMARY_V1_KEYS)
    case.assertEqual(payload["schema"], "openmc2donjon.from-openmc-summary.v1")
    case.assertIsInstance(payload["package_version"], str)
    case.assertIsInstance(payload["recipe"], str)
    case.assertTrue(payload["recipe"])
    case.assertTrue(payload["statepoint"] is None or isinstance(payload["statepoint"], str))
    case.assertIsInstance(payload["loaded_statepoint"], bool)
    case.assertIsInstance(payload["hdf5"], str)
    case.assertTrue(payload["hdf5"])
    case.assertIsInstance(payload["hdf5_kept"], bool)
    case.assertIsInstance(payload["output"], str)
    case.assertTrue(payload["output"])
    case.assertIn(payload["format"], {"multicompo", "macrolib"})
    case.assertIsInstance(payload["energy_groups"], int)
    case.assertGreater(payload["energy_groups"], 0)
    case.assertIsInstance(payload["legendre_order"], int)
    case.assertGreaterEqual(payload["legendre_order"], 0)
    case.assertIsInstance(payload["mixture_count"], int)
    case.assertGreaterEqual(payload["mixture_count"], 0)
    case.assertIsInstance(payload["mixture_names"], list)
    case.assertTrue(all(isinstance(name, str) for name in payload["mixture_names"]))
    case.assertEqual(payload["mixture_count"], len(payload["mixture_names"]))
    case.assertIsInstance(payload["state_points"], int)
    case.assertGreaterEqual(payload["state_points"], 0)
    case.assertTrue(
        payload["selected_mixtures"] is None
        or (
            isinstance(payload["selected_mixtures"], list)
            and all(isinstance(name, str) for name in payload["selected_mixtures"])
        )
    )
    case.assertTrue(payload["root_name"] is None or isinstance(payload["root_name"], str))
    case.assertTrue(_is_optional_number(payload["single_point_burnup"]))
    case.assertTrue(_is_optional_number(payload["h_factor_default"]))
    _assert_burnup_axis(case, payload["burnup_axis"])


def _assert_burnup_axis(case: unittest.TestCase, burnup_axis: object) -> None:
    case.assertIsInstance(burnup_axis, dict)
    burnup = burnup_axis
    assert isinstance(burnup, dict)
    case.assertIsInstance(burnup.get("present"), bool)
    if burnup["present"]:
        case.assertEqual(set(burnup), {"count", "present", "values"})
        case.assertIsInstance(burnup["count"], int)
        case.assertIsInstance(burnup["values"], list)
        case.assertEqual(burnup["count"], len(burnup["values"]))
        case.assertTrue(all(_is_number(value) for value in burnup["values"]))
    else:
        case.assertEqual(set(burnup), {"present"})


def _is_optional_number(value: object) -> bool:
    return value is None or _is_number(value)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
            self.assertEqual(payload["schema"], "openmc2donjon.from-openmc-summary.v1")
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
