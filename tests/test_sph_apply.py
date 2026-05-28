from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main
from openmc2donjon.sph_apply import (
    apply_sph_to_openmc_mgxs_hdf5,
    apply_sph_to_hdf5,
    apply_sph_to_mixture_arrays,
    apply_sph_to_scatter_matrix,
)


class SphApplyTests(unittest.TestCase):
    def test_apply_sph_to_mixture_arrays_uses_nsph_divisor(self) -> None:
        sph = np.array([2.0, 0.5])
        scatter = np.array(
            [
                [[4.0, 6.0], [8.0, 10.0]],
                [[0.4, 0.6], [0.8, 1.0]],
            ]
        )
        datasets = {
            "total": np.array([10.0, 20.0]),
            "absorption": np.array([2.0, 3.0]),
            "nu_fission": np.array([1.0, 0.0]),
            "total_std_dev": np.array([0.2, 0.4]),
            "scatter_matrix": scatter,
            "chi": np.array([0.25, 0.75]),
        }

        applied = apply_sph_to_mixture_arrays(datasets, sph)

        np.testing.assert_allclose(applied.datasets["total"], [5.0, 40.0])
        np.testing.assert_allclose(applied.datasets["absorption"], [1.0, 6.0])
        np.testing.assert_allclose(applied.datasets["nu_fission"], [0.5, 0.0])
        np.testing.assert_allclose(applied.datasets["total_std_dev"], [0.1, 0.8])
        np.testing.assert_allclose(applied.datasets["chi"], [0.25, 0.75])
        np.testing.assert_allclose(applied.datasets["scatter_matrix"][0], [[2.0, 3.0], [16.0, 20.0]])
        np.testing.assert_allclose(applied.datasets["scatter_matrix"][1], [[0.2, 0.3], [1.6, 2.0]])
        self.assertEqual(
            applied.scaled_names,
            ("total", "absorption", "nu_fission", "total_std_dev", "scatter_matrix"),
        )

    def test_apply_sph_to_scatter_matrix_supports_openmc_axis_order(self) -> None:
        values = np.array(
            [
                [[2.0, 20.0], [4.0, 40.0]],
                [[6.0, 60.0], [8.0, 80.0]],
            ]
        )

        corrected = apply_sph_to_scatter_matrix(
            values,
            np.array([2.0, 4.0]),
            scatter_axes="from,to,moment",
        )

        np.testing.assert_allclose(
            corrected,
            [
                [[1.0, 10.0], [2.0, 20.0]],
                [[1.5, 15.0], [2.0, 20.0]],
            ],
        )

    def test_apply_sph_to_hdf5_writes_corrected_copy_without_active_sph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            sidecar = root / "sph.h5"
            output = root / "corrected.h5"
            _write_mgxs(mgxs)
            _write_sidecar(sidecar)

            report = apply_sph_to_hdf5(mgxs, sph_source=sidecar, output_h5=output)

            self.assertEqual(report.energy_groups, 2)
            self.assertEqual(report.mixture_names, ("fuel", "moderator"))
            self.assertEqual(report.operator, "divide-xs-by-nsph")
            self.assertEqual(report.scaled_dataset_count, 16)
            self.assertAlmostEqual(report.sph_min, 0.25)
            self.assertAlmostEqual(report.sph_max, 2.0)
            with h5py.File(output, "r") as h5:
                self.assertTrue(bool(h5.attrs["sph_applied"]))
                self.assertEqual(h5.attrs["sph_apply_operator"], "divide-xs-by-nsph")
                fuel = h5["mixtures/fuel"]
                moderator = h5["mixtures/moderator"]
                np.testing.assert_allclose(fuel["total"][:], [5.0, 40.0])
                np.testing.assert_allclose(fuel["absorption"][:], [1.0, 6.0])
                np.testing.assert_allclose(fuel["nu_fission"][:], [0.5, 0.0])
                np.testing.assert_allclose(fuel["H-FACTOR"][:], [50.0, 400.0])
                np.testing.assert_allclose(fuel["total_std_dev"][:], [0.05, 0.4])
                np.testing.assert_allclose(fuel["chi"][:], [0.4, 0.6])
                np.testing.assert_allclose(fuel["scatter_matrix"][0], [[2.0, 3.0], [16.0, 20.0]])
                np.testing.assert_allclose(fuel["applied_sph"][:], [2.0, 0.5])
                self.assertNotIn("sph", fuel)
                np.testing.assert_allclose(moderator["total"][:], [5.0, 24.0])
                np.testing.assert_allclose(moderator["scatter_matrix"][0], [[4.0, 6.0], [32.0, 40.0]])
                np.testing.assert_allclose(moderator["applied_sph"][:], [1.0, 0.25])

    def test_apply_sph_to_hdf5_handles_state_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "states.h5"
            sidecar = root / "sph.h5"
            output = root / "corrected.h5"
            _write_state_mgxs(mgxs)
            _write_sidecar(sidecar, mixture_names=("fuel", "moderator"))

            apply_sph_to_hdf5(mgxs, sph_source=sidecar, output_h5=output)

            with h5py.File(output, "r") as h5:
                fuel = h5["mixtures/fuel"]
                np.testing.assert_allclose(fuel["applied_sph"][:], [2.0, 0.5])
                self.assertNotIn("sph", fuel)
                for state_name in ("00000001", "00000002"):
                    state = fuel["states"][state_name]
                    np.testing.assert_allclose(state["total"][:], [5.0, 40.0])
                    np.testing.assert_allclose(state["applied_sph"][:], [2.0, 0.5])
                    self.assertNotIn("sph", state)

    def test_apply_sph_rejects_nonpositive_factor(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            apply_sph_to_mixture_arrays({"total": np.array([1.0, 2.0])}, np.array([1.0, 0.0]))

    def test_apply_sph_cli_writes_corrected_hdf5_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            sidecar = root / "sph.h5"
            output = root / "corrected.h5"
            summary = root / "apply_summary.json"
            _write_mgxs(mgxs)
            _write_sidecar(sidecar)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = cli_main(
                    [
                        "apply-sph",
                        str(mgxs),
                        "--sph-source",
                        str(sidecar),
                        "-o",
                        str(output),
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("SPH-applied MGXS", stdout.getvalue())
            self.assertIn("openmc2donjon_sph_apply_passed", stdout.getvalue())
            self.assertTrue(output.exists())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "openmc2donjon.sph-apply.v1")
            self.assertEqual(payload["decision"], "openmc2donjon_sph_apply_passed")
            self.assertEqual(payload["operator"], "divide-xs-by-nsph")
            self.assertEqual(payload["mixtures"], ["fuel", "moderator"])
            with h5py.File(output, "r") as h5:
                np.testing.assert_allclose(h5["mixtures/fuel/total"][:], [5.0, 40.0])
                self.assertNotIn("sph", h5["mixtures/fuel"])

    def test_apply_sph_to_openmc_native_mgxs_uses_set_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "openmc_mgxs.h5"
            sidecar = root / "sph.h5"
            output = root / "openmc_mgxs_corrected.h5"
            _write_openmc_native_mgxs(mgxs)
            _write_sidecar(sidecar)

            report = apply_sph_to_openmc_mgxs_hdf5(mgxs, sph_source=sidecar, output_h5=output)

            self.assertEqual(report.input_format, "openmc-mgxs")
            self.assertEqual(report.scaled_dataset_count, 12)
            with h5py.File(output, "r") as h5:
                self.assertTrue(bool(h5.attrs["sph_applied"]))
                self.assertEqual(h5.attrs["sph_apply_input_format"], "openmc-mgxs")
                np.testing.assert_allclose(h5["set1/294K/total"][:], [5.0, 40.0])
                np.testing.assert_allclose(h5["set1/294K/absorption"][:], [1.0, 6.0])
                np.testing.assert_allclose(h5["set1/294K/nu-fission"][:], [0.5, 0.0])
                np.testing.assert_allclose(h5["set1/294K/kappa-fission"][:], [50.0, 400.0])
                np.testing.assert_allclose(h5["set1/294K/chi"][:], [0.4, 0.6])
                np.testing.assert_allclose(
                    h5["set1/294K/scatter_data/scatter_matrix"][:],
                    [2.0, 3.0, 16.0, 20.0],
                )
                np.testing.assert_allclose(
                    h5["set1/294K/scatter_data/multiplicity_matrix"][:],
                    [1.0, 1.0, 1.0, 1.0],
                )
                np.testing.assert_allclose(h5["set2/294K/total"][:], [5.0, 24.0])
                np.testing.assert_allclose(
                    h5["set2/294K/scatter_data/scatter_matrix"][:],
                    [4.0, 6.0, 32.0, 40.0],
                )

    def test_apply_sph_cli_supports_openmc_native_mgxs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "openmc_mgxs.h5"
            sidecar = root / "sph.h5"
            output = root / "openmc_mgxs_corrected.h5"
            _write_openmc_native_mgxs(mgxs)
            _write_sidecar(sidecar)

            with redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "apply-sph",
                        str(mgxs),
                        "--input-format",
                        "openmc-mgxs",
                        "--sph-source",
                        str(sidecar),
                        "-o",
                        str(output),
                    ]
                )

            self.assertEqual(rc, 0)
            with h5py.File(output, "r") as h5:
                np.testing.assert_allclose(h5["set2/294K/total"][:], [5.0, 24.0])


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=[0.0, 1.0, 2.0])
        mixtures = h5.create_group("mixtures")
        _write_mix(mixtures.create_group("fuel"), fissionable=True)
        _write_mix(mixtures.create_group("moderator"), fissionable=False, total=(5.0, 6.0))


def _write_state_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=[0.0, 1.0, 2.0])
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        states = fuel.create_group("states")
        _write_mix(states.create_group("00000001"), fissionable=True)
        _write_mix(states.create_group("00000002"), fissionable=True)
        moderator = mixtures.create_group("moderator")
        _write_mix(moderator.create_group("states").create_group("00000001"), fissionable=False)


def _write_mix(group, *, fissionable: bool, total: tuple[float, float] = (10.0, 20.0)) -> None:
    group.attrs["fissionable"] = fissionable
    group.attrs["scatter_axes"] = "moment,from,to"
    group.create_dataset("total", data=np.array(total))
    group.create_dataset("total_std_dev", data=np.array([0.1, 0.2]))
    group.create_dataset("absorption", data=np.array([2.0, 3.0]))
    group.create_dataset("fission", data=np.array([0.2, 0.0]))
    group.create_dataset("nu_fission", data=np.array([1.0, 0.0]))
    group.create_dataset("H-FACTOR", data=np.array([100.0, 200.0]))
    group.create_dataset("chi", data=np.array([0.4, 0.6]))
    group.create_dataset(
        "scatter_matrix",
        data=np.array([[[4.0, 6.0], [8.0, 10.0]]]),
    )
    group.create_dataset(
        "scatter_matrix_std_dev",
        data=np.array([[[0.04, 0.06], [0.08, 0.10]]]),
    )
    group.create_dataset("sph", data=np.array([9.0, 9.0]))


def _write_sidecar(path: Path, *, mixture_names: tuple[str, ...] = ("fuel", "moderator")) -> None:
    values = np.array([[2.0, 0.5], [1.0, 0.25]])
    with h5py.File(path, "w") as h5:
        h5.attrs["sph_kind"] = "openmc-ce-mg"
        h5.attrs["sph_real"] = True
        h5.attrs["sph_applied"] = False
        dataset = h5.create_dataset("sph", data=values[: len(mixture_names)])
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")
        dataset.attrs["group_order"] = "mgxs_donjon"


def _write_openmc_native_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["filetype"] = np.bytes_("mgxs")
        h5.attrs["energy_groups"] = 2
        h5.attrs["group structure"] = np.array([0.0, 1.0, 2.0])
        h5.create_group("settings")
        _write_openmc_set(h5.create_group("set1"), total=(10.0, 20.0))
        _write_openmc_set(h5.create_group("set2"), total=(5.0, 6.0))


def _write_openmc_set(group, *, total: tuple[float, float]) -> None:
    group.attrs["scatter_format"] = np.bytes_("histogram")
    group.attrs["scatter_shape"] = np.bytes_("[G][G'][Order]")
    group.create_group("kTs").create_dataset("294K", data=294.0)
    temperature = group.create_group("294K")
    temperature.create_dataset("total", data=np.array(total))
    temperature.create_dataset("absorption", data=np.array([2.0, 3.0]))
    temperature.create_dataset("fission", data=np.array([0.2, 0.0]))
    temperature.create_dataset("nu-fission", data=np.array([1.0, 0.0]))
    temperature.create_dataset("kappa-fission", data=np.array([100.0, 200.0]))
    temperature.create_dataset("chi", data=np.array([0.4, 0.6]))
    scatter = temperature.create_group("scatter_data")
    scatter.create_dataset("g_min", data=np.array([1, 1]))
    scatter.create_dataset("g_max", data=np.array([2, 2]))
    scatter.create_dataset("multiplicity_matrix", data=np.array([1.0, 1.0, 1.0, 1.0]))
    scatter.create_dataset("scatter_matrix", data=np.array([4.0, 6.0, 8.0, 10.0]))
