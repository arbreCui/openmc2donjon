from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import contextlib
import io
import pickle
import tempfile
import textwrap
import unittest

import h5py
import numpy as np

from openmc2donjon.export_cli import build_parser, main as export_cli_main
from openmc2donjon.export_openmc_mgxs import (
    DomainExportSpec,
    export_openmc_mgxs_library,
)
from openmc2donjon.multicompo import read_mgxs_hdf5


@dataclass
class FakeDomain:
    name: str
    id: int
    volume: float
    fissionable: bool


@dataclass
class FakeMeshDomain:
    name: str
    id: int
    volume: float


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


class SubdomainFakeMGXS:
    def __init__(self, values_by_subdomain: dict[tuple[int, int, int], np.ndarray]) -> None:
        self._values_by_subdomain = values_by_subdomain

    def get_xs(self, **kwargs: object) -> np.ndarray:
        subdomains = kwargs.get("subdomains")
        if not subdomains:
            raise TypeError("subdomains are required")
        subdomain = tuple(subdomains[0])  # type: ignore[index]
        return self._values_by_subdomain[subdomain]


class SubdomainFakeLibrary:
    def __init__(self) -> None:
        self.energy_groups = FakeEnergyGroups()
        self.mesh = FakeMeshDomain("mesh", 201, 1.0)
        self.domains = [self.mesh]
        self._data = {
            "total": {
                (1, 1, 1): np.array([0.5, 0.6, 0.7]),
                (2, 1, 1): np.array([0.8, 0.9, 1.0]),
            },
            "absorption": {
                (1, 1, 1): np.array([0.05, 0.06, 0.07]),
                (2, 1, 1): np.array([0.08, 0.09, 0.10]),
            },
            "nu-fission": {
                (1, 1, 1): np.array([0.025, 0.0, 0.0]),
                (2, 1, 1): np.array([0.0, 0.0, 0.0]),
            },
            "chi": {
                (1, 1, 1): np.array([1.0, 0.0, 0.0]),
                (2, 1, 1): np.array([0.0, 0.0, 0.0]),
            },
            "consistent nu-scatter matrix": {
                (1, 1, 1): np.eye(3),
                (2, 1, 1): np.eye(3) * 2.0,
            },
        }
        self._data["fission"] = self._data["nu-fission"]

    def get_mgxs(self, domain: FakeMeshDomain, mgxs_type: str) -> SubdomainFakeMGXS:
        if domain is not self.mesh or mgxs_type not in self._data:
            raise KeyError((domain, mgxs_type))
        return SubdomainFakeMGXS(self._data[mgxs_type])


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

    def test_exports_ambiguous_two_group_p1_scatter_as_openmc_moment_last(self) -> None:
        class EnergyGroups2:
            group_edges = np.array([1.0e-5, 1.0, 1.0e7])

        class Library2:
            def __init__(self) -> None:
                self.energy_groups = EnergyGroups2()
                self.domain = FakeDomain("fuel", 1, 3.0, True)
                self.domains = [self.domain]
                self.scatter = np.array(
                    [
                        [[0.40, 0.04], [0.03, 0.003]],
                        [[0.02, 0.002], [0.50, 0.05]],
                    ]
                )
                self.data = {
                    "total": np.array([0.5, 0.6]),
                    "absorption": np.array([0.05, 0.06]),
                    "fission": np.array([0.01, 0.02]),
                    "nu-fission": np.array([0.025, 0.05]),
                    "chi": np.array([1.0, 0.0]),
                    "scatter matrix": self.scatter,
                }

            def get_mgxs(self, domain: FakeDomain, mgxs_type: str) -> FakeMGXS:
                if domain is not self.domain or mgxs_type not in self.data:
                    raise KeyError((domain, mgxs_type))
                return FakeMGXS(self.data[mgxs_type])

        library = Library2()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            export_openmc_mgxs_library(library, path)
            with h5py.File(path, "r") as h5:
                stored_scatter = h5["mixtures"]["fuel"]["scatter_matrix"][:]

        self.assertEqual(stored_scatter.shape, (2, 2, 2))
        np.testing.assert_allclose(stored_scatter[0], library.scatter[:, :, 0])
        np.testing.assert_allclose(stored_scatter[1], library.scatter[:, :, 1])

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

    def test_export_cli_reads_recipe_and_statepoint(self) -> None:
        recipe = """
            from dataclasses import dataclass

            import numpy as np
            from openmc2donjon import DomainExportSpec

            class EnergyGroups:
                group_edges = np.array([1.0e-5, 1.0, 1.0e7])

            @dataclass(frozen=True)
            class Domain:
                name: str = "mesh"
                id: int = 9001
                volume: float = 1.0

            class MGXS:
                def __init__(self, values):
                    self.values = np.asarray(values, dtype=float)

                def get_xs(self, **_kwargs):
                    return self.values

            class Library:
                def __init__(self):
                    self.energy_groups = EnergyGroups()
                    self.domain = Domain()
                    self.domains = [self.domain]
                    self.loaded_from = None
                    self.data = {
                        "total": np.array([0.5, 0.6]),
                        "absorption": np.array([0.05, 0.06]),
                        "scatter matrix": np.eye(2),
                    }

                def get_mgxs(self, domain, mgxs_type):
                    if domain is not self.domain or mgxs_type not in self.data:
                        raise KeyError((domain, mgxs_type))
                    return MGXS(self.data[mgxs_type])

            def build_library():
                return Library()

            def load_statepoint(library, statepoint_path):
                library.loaded_from = str(statepoint_path)

            def domain_specs(library):
                return [
                    DomainExportSpec(
                        domain=library.domain,
                        name="ASM_Y01_X01",
                        volume=12.5,
                        attrs={"mesh_index": [1, 1, 1]},
                    )
                ]

            def root_attrs(library):
                return {
                    "workflow": "recipe",
                    "loaded_from": library.loaded_from,
                }
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "recipe.py"
            statepoint_path = Path(tmpdir) / "statepoint.10.h5"
            output_path = Path(tmpdir) / "mgxs.h5"
            recipe_path.write_text(textwrap.dedent(recipe), encoding="utf-8")
            statepoint_path.write_text("fake statepoint marker", encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = export_cli_main(
                    [
                        "--recipe",
                        str(recipe_path),
                        "--statepoint",
                        str(statepoint_path),
                        "-o",
                        str(output_path),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("from recipe", stream.getvalue())
            mixtures, _energy_bounds = read_mgxs_hdf5(output_path)

            with h5py.File(output_path, "r") as h5:
                self.assertEqual(h5.attrs["workflow"], "recipe")
                self.assertEqual(h5.attrs["loaded_from"], str(statepoint_path.resolve()))
                mesh_index = h5["mixtures"]["ASM_Y01_X01"].attrs["mesh_index"]

        self.assertEqual([mixture.name for mixture in mixtures], ["ASM_Y01_X01"])
        self.assertEqual(mixtures[0].volume, 12.5)
        np.testing.assert_array_equal(mesh_index, [1, 1, 1])

    def test_export_cli_recipe_dry_run_without_statepoint_or_output(self) -> None:
        recipe = """
            from dataclasses import dataclass

            import numpy as np

            class EnergyGroups:
                group_edges = np.array([1.0e-5, 1.0, 1.0e7])

            @dataclass(frozen=True)
            class Domain:
                name: str
                id: int
                volume: float

            class Library:
                def __init__(self):
                    self.energy_groups = EnergyGroups()
                    self.domain_type = "cell"
                    self.legendre_order = 1
                    self.mgxs_types = [
                        "total",
                        "absorption",
                        "consistent nu-scatter matrix",
                        "transport",
                    ]
                    self.domains = [
                        Domain("ASM/1", 1, 10.0),
                        Domain("ASM/1", 2, 20.0),
                    ]

            def build_library():
                return Library()

            def domain_names(library):
                return {domain.id: domain.name for domain in library.domains}

            def root_attrs():
                return {"domain_mode": "assembly"}
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "recipe.py"
            recipe_path.write_text(textwrap.dedent(recipe), encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = export_cli_main(["--recipe", str(recipe_path), "--dry-run"])

        output = stream.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("recipe dry-run OK", output)
        self.assertIn("statepoint: none", output)
        self.assertIn("output: dry run; no HDF5 written", output)
        self.assertIn("energy_groups: 2", output)
        self.assertIn("legendre_order: 1", output)
        self.assertIn("domain_type: cell", output)
        self.assertIn("mixtures: 2", output)
        self.assertIn("production_checklist:", output)
        self.assertIn(
            "PASS mgxs-required: total, absorption, and scatter matrix MGXS are declared",
            output,
        )
        self.assertIn("PASS transport: transport MGXS declared", output)
        self.assertIn("WARN fission-source: missing fission, nu-fission, chi", output)
        self.assertIn(
            "PASS domain-mapping: 2 cell domain(s) -> 2 DONJON mixture(s)",
            output,
        )
        self.assertIn("PASS volumes: all selected domains have positive explicit volumes", output)
        self.assertIn("PASS domain-mode: root_attrs include domain_mode", output)
        self.assertIn("ASM_1", output)
        self.assertIn("volume_source=domain", output)
        self.assertIn("duplicate name 'ASM_1' written as 'ASM_1_2'", output)

    def test_export_cli_recipe_dry_run_flags_missing_required_mgxs_types(self) -> None:
        recipe = """
            from dataclasses import dataclass

            import numpy as np

            class EnergyGroups:
                group_edges = np.array([1.0e-5, 1.0, 1.0e7])

            @dataclass(frozen=True)
            class Domain:
                name: str
                id: int

            class Library:
                def __init__(self):
                    self.energy_groups = EnergyGroups()
                    self.domain_type = "cell"
                    self.legendre_order = 0
                    self.mgxs_types = ["total", "transport"]
                    self.domains = [Domain("fuel", 1)]

            def build_library():
                return Library()
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "recipe.py"
            recipe_path.write_text(textwrap.dedent(recipe), encoding="utf-8")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = export_cli_main(["--recipe", str(recipe_path), "--dry-run"])

        output = stream.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("FAIL mgxs-required: missing required MGXS type(s): absorption", output)
        self.assertIn("scatter matrix", output)
        self.assertIn("WARN legendre-order: P0 only", output)
        self.assertIn("WARN volumes: 1 domain(s) use default volume=1.0: fuel", output)
        self.assertIn("WARN domain-mode: root_attrs should include domain_mode", output)

    def test_exports_explicit_subdomain_specs(self) -> None:
        library = SubdomainFakeLibrary()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "assembly.h5"
            export_openmc_mgxs_library(
                library,
                path,
                domain_specs=[
                    DomainExportSpec(
                        domain=library.mesh,
                        name="ASM/Y01/X01",
                        xs_kwargs={"subdomains": [(1, 1, 1)]},
                        volume=10.0,
                        attrs={"mesh_index": [1, 1, 1]},
                    ),
                    {
                        "domain": library.mesh,
                        "name": "ASM/Y01/X02",
                        "xs_kwargs": {"subdomains": [(2, 1, 1)]},
                        "volume": 20.0,
                        "attrs": {"mesh_index": [2, 1, 1]},
                    },
                ],
                root_attrs={"domain_mode": "assembly", "mesh_dimension": 2},
            )
            mixtures, _energy_bounds = read_mgxs_hdf5(path)

            with h5py.File(path, "r") as h5:
                domain_mode = h5.attrs["domain_mode"]
                mesh_dimension = int(h5.attrs["mesh_dimension"])
                mesh_index = h5["mixtures"]["ASM_Y01_X02"].attrs["mesh_index"]

        by_name = {mixture.name: mixture for mixture in mixtures}
        self.assertEqual(domain_mode, "assembly")
        self.assertEqual(mesh_dimension, 2)
        np.testing.assert_array_equal(mesh_index, [2, 1, 1])
        np.testing.assert_allclose(by_name["ASM_Y01_X01"].total, [0.5, 0.6, 0.7])
        np.testing.assert_allclose(by_name["ASM_Y01_X02"].total, [0.8, 0.9, 1.0])
        self.assertEqual(by_name["ASM_Y01_X01"].volume, 10.0)
        self.assertEqual(by_name["ASM_Y01_X02"].volume, 20.0)
        self.assertTrue(by_name["ASM_Y01_X01"].fissionable)
        self.assertFalse(by_name["ASM_Y01_X02"].fissionable)

    def test_export_cli_version_option(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            build_parser().parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), "openmc2donjon-export 0.1.2")


if __name__ == "__main__":
    unittest.main()
