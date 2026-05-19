from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import h5py

from openmc2donjon import lcm_ascii
from openmc2donjon.from_openmc_cli import build_parser, main as from_openmc_main


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
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("preflight OK: mixtures=2", stream.getvalue())
            self.assertTrue(hdf5.exists())
            self.assertTrue(output.exists())

            with h5py.File(hdf5, "r") as h5:
                self.assertEqual(sorted(h5["mixtures"]), ["FUEL_A", "MOD_A"])
                self.assertEqual(h5.attrs["domain_mode"], "recipe_smoke")

            blocks = lcm_ascii.read_lcm_ascii(output)
            names = [block.name for block in blocks if block.name]
            self.assertEqual(names[0], "SIGNATURE")


if __name__ == "__main__":
    unittest.main()
