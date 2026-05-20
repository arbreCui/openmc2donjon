from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main


class AdfAugmentTests(unittest.TestCase):
    def test_augment_adf_from_root_dataset_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_h5 = tmp / "mgxs.h5"
            sidecar = tmp / "adf_sidecar.h5"
            output_h5 = tmp / "mgxs_with_adf.h5"
            summary = tmp / "adf_summary.json"
            _write_minimal_mgxs(input_h5)
            _write_root_dataset_sidecar(sidecar)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "augment-adf",
                        str(input_h5),
                        "--adf-source",
                        str(sidecar),
                        "-o",
                        str(output_h5),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--summary-json",
                        str(summary),
                    ]
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(output_h5, "r") as h5:
                fuel_xmin = h5["mixtures/fuel/adf/FD_XMIN"][:]
                mod_xmax = h5["mixtures/mod/adf/FD_XMAX"][:]
                root_attrs = dict(h5.attrs)

        self.assertEqual(rc, 0)
        self.assertIn("openmc2donjon_adf_augment_passed", stream.getvalue())
        self.assertEqual(payload["schema"], "openmc2donjon.adf-augment.v1")
        self.assertEqual(payload["mixture_names"], ["fuel", "mod"])
        self.assertEqual(payload["face_names"], ["FD_XMIN", "FD_XMAX"])
        np.testing.assert_allclose(fuel_xmin, [1.01, 1.02])
        np.testing.assert_allclose(mod_xmax, [0.97, 0.96])
        self.assertEqual(root_attrs["adf_kind"], "production")
        self.assertEqual(root_attrs["adf_real"], "true")

    def test_augment_adf_from_c5g7_production_payload(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source = repo_root / "examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5"
        if not source.exists():
            self.skipTest("C5G7 production ADF fixture is not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            stripped = tmp / "c5g7_no_adf.h5"
            output = tmp / "c5g7_with_adf.h5"
            shutil.copyfile(source, stripped)
            _strip_adf(stripped)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "augment-adf",
                        str(stripped),
                        "--adf-source",
                        str(source),
                        "-o",
                        str(output),
                        "--faces",
                        "FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
                    ]
                )

            check_stream = io.StringIO()
            with contextlib.redirect_stdout(check_stream):
                check_rc = cli_main(
                    [
                        "check",
                        str(output),
                        "--require-adf",
                        "--expected-adf-faces",
                        "FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
                    ]
                )

            with h5py.File(source, "r") as src, h5py.File(output, "r") as out:
                names = tuple(src["mixtures"])
                source_values = _adf_matrix(src["mixtures"][names[1]])
                output_values = np.stack(
                    [out[f"mixtures/{names[1]}/adf/{face}"][:] for face in _faces()]
                )
                root_attrs = dict(out.attrs)

        self.assertEqual(rc, 0)
        self.assertEqual(check_rc, 0)
        self.assertIn("openmc2donjon_adf_augment_passed", stream.getvalue())
        self.assertIn("mgxs_input_contract_passed", check_stream.getvalue())
        np.testing.assert_allclose(output_values, source_values)
        self.assertEqual(root_attrs["adf_kind"], "production")
        self.assertEqual(root_attrs["adf_real"], "true")


def _write_minimal_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        for name, fissionable in (("fuel", True), ("mod", False)):
            group = mixtures.create_group(name)
            group.attrs["fissionable"] = fissionable
            group.attrs["scatter_axes"] = "moment,from,to"
            group.attrs["volume"] = 1.0
            group.create_dataset("total", data=np.array([0.5, 0.7]))
            group.create_dataset("absorption", data=np.array([0.05, 0.08]))
            group.create_dataset("fission", data=np.array([0.01, 0.015]))
            group.create_dataset("nu_fission", data=np.array([0.025, 0.03]))
            group.create_dataset("chi", data=np.array([1.0, 0.0]))
            group.create_dataset("transport_total", data=np.array([0.45, 0.63]))
            group.create_dataset(
                "scatter_matrix",
                data=np.array([[[0.2, 0.04], [0.0, 0.3]]]),
            )


def _write_root_dataset_sidecar(path: Path) -> None:
    values = np.array(
        [
            [[1.01, 1.02], [0.99, 0.98]],
            [[1.03, 1.04], [0.97, 0.96]],
        ]
    )
    with h5py.File(path, "w") as h5:
        h5.attrs["adf_kind"] = "production"
        h5.attrs["adf_real"] = "true"
        dataset = h5.create_dataset("adf", data=values)
        dataset.attrs["mixture_names"] = np.asarray(["fuel", "mod"], dtype="S")
        dataset.attrs["face_names"] = np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S")


def _strip_adf(path: Path) -> None:
    with h5py.File(path, "r+") as h5:
        for key in list(h5.attrs):
            if str(key).startswith("adf"):
                del h5.attrs[key]
        for group in h5["mixtures"].values():
            if "adf" in group:
                del group["adf"]


def _adf_matrix(mixture_group) -> np.ndarray:
    adf = mixture_group["adf"]
    if hasattr(adf, "keys"):
        return np.stack([adf[face][:] for face in _faces()])
    return np.asarray(adf[:], dtype=float)


def _faces() -> tuple[str, ...]:
    return ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")


if __name__ == "__main__":
    unittest.main()
