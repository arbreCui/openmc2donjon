from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import contextlib
import io
import pickle
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.export_cli import build_parser, main as export_cli_main
from openmc2donjon.export_openmc_mgxs import export_openmc_mgxs_library
from openmc2donjon.multicompo import read_mgxs_hdf5


@dataclass
class FakeDomain:
    name: str
    id: int
    volume: float
    fissionable: bool


class FakeEnergyGroups:
    group_edges = np.array([1.0e-5, 1.0, 1.0e3, 1.0e7])


class FakeMGXS:
    def __init__(self, values: np.ndarray) -> None:
        self._values = np.asarray(values, dtype=float)

    def get_xs(self, **_kwargs: object) -> np.ndarray:
        return self._values


class KeywordOnlyFakeLibrary:
    def __init__(self) -> None:
        self.energy_groups = FakeEnergyGroups()
        self.domains = [
            FakeDomain("ASM/1", 101, 4.0, True),
            FakeDomain("MOD", 102, 2.0, False),
        ]

        scatter_openmc_order = np.arange(18, dtype=float).reshape(3, 3, 2) / 10.0
        self._data = {
            (101, "total"): np.array([0.5, 0.6, 0.7]),
            (101, "absorption"): np.array([0.05, 0.06, 0.07]),
            (101, "fission"): np.array([0.01, 0.02, 0.03]),
            (101, "nu-fission"): np.array([0.025, 0.05, 0.075]),
            (101, "chi"): np.array([1.0, 0.0, 0.0]),
            (101, "scatter matrix"): scatter_openmc_order,
            (101, "transport"): np.array([0.45, 0.55, 0.65]),
            (101, "inverse-velocity"): np.array([1.0e-8, 2.0e-7, 3.0e-6]),
            (102, "total"): np.array([0.2, 0.3, 0.4]),
            (102, "absorption"): np.array([0.01, 0.02, 0.03]),
            (102, "scatter matrix"): np.eye(3),
        }

    def get_mgxs(self, *, domain: FakeDomain, mgxs_type: str) -> FakeMGXS:
        key = (domain.id, mgxs_type)
        if key not in self._data:
            raise KeyError(key)
        return FakeMGXS(self._data[key])


class ExportOpenMCMGXSTests(unittest.TestCase):
    def test_exports_duck_typed_library_to_hdf5_contract(self) -> None:
        library = KeywordOnlyFakeLibrary()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            summary = export_openmc_mgxs_library(
                library,
                path,
                domain_names={101: "ASM/Y1/X1"},
            )
            mixtures, energy_bounds = read_mgxs_hdf5(path)

            with h5py.File(path, "r") as h5:
                fuel_group = h5["mixtures"]["ASM_Y1_X1"]
                scatter_axes = fuel_group.attrs["scatter_axes"]
                stored_scatter = fuel_group["scatter_matrix"][:]
                mod_scatter = h5["mixtures"]["MOD"]["scatter_matrix"][:]

        self.assertEqual(summary.energy_groups, 3)
        self.assertEqual(summary.legendre_order, 1)
        self.assertEqual([domain.name for domain in summary.domains], ["ASM_Y1_X1", "MOD"])
        np.testing.assert_allclose(energy_bounds, [1.0e-5, 1.0, 1.0e3, 1.0e7])

        by_name = {mixture.name: mixture for mixture in mixtures}
        self.assertEqual(set(by_name), {"ASM_Y1_X1", "MOD"})
        self.assertTrue(by_name["ASM_Y1_X1"].fissionable)
        self.assertFalse(by_name["MOD"].fissionable)
        self.assertEqual(by_name["ASM_Y1_X1"].volume, 4.0)
        np.testing.assert_allclose(by_name["ASM_Y1_X1"].transport_total, [0.45, 0.55, 0.65])
        np.testing.assert_allclose(
            by_name["ASM_Y1_X1"].inverse_velocity,
            [1.0e-8, 2.0e-7, 3.0e-6],
        )

        openmc_order = library._data[(101, "scatter matrix")]
        self.assertEqual(scatter_axes, "moment,from,to")
        self.assertEqual(stored_scatter.shape, (2, 3, 3))
        np.testing.assert_allclose(stored_scatter[0], openmc_order[:, :, 0])
        np.testing.assert_allclose(stored_scatter[1], openmc_order[:, :, 1])
        self.assertEqual(mod_scatter.shape, (2, 3, 3))
        np.testing.assert_allclose(mod_scatter[0], np.eye(3))
        np.testing.assert_allclose(mod_scatter[1], np.zeros((3, 3)))

    def test_export_cli_reads_pickled_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pickle_path = Path(tmpdir) / "library.pkl"
            output_path = Path(tmpdir) / "mgxs.h5"
            with pickle_path.open("wb") as fh:
                pickle.dump(KeywordOnlyFakeLibrary(), fh)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = export_cli_main([str(pickle_path), "-o", str(output_path)])

            self.assertEqual(rc, 0)
            self.assertTrue(output_path.exists())
            self.assertIn("exported 2 domains, 3 groups, P1", stream.getvalue())

    def test_export_cli_version_option(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            build_parser().parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), "openmc2donjon-export 0.1.0")


if __name__ == "__main__":
    unittest.main()
