from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main
from openmc2donjon.zero_flux_fill import fill_zero_flux_groups


GROUPS = 4

# Macrolib storage is ascending energy (index 0 = lowest energy group).
FUEL_TOTAL_ASC = np.array([1.0, 2.0, 3.0, 4.0])
FUEL_ABSORPTION_ASC = np.array([0.1, 0.2, 0.3, 0.4])
FUEL_FISSION_ASC = np.array([0.05, 0.06, 0.07, 0.08])
FUEL_NU_FISSION_ASC = np.array([0.125, 0.15, 0.175, 0.2])
FUEL_SCATTER_ASC = np.arange(32, dtype=float).reshape(4, 4, 2)  # (g_in, g_out, order)
SODIUM_TOTAL_ASC = np.array([5.0, 6.0, 7.0, 8.0])
SODIUM_ABSORPTION_ASC = np.array([0.5, 0.6, 0.7, 0.8])
SODIUM_SCATTER_ASC = 0.5 * np.arange(32, dtype=float).reshape(4, 4, 2)


class _FakeXSData:
    def __init__(
        self,
        name: str,
        *,
        total: np.ndarray,
        absorption: np.ndarray,
        scatter: np.ndarray,
        fission: np.ndarray | None = None,
        nu_fission: np.ndarray | None = None,
        fissionable: bool = False,
        temperatures: tuple[float, ...] = (294.0,),
    ) -> None:
        self.name = name
        self.temperatures = list(temperatures)
        self.fissionable = fissionable
        self.total = [np.asarray(total, dtype=float)]
        self.absorption = [np.asarray(absorption, dtype=float)]
        self.scatter_matrix = [np.asarray(scatter, dtype=float)]
        self.fission = None if fission is None else [np.asarray(fission, dtype=float)]
        self.nu_fission = None if nu_fission is None else [np.asarray(nu_fission, dtype=float)]


class _FakeMGXSLibrary:
    def __init__(self, xsdatas: list[_FakeXSData]) -> None:
        self.xsdatas = list(xsdatas)


@contextmanager
def _fake_openmc(library: _FakeMGXSLibrary):
    class _FakeLoader:
        @staticmethod
        def from_hdf5(path: str) -> _FakeMGXSLibrary:
            return library

    previous = sys.modules.get("openmc")
    sys.modules["openmc"] = types.SimpleNamespace(MGXSLibrary=_FakeLoader)
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop("openmc", None)
        else:
            sys.modules["openmc"] = previous


def _fake_library(*, fuel_orders: int = 2) -> _FakeMGXSLibrary:
    return _FakeMGXSLibrary(
        [
            _FakeXSData(
                "FUEL",
                total=FUEL_TOTAL_ASC,
                absorption=FUEL_ABSORPTION_ASC,
                scatter=FUEL_SCATTER_ASC[:, :, :fuel_orders],
                fission=FUEL_FISSION_ASC,
                nu_fission=FUEL_NU_FISSION_ASC,
                fissionable=True,
            ),
            _FakeXSData(
                "NA",
                total=SODIUM_TOTAL_ASC,
                absorption=SODIUM_ABSORPTION_ASC,
                scatter=SODIUM_SCATTER_ASC,
            ),
        ]
    )


def _fuel_spec(
    *,
    total=(10.0, 20.0, 0.0, 0.0),
    transport=(9.0, 19.0, 0.0, 0.0),
    orders: int = 2,
    with_fission: bool = True,
    label_attr: str = "irena_mixture_label",
) -> dict:
    datasets = {
        "total": total,
        "absorption": (1.0, 2.0, 0.0, 0.0),
        "scatter_matrix": np.full((orders, GROUPS, GROUPS), 9.0),
        "total_std_dev": (0.1, 0.1, 0.1, 0.1),
        "absorption_std_dev": (0.1, 0.1, 0.1, 0.1),
        "scatter_matrix_std_dev": np.full((orders, GROUPS, GROUPS), 0.2),
    }
    if transport is not None:
        datasets["transport_total"] = transport
        datasets["transport_total_std_dev"] = (0.1, 0.1, 0.1, 0.1)
    if with_fission:
        datasets["fission"] = (0.5, 0.5, 0.0, 0.0)
        datasets["fission_std_dev"] = (0.1, 0.1, 0.1, 0.1)
        datasets["nu_fission"] = (1.2, 1.2, 0.0, 0.0)
        datasets["nu_fission_std_dev"] = (0.1, 0.1, 0.1, 0.1)
    return {"attrs": {label_attr: "FUEL", "fissionable": True}, "datasets": datasets}


def _sodium_spec(*, total=(30.0, 40.0, 50.0, 60.0), transport=None) -> dict:
    datasets = {
        "total": total,
        "absorption": (3.0, 4.0, 5.0, 6.0),
        "fission": (0.0, 0.0, 0.0, 0.0),
        "fission_std_dev": (0.1, 0.1, 0.1, 0.1),
        "scatter_matrix": np.full((2, GROUPS, GROUPS), 9.0),
    }
    if transport is not None:
        datasets["transport_total"] = transport
    return {"attrs": {"irena_mixture_label": "NA", "fissionable": False}, "datasets": datasets}


def _write_converter_h5(path: Path, mixtures: dict[str, dict]) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = GROUPS
        root = h5.create_group("mixtures", track_order=True)
        for name, spec in mixtures.items():
            group = root.create_group(name)
            for key, value in spec["attrs"].items():
                group.attrs[key] = value
            for key, value in spec["datasets"].items():
                group.create_dataset(key, data=np.asarray(value, dtype=float))


def _touch_macrolib(root: Path) -> Path:
    macrolib = root / "macrolib.h5"
    macrolib.write_bytes(b"fake macrolib payload")
    return macrolib


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ZeroFluxFillTests(unittest.TestCase):
    def test_fills_zero_total_bins_with_reversed_macrolib_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            output = root / "filled.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec()})
            input_digest = _sha256(mgxs)

            with _fake_openmc(_fake_library()):
                report = fill_zero_flux_groups(mgxs, macrolib=macrolib, output_h5=output)

            self.assertEqual(report.output_h5, output)
            self.assertEqual(report.mixture_count, 1)
            self.assertEqual(report.filled_per_mixture, (("fuel", 2),))
            self.assertEqual(report.total_filled_bins, 2)
            self.assertEqual(_sha256(mgxs), input_digest, "copy mode must not touch the input")
            with h5py.File(output, "r") as h5:
                fuel = h5["mixtures/fuel"]
                # Converter order is descending energy: converter index g maps
                # to ascending macrolib index GROUPS - 1 - g.
                np.testing.assert_array_equal(fuel["total"][:], [10.0, 20.0, 2.0, 1.0])
                np.testing.assert_array_equal(fuel["absorption"][:], [1.0, 2.0, 0.2, 0.1])
                np.testing.assert_array_equal(fuel["fission"][:], [0.5, 0.5, 0.06, 0.05])
                np.testing.assert_array_equal(fuel["nu_fission"][:], [1.2, 1.2, 0.15, 0.125])
                matrix = fuel["scatter_matrix"][:]
                np.testing.assert_array_equal(matrix[0][2], [14.0, 12.0, 10.0, 8.0])
                np.testing.assert_array_equal(matrix[1][2], [15.0, 13.0, 11.0, 9.0])
                np.testing.assert_array_equal(matrix[0][3], [6.0, 4.0, 2.0, 0.0])
                np.testing.assert_array_equal(matrix[1][3], [7.0, 5.0, 3.0, 1.0])
                np.testing.assert_array_equal(matrix[0][0], np.full(GROUPS, 9.0))
                # transport_total = total - P1 out-scatter row sum.
                np.testing.assert_array_equal(
                    fuel["transport_total"][:], [9.0, 19.0, 2.0 - 48.0, 1.0 - 16.0]
                )

    def test_fills_nonpositive_transport_bins_even_when_total_is_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(
                mgxs,
                {
                    "fuel": _fuel_spec(
                        total=(10.0, 20.0, 30.0, 40.0),
                        transport=(9.0, -0.5, 29.0, 0.0),
                    )
                },
            )

            with _fake_openmc(_fake_library()):
                report = fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            self.assertEqual(report.total_filled_bins, 2)
            with h5py.File(mgxs, "r") as h5:
                fuel = h5["mixtures/fuel"]
                np.testing.assert_array_equal(
                    fuel.attrs["zero_flux_filled_groups"], np.array([1, 3], dtype=np.int64)
                )
                np.testing.assert_array_equal(fuel["total"][:], [10.0, 3.0, 30.0, 1.0])

    def test_fission_is_only_filled_for_fissionable_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(
                mgxs,
                {
                    # Non-fissionable material with a fission dataset: untouched.
                    "sodium": _sodium_spec(total=(30.0, 40.0, 0.0, 0.0)),
                    # Fissionable material without a fission dataset: no error.
                    "fuel": _fuel_spec(with_fission=False),
                },
            )

            with _fake_openmc(_fake_library()):
                report = fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            self.assertEqual(report.filled_per_mixture, (("sodium", 2), ("fuel", 2)))
            with h5py.File(mgxs, "r") as h5:
                sodium = h5["mixtures/sodium"]
                np.testing.assert_array_equal(sodium["total"][:], [30.0, 40.0, 6.0, 5.0])
                np.testing.assert_array_equal(sodium["fission"][:], np.zeros(GROUPS))
                np.testing.assert_array_equal(
                    sodium["fission_std_dev"][:], np.full(GROUPS, 0.1)
                )
                self.assertNotIn("fission", h5["mixtures/fuel"])

    def test_filled_bins_get_zero_std_dev(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec()})

            with _fake_openmc(_fake_library()):
                fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            with h5py.File(mgxs, "r") as h5:
                fuel = h5["mixtures/fuel"]
                for key in (
                    "total_std_dev",
                    "absorption_std_dev",
                    "fission_std_dev",
                    "nu_fission_std_dev",
                    "transport_total_std_dev",
                ):
                    np.testing.assert_array_equal(fuel[key][:], [0.1, 0.1, 0.0, 0.0])
                scatter_std = fuel["scatter_matrix_std_dev"][:]
                np.testing.assert_array_equal(scatter_std[:, 2:, :], np.zeros((2, 2, GROUPS)))
                np.testing.assert_array_equal(scatter_std[:, :2, :], np.full((2, 2, GROUPS), 0.2))

    def test_records_fill_attrs_only_on_touched_mixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(
                mgxs,
                {"fuel": _fuel_spec(), "sodium": _sodium_spec()},
            )

            with _fake_openmc(_fake_library()):
                report = fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            self.assertEqual(report.mixture_count, 2)
            self.assertEqual(report.filled_per_mixture, (("fuel", 2),))
            with h5py.File(mgxs, "r") as h5:
                fuel = h5["mixtures/fuel"]
                np.testing.assert_array_equal(
                    fuel.attrs["zero_flux_filled_groups"], np.array([2, 3], dtype=np.int64)
                )
                self.assertEqual(fuel.attrs["zero_flux_fill_source"], str(macrolib))
                sodium = h5["mixtures/sodium"]
                self.assertNotIn("zero_flux_filled_groups", sodium.attrs)
                self.assertNotIn("zero_flux_fill_source", sodium.attrs)

    def test_p0_macrolib_fills_transport_with_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec(orders=1)})

            with _fake_openmc(_fake_library(fuel_orders=1)):
                fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            with h5py.File(mgxs, "r") as h5:
                fuel = h5["mixtures/fuel"]
                np.testing.assert_array_equal(fuel["transport_total"][:], [9.0, 19.0, 2.0, 1.0])

    def test_custom_label_attr_selects_macrolib_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec(label_attr="material_name")})

            with _fake_openmc(_fake_library()):
                report = fill_zero_flux_groups(
                    mgxs,
                    macrolib=macrolib,
                    in_place=True,
                    label_attr="material_name",
                )

            self.assertEqual(report.label_attr, "material_name")
            self.assertEqual(report.total_filled_bins, 2)

    def test_missing_label_attr_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            spec = _fuel_spec()
            del spec["attrs"]["irena_mixture_label"]
            _write_converter_h5(mgxs, {"fuel": spec})

            with _fake_openmc(_fake_library()):
                with self.assertRaises(ValueError) as context:
                    fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            self.assertIn("irena_mixture_label", str(context.exception))
            self.assertIn("fuel", str(context.exception))

    def test_unknown_macrolib_material_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            spec = _fuel_spec()
            spec["attrs"]["irena_mixture_label"] = "MISSING"
            _write_converter_h5(mgxs, {"fuel": spec})

            with _fake_openmc(_fake_library()):
                with self.assertRaises(ValueError) as context:
                    fill_zero_flux_groups(mgxs, macrolib=macrolib, in_place=True)

            self.assertIn("MISSING", str(context.exception))
            self.assertIn("irena_mixture_label", str(context.exception))

    def test_destination_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            output = root / "filled.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec()})

            with _fake_openmc(_fake_library()):
                with self.assertRaises(ValueError):
                    fill_zero_flux_groups(mgxs, macrolib=macrolib)
                with self.assertRaises(ValueError):
                    fill_zero_flux_groups(
                        mgxs, macrolib=macrolib, output_h5=output, in_place=True
                    )
                with self.assertRaises(ValueError):
                    fill_zero_flux_groups(mgxs, macrolib=macrolib, output_h5=mgxs)
                output.write_bytes(b"existing")
                with self.assertRaises(FileExistsError):
                    fill_zero_flux_groups(mgxs, macrolib=macrolib, output_h5=output)
                report = fill_zero_flux_groups(
                    mgxs, macrolib=macrolib, output_h5=output, force=True
                )
            self.assertEqual(report.total_filled_bins, 2)

    def test_cli_fill_zero_flux_writes_copy_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            output = root / "filled.h5"
            summary = root / "summary.json"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec()})
            input_digest = _sha256(mgxs)

            stream = io.StringIO()
            with _fake_openmc(_fake_library()):
                with redirect_stdout(stream):
                    exit_code = cli_main(
                        [
                            "fill-zero-flux",
                            str(mgxs),
                            "--macrolib",
                            str(macrolib),
                            "-o",
                            str(output),
                            "--summary-json",
                            str(summary),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertIn("openmc2donjon_zero_flux_fill_passed", stream.getvalue())
            self.assertEqual(_sha256(mgxs), input_digest)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "openmc2donjon.zero-flux-fill.v1")
            self.assertEqual(payload["decision"], "openmc2donjon_zero_flux_fill_passed")
            self.assertEqual(payload["total_filled_bins"], 2)
            self.assertEqual(payload["filled_per_mixture"], {"fuel": 2})
            self.assertEqual(payload["label_attr"], "irena_mixture_label")
            with h5py.File(output, "r") as h5:
                np.testing.assert_array_equal(
                    h5["mixtures/fuel"]["total"][:], [10.0, 20.0, 2.0, 1.0]
                )

    def test_cli_fill_zero_flux_in_place_edits_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(mgxs, {"fuel": _fuel_spec()})

            stream = io.StringIO()
            with _fake_openmc(_fake_library()):
                with redirect_stdout(stream):
                    exit_code = cli_main(
                        [
                            "fill-zero-flux",
                            str(mgxs),
                            "--macrolib",
                            str(macrolib),
                            "--in-place",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            with h5py.File(mgxs, "r") as h5:
                np.testing.assert_array_equal(
                    h5["mixtures/fuel"]["total"][:], [10.0, 20.0, 2.0, 1.0]
                )

    def test_matches_reference_script_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pristine = root / "pristine.h5"
            reference = root / "reference.h5"
            candidate = root / "candidate.h5"
            macrolib = _touch_macrolib(root)
            _write_converter_h5(
                pristine,
                {
                    "fuel": _fuel_spec(transport=(9.0, -1.0, 0.0, 0.0)),
                    "sodium": _sodium_spec(
                        total=(30.0, 40.0, 50.0, 0.0),
                        transport=(29.0, 39.0, 49.0, 0.0),
                    ),
                    "untouched": _sodium_spec(),
                },
            )
            library = _fake_library()

            shutil.copy2(pristine, reference)
            reference_total = _reference_fill(reference, library, str(macrolib))

            with _fake_openmc(library):
                report = fill_zero_flux_groups(
                    pristine, macrolib=macrolib, output_h5=candidate
                )

            self.assertEqual(report.total_filled_bins, reference_total)
            reference_datasets, reference_attrs = _snapshot(reference)
            candidate_datasets, candidate_attrs = _snapshot(candidate)
            self.assertEqual(sorted(reference_datasets), sorted(candidate_datasets))
            for name, expected in reference_datasets.items():
                actual = candidate_datasets[name]
                self.assertEqual(expected.dtype, actual.dtype, name)
                np.testing.assert_array_equal(actual, expected, err_msg=name)
            self.assertEqual(sorted(reference_attrs), sorted(candidate_attrs))
            for key, expected in reference_attrs.items():
                actual = candidate_attrs[key]
                if isinstance(expected, np.ndarray):
                    self.assertEqual(expected.dtype, actual.dtype, key)
                    np.testing.assert_array_equal(actual, expected, err_msg=str(key))
                else:
                    self.assertEqual(actual, expected, key)


def _snapshot(path: Path) -> tuple[dict, dict]:
    datasets: dict[str, np.ndarray] = {}
    attrs: dict[tuple[str, str], object] = {}
    with h5py.File(path, "r") as h5:
        for key, value in h5.attrs.items():
            attrs[("/", str(key))] = value

        def collect(name: str, obj) -> None:
            if isinstance(obj, h5py.Dataset):
                datasets[name] = obj[()]
            for key, value in obj.attrs.items():
                attrs[(name, str(key))] = value

        h5.visititems(collect)
    return datasets, attrs


def _reference_fill(mgxs_path: Path, library: _FakeMGXSLibrary, macrolib_arg: str) -> int:
    """Verbatim port of examples/irena30_zrefl_hex/fill_zero_flux_groups.py
    (pre-shim revision) used as the behavioral reference."""

    def dense_scatter(xsdata, temp_idx: int) -> np.ndarray:
        matrix = np.transpose(np.asarray(xsdata.scatter_matrix[temp_idx]), (2, 0, 1))
        return matrix[:, ::-1, ::-1]

    def group_vector(values) -> np.ndarray:
        return np.asarray(values, dtype=float)[::-1]

    def fill_dataset(group, fill: np.ndarray, key: str, values: np.ndarray) -> None:
        data = group[key][:]
        data[fill] = values[fill]
        group[key][...] = data
        std_key = f"{key}_std_dev"
        if std_key in group:
            std = group[std_key][:]
            std[fill] = 0.0
            group[std_key][...] = std

    by_name = {xsdata.name: xsdata for xsdata in library.xsdatas}
    total_filled = 0
    with h5py.File(mgxs_path, "r+") as h5:
        for name, group in h5["mixtures"].items():
            label = group.attrs.get("irena_mixture_label")
            label = label.decode() if isinstance(label, bytes) else str(label)
            if label not in by_name:
                raise SystemExit(f"{name}: unknown IRENA mixture label {label!r}")
            xsdata = by_name[label]
            if len(xsdata.temperatures) != 1:
                raise SystemExit(f"{label}: expected a single-temperature macrolib")
            temp_idx = 0

            total = group["total"][:]
            fill_mask = total == 0.0
            if "transport_total" in group:
                fill_mask |= group["transport_total"][:] <= 0.0
            fill = np.where(fill_mask)[0]
            if not len(fill):
                continue

            mac_total = group_vector(xsdata.total[temp_idx])
            mac_absorption = group_vector(xsdata.absorption[temp_idx])
            scatter = dense_scatter(xsdata, temp_idx)
            n_orders_mac = scatter.shape[0]

            fill_dataset(group, fill, "total", mac_total)
            fill_dataset(group, fill, "absorption", mac_absorption)
            if xsdata.fissionable and "fission" in group:
                fill_dataset(group, fill, "fission", group_vector(xsdata.fission[temp_idx]))
                fill_dataset(group, fill, "nu_fission", group_vector(xsdata.nu_fission[temp_idx]))

            matrix = group["scatter_matrix"][:]
            for order in range(min(matrix.shape[0], n_orders_mac)):
                matrix[order][fill, :] = scatter[order][fill, :]
            group["scatter_matrix"][...] = matrix
            if "scatter_matrix_std_dev" in group:
                std = group["scatter_matrix_std_dev"][:]
                std[:, fill, :] = 0.0
                group["scatter_matrix_std_dev"][...] = std

            if "transport_total" in group:
                if n_orders_mac > 1:
                    correction = scatter[1].sum(axis=1)
                else:
                    correction = np.zeros_like(mac_total)
                fill_dataset(group, fill, "transport_total", mac_total - correction)

            group.attrs["zero_flux_filled_groups"] = fill.astype(np.int64)
            group.attrs["zero_flux_fill_source"] = macrolib_arg
            total_filled += len(fill)
    return total_filled


if __name__ == "__main__":
    unittest.main()
