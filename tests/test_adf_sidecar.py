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


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


if __name__ == "__main__":
    unittest.main()
