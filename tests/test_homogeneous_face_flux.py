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
from openmc2donjon.homogeneous_face_flux import (
    PASS_DECISION,
    reconstruct_homogeneous_face_flux,
)


class HomogeneousFaceFluxTests(unittest.TestCase):
    def test_reconstruct_homogeneous_face_flux(self) -> None:
        volume = np.array([[10.0, 20.0]])
        current = np.array([[[1.0, -2.0], [0.0, 1.0]]])
        diffusion = np.array([[2.0, 4.0]])

        values = reconstruct_homogeneous_face_flux(
            volume,
            current,
            diffusion=diffusion,
            face_widths=(4.0, 2.0),
        )

        expected = np.array([[[9.0, 21.0], [10.0, 19.75]]])
        np.testing.assert_allclose(values, expected)

    def test_make_homogeneous_face_flux_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            driver = tmp / "driver.h5"
            output = tmp / "homogeneous_face_flux.h5"
            summary = tmp / "homogeneous_face_flux_summary.json"
            _write_mgxs(mgxs)
            _write_driver(driver)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "make-homogeneous-face-flux",
                        str(mgxs),
                        "-o",
                        str(output),
                        "--volume-flux",
                        str(driver),
                        "--net-current",
                        str(driver),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--face-widths",
                        "4.0,2.0",
                        "--summary-json",
                        str(summary),
                    ]
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(output, "r") as h5:
                values = h5["homogeneous_face_flux"][:]
                mixture_names = tuple(_decode(value) for value in h5["mixture_names"][:])
                face_names = tuple(_decode(value) for value in h5["face_names"][:])
                attrs = dict(h5.attrs)

        self.assertEqual(rc, 0)
        self.assertIn(PASS_DECISION, stream.getvalue())
        expected = np.array(
            [
                [[7.0, 23.0], [10.0, 19.25]],
                [[30.0, 40.0], [27.6, 49.6]],
            ]
        )
        np.testing.assert_allclose(values, expected)
        self.assertEqual(mixture_names, ("fuel", "mod"))
        self.assertEqual(face_names, ("FD_XMIN", "FD_XMAX"))
        self.assertEqual(attrs["schema"], "openmc2donjon.homogeneous-face-flux.v1")
        self.assertEqual(payload["decision"], PASS_DECISION)
        self.assertEqual(payload["face_widths"], [4.0, 2.0])
        self.assertEqual(payload["nonpositive_count"], 0)

    def test_make_homogeneous_face_flux_reads_mesh_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            driver = tmp / "driver.h5"
            output = tmp / "homogeneous_face_flux.h5"
            _write_mgxs(mgxs)
            with h5py.File(driver, "w") as h5:
                h5.create_dataset("mixture_names", data=np.asarray([["fuel", "mod"]], dtype="S"))
                h5.create_dataset("volume_flux", data=np.array([[[10.0, 20.0], [30.0, 40.0]]]))
                h5.create_dataset(
                    "net_current_density",
                    data=np.array([[[[1.0, -2.0], [0.0, 1.0]], [[0.0, 0.0], [2.0, -4.0]]]]),
                )

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-homogeneous-face-flux",
                        str(mgxs),
                        "-o",
                        str(output),
                        "--volume-flux",
                        str(driver),
                        "--net-current",
                        str(driver),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--face-widths",
                        "4.0,2.0",
                    ]
                )
            with h5py.File(output, "r") as h5:
                values = h5["homogeneous_face_flux"][:]

        self.assertEqual(rc, 0)
        np.testing.assert_allclose(
            values,
            np.array(
                [
                    [[7.0, 23.0], [10.0, 19.25]],
                    [[30.0, 40.0], [27.6, 49.6]],
                ]
            ),
        )


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        for name, transport in (("fuel", [0.5, 0.25]), ("mod", [0.4, 0.8])):
            group = mixtures.create_group(name)
            group.attrs["fissionable"] = name == "fuel"
            group.attrs["volume"] = 1.0
            group.create_dataset("transport_total", data=np.asarray(transport))


def _write_driver(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        volume = h5.create_dataset("volume_flux", data=np.array([[10.0, 20.0], [30.0, 40.0]]))
        current = h5.create_dataset(
            "net_current_density",
            data=np.array([[[1.0, -2.0], [0.0, 1.0]], [[0.0, 0.0], [2.0, -4.0]]]),
        )
        volume.attrs["mixture_names"] = np.asarray(["fuel", "mod"], dtype="S")
        current.attrs["mixture_names"] = np.asarray(["fuel", "mod"], dtype="S")


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


if __name__ == "__main__":
    unittest.main()
