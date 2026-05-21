from __future__ import annotations

from pathlib import Path
import unittest

import h5py


EXPECTED_SCATTER_MGXS = "consistent nu-scatter matrix"


class C5G7RecipeContractTests(unittest.TestCase):
    def test_recipe_declares_locked_scatter_mgxs_type(self) -> None:
        text = (_repo_root() / "scripts" / "c5g7_export_recipe.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(f'"{EXPECTED_SCATTER_MGXS}"', text)
        self.assertIn("def scatter_mgxs_type", text)

    def test_accepted_hdf5_records_locked_scatter_mgxs_type(self) -> None:
        path = (
            _repo_root()
            / "examples"
            / "donjon_openmc2donjon"
            / "c5g7_assembly_p1_adf_production.h5"
        )

        with h5py.File(path, "r") as h5:
            self.assertEqual(h5.attrs["openmc_scatter_mgxs_type"], EXPECTED_SCATTER_MGXS)
            for group in h5["mixtures"].values():
                self.assertEqual(
                    group.attrs["openmc_scatter_mgxs_type"],
                    EXPECTED_SCATTER_MGXS,
                )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
