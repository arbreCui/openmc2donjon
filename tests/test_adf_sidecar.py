from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import main as cli_main


class AdfSidecarTests(unittest.TestCase):
    def test_make_unity_adf_sidecar_from_mgxs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            sidecar = tmp / "adf_sidecar.h5"
            summary = tmp / "adf_sidecar_summary.json"
            _write_minimal_mgxs(mgxs)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "make-adf-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--summary-json",
                        str(summary),
                    ]
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(sidecar, "r") as h5:
                values = h5["adf"][:]
                mixture_names = tuple(_decode(value) for value in h5["adf"].attrs["mixture_names"])
                face_names = tuple(_decode(value) for value in h5["adf"].attrs["face_names"])
                attrs = dict(h5.attrs)

        self.assertEqual(rc, 0)
        self.assertIn("openmc2donjon_adf_sidecar_passed", stream.getvalue())
        self.assertEqual(values.shape, (2, 2, 2))
        np.testing.assert_allclose(values, 1.0)
        self.assertEqual(mixture_names, ("fuel", "mod"))
        self.assertEqual(face_names, ("FD_XMIN", "FD_XMAX"))
        self.assertEqual(attrs["adf_kind"], "unity")
        self.assertEqual(attrs["adf_real"], "false")
        self.assertEqual(payload["schema"], "openmc2donjon.adf-sidecar.v1")
        self.assertEqual(payload["decision"], "openmc2donjon_adf_sidecar_passed")
        self.assertFalse(payload["adf_real"])
        self.assertEqual(payload["face_names"], ["FD_XMIN", "FD_XMAX"])

    def test_make_flux_ratio_adf_sidecar_from_face_fluxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            surface = tmp / "surface_flux.h5"
            homogeneous = tmp / "homogeneous_face_flux.h5"
            sidecar = tmp / "adf_sidecar.h5"
            summary = tmp / "adf_sidecar_summary.json"
            _write_minimal_mgxs(mgxs)
            _write_flux_file(
                surface,
                "surface_flux/mean",
                np.array(
                    [
                        [[2.0, 4.0], [3.0, 6.0]],
                        [[4.0, 8.0], [5.0, 10.0]],
                    ]
                ),
            )
            _write_flux_file(
                homogeneous,
                "homogeneous_face_flux",
                np.array(
                    [
                        [[1.0, 2.0], [1.5, 2.0]],
                        [[2.0, 4.0], [10.0, 5.0]],
                    ]
                ),
            )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "make-adf-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "flux-ratio",
                        "--surface-flux",
                        str(surface),
                        "--homogeneous-face-flux",
                        str(homogeneous),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--summary-json",
                        str(summary),
                    ]
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(sidecar, "r") as h5:
                values = h5["adf"][:]
                attrs = dict(h5.attrs)

        self.assertEqual(rc, 0)
        self.assertIn("mode=flux-ratio", stream.getvalue())
        expected = np.array(
            [
                [[2.0, 2.0], [2.0, 3.0]],
                [[2.0, 2.0], [0.5, 2.0]],
            ]
        )
        np.testing.assert_allclose(values, expected)
        self.assertEqual(attrs["adf_kind"], "flux-ratio")
        self.assertEqual(attrs["adf_real"], "true")
        self.assertEqual(attrs["adf_definition"], "ADF = heterogeneous face flux / homogeneous face flux")
        self.assertEqual(payload["schema"], "openmc2donjon.adf-sidecar.v1")
        self.assertEqual(payload["decision"], "openmc2donjon_adf_sidecar_passed")
        self.assertEqual(payload["mode"], "flux-ratio")
        self.assertTrue(payload["adf_real"])
        self.assertEqual(payload["invalid_count"], 0)
        self.assertEqual(payload["min"], 0.5)
        self.assertEqual(payload["median"], 2.0)
        self.assertEqual(payload["max"], 3.0)

    def test_make_flux_ratio_sidecar_reads_mesh_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            flux = tmp / "face_fluxes.h5"
            sidecar = tmp / "adf_sidecar.h5"
            _write_minimal_mgxs(mgxs)
            with h5py.File(flux, "w") as h5:
                h5.create_dataset(
                    "mixture_names",
                    data=np.asarray([["fuel", "mod"]], dtype="S"),
                )
                h5.create_dataset(
                    "face_names",
                    data=np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S"),
                )
                h5.create_dataset(
                    "surface_flux_proxy",
                    data=np.array([[[[2.0, 3.0], [4.0, 6.0]], [[4.0, 5.0], [8.0, 10.0]]]]),
                )
                h5.create_dataset(
                    "homogeneous_face_flux",
                    data=np.array([[[[1.0, 1.5], [2.0, 2.0]], [[2.0, 10.0], [4.0, 5.0]]]]),
                )

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-adf-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "flux-ratio",
                        "--surface-flux",
                        str(flux),
                        "--homogeneous-face-flux",
                        str(flux),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                    ]
                )
            with h5py.File(sidecar, "r") as h5:
                values = h5["adf"][:]

        self.assertEqual(rc, 0)
        np.testing.assert_allclose(
            values,
            np.array(
                [
                    [[2.0, 2.0], [2.0, 3.0]],
                    [[2.0, 2.0], [0.5, 2.0]],
                ]
            ),
        )

    def test_make_flux_ratio_requires_explicit_invalid_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            surface = tmp / "surface_flux.h5"
            homogeneous = tmp / "homogeneous_face_flux.h5"
            sidecar = tmp / "adf_sidecar.h5"
            _write_minimal_mgxs(mgxs)
            _write_flux_file(surface, "surface_flux/mean", np.ones((2, 2, 2)))
            _write_flux_file(homogeneous, "homogeneous_face_flux", np.zeros((2, 2, 2)))

            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                cli_main(
                    [
                        "make-adf-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "flux-ratio",
                        "--surface-flux",
                        str(surface),
                        "--homogeneous-face-flux",
                        str(homogeneous),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                    ]
                )

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("invalid bin", err.getvalue())

    def test_make_flux_ratio_fills_nonpositive_homogeneous_flux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            surface = tmp / "surface_flux.h5"
            homogeneous = tmp / "homogeneous_face_flux.h5"
            sidecar = tmp / "adf_sidecar.h5"
            summary = tmp / "adf_sidecar_summary.json"
            _write_minimal_mgxs(mgxs)
            _write_flux_file(
                surface,
                "surface_flux/mean",
                np.array(
                    [
                        [[2.0, 4.0], [3.0, 6.0]],
                        [[4.0, 8.0], [5.0, 10.0]],
                    ]
                ),
            )
            _write_flux_file(
                homogeneous,
                "homogeneous_face_flux",
                np.array(
                    [
                        [[1.0, -2.0], [1.5, 0.0]],
                        [[2.0, 4.0], [10.0, 5.0]],
                    ]
                ),
            )

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-adf-sidecar",
                        str(mgxs),
                        "-o",
                        str(sidecar),
                        "--mode",
                        "flux-ratio",
                        "--surface-flux",
                        str(surface),
                        "--homogeneous-face-flux",
                        str(homogeneous),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--invalid-fill",
                        "1.0",
                        "--summary-json",
                        str(summary),
                    ]
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(sidecar, "r") as h5:
                values = h5["adf"][:]

        self.assertEqual(rc, 0)
        np.testing.assert_allclose(
            values,
            np.array(
                [
                    [[2.0, 1.0], [2.0, 1.0]],
                    [[2.0, 2.0], [0.5, 2.0]],
                ]
            ),
        )
        self.assertEqual(payload["invalid_count"], 2)
        self.assertEqual(payload["invalid_filled_count"], 2)


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


def _write_flux_file(path: Path, dataset_path: str, values: np.ndarray) -> None:
    with h5py.File(path, "w") as h5:
        parent = h5
        parts = dataset_path.split("/")
        for part in parts[:-1]:
            parent = parent.create_group(part)
        dataset = parent.create_dataset(parts[-1], data=values)
        dataset.attrs["mixture_names"] = np.asarray(["fuel", "mod"], dtype="S")
        dataset.attrs["face_names"] = np.asarray(["FD_XMIN", "FD_XMAX"], dtype="S")


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


if __name__ == "__main__":
    unittest.main()
