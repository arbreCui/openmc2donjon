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
from openmc2donjon.low_order_driver import CHECK_FAIL_DECISION, CHECK_PASS_DECISION, PASS_DECISION


class LowOrderDriverTests(unittest.TestCase):
    def test_make_low_order_driver_canonicalizes_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            raw = tmp / "raw_driver.h5"
            driver = tmp / "low_order_driver.h5"
            homogeneous = tmp / "homogeneous_face_flux.h5"
            summary = tmp / "low_order_driver_summary.json"
            check_summary = tmp / "low_order_driver_check_summary.json"
            _write_mgxs(mgxs)
            _write_raw_driver(raw)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "make-low-order-driver",
                        str(mgxs),
                        "-o",
                        str(driver),
                        "--volume-flux",
                        str(raw),
                        "--net-current",
                        str(raw),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--source-label",
                        "unit-test low-order solve",
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn(PASS_DECISION, stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(driver, "r") as h5:
                volume_flux = h5["volume_flux"][:]
                net_current = h5["net_current_density"][:]
                mixture_names = tuple(_decode(value) for value in h5["mixture_names"][:])
                face_names = tuple(_decode(value) for value in h5["face_names"][:])
                attrs = dict(h5.attrs)

            np.testing.assert_allclose(volume_flux, [[10.0, 20.0], [30.0, 40.0]])
            np.testing.assert_allclose(
                net_current,
                [
                    [[1.0, -2.0], [0.0, 1.0]],
                    [[0.0, 0.0], [2.0, -4.0]],
                ],
            )
            self.assertEqual(mixture_names, ("fuel", "mod"))
            self.assertEqual(face_names, ("FD_XMIN", "FD_XMAX"))
            self.assertEqual(attrs["schema"], "openmc2donjon.low-order-driver.v1")
            self.assertEqual(attrs["source_label"], "unit-test low-order solve")
            self.assertEqual(payload["decision"], PASS_DECISION)
            self.assertEqual(payload["volume_flux_dataset"], "volume_flux")
            self.assertEqual(payload["net_current_dataset"], "net_current_density")

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "check-low-order-driver",
                        str(mgxs),
                        str(driver),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--face-widths",
                        "4.0,2.0",
                        "--summary-json",
                        str(check_summary),
                    ]
                )
            check_payload = json.loads(check_summary.read_text(encoding="utf-8"))

            self.assertEqual(rc, 0)
            self.assertIn(CHECK_PASS_DECISION, stream.getvalue())
            self.assertEqual(check_payload["decision"], CHECK_PASS_DECISION)
            self.assertTrue(check_payload["ok"])
            self.assertEqual(check_payload["face_names"], ["FD_XMIN", "FD_XMAX"])
            self.assertGreater(check_payload["homogeneous_face_flux_min"], 0.0)

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-homogeneous-face-flux",
                        str(mgxs),
                        "-o",
                        str(homogeneous),
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
            self.assertEqual(rc, 0)
            with h5py.File(homogeneous, "r") as h5:
                values = h5["homogeneous_face_flux"][:]

        np.testing.assert_allclose(
            values,
            np.array(
                [
                    [[7.0, 23.0], [10.0, 19.25]],
                    [[30.0, 40.0], [27.6, 49.6]],
                ]
            ),
        )

    def test_check_low_order_driver_fails_bad_sign_convention(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            raw = tmp / "raw_driver.h5"
            driver = tmp / "low_order_driver.h5"
            summary = tmp / "low_order_driver_check_summary.json"
            _write_mgxs(mgxs)
            _write_raw_driver(raw)
            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-low-order-driver",
                        str(mgxs),
                        "-o",
                        str(driver),
                        "--volume-flux",
                        str(raw),
                        "--net-current",
                        str(raw),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                    ]
                )
            self.assertEqual(rc, 0)
            with h5py.File(driver, "a") as h5:
                h5["net_current_density"].attrs["sign_convention"] = "inward positive"

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "check-low-order-driver",
                        str(mgxs),
                        str(driver),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                        "--summary-json",
                        str(summary),
                    ]
                )
            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        self.assertIn(CHECK_FAIL_DECISION, stream.getvalue())
        self.assertEqual(payload["decision"], CHECK_FAIL_DECISION)
        self.assertFalse(payload["ok"])
        self.assertIn("sign_convention", payload["errors"][0])

    def test_make_low_order_driver_reorders_declared_face_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            mgxs = tmp / "mgxs.h5"
            raw = tmp / "raw_driver.h5"
            driver = tmp / "low_order_driver.h5"
            _write_mgxs(mgxs)
            _write_raw_driver_reversed_faces(raw)

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-low-order-driver",
                        str(mgxs),
                        "-o",
                        str(driver),
                        "--volume-flux",
                        str(raw),
                        "--net-current",
                        str(raw),
                        "--faces",
                        "FD_XMIN,FD_XMAX",
                    ]
                )

            with h5py.File(driver, "r") as h5:
                net_current = h5["net_current_density"][:]
                face_names = tuple(_decode(value) for value in h5["face_names"][:])

        self.assertEqual(rc, 0)
        self.assertEqual(face_names, ("FD_XMIN", "FD_XMAX"))
        np.testing.assert_allclose(
            net_current,
            [
                [[1.0, -2.0], [0.0, 1.0]],
                [[0.0, 0.0], [2.0, -4.0]],
            ],
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
            group.attrs["scatter_axes"] = "moment,from,to"
            group.attrs["volume"] = 1.0
            group.create_dataset("transport_total", data=np.asarray(transport))


def _write_raw_driver(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        volume = h5.create_dataset("volume_flux", data=np.array([[30.0, 40.0], [10.0, 20.0]]))
        current = h5.create_dataset(
            "net_current_density",
            data=np.array(
                [
                    [[0.0, 0.0], [2.0, -4.0]],
                    [[1.0, -2.0], [0.0, 1.0]],
                ]
            ),
        )
        names = np.asarray(["mod", "fuel"], dtype="S")
        volume.attrs["mixture_names"] = names
        current.attrs["mixture_names"] = names


def _write_raw_driver_reversed_faces(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        volume = h5.create_dataset("volume_flux", data=np.array([[10.0, 20.0], [30.0, 40.0]]))
        current = h5.create_dataset(
            "net_current_density",
            data=np.array(
                [
                    [[0.0, 1.0], [1.0, -2.0]],
                    [[2.0, -4.0], [0.0, 0.0]],
                ]
            ),
        )
        names = np.asarray(["fuel", "mod"], dtype="S")
        faces = np.asarray(["FD_XMAX", "FD_XMIN"], dtype="S")
        volume.attrs["mixture_names"] = names
        current.attrs["mixture_names"] = names
        current.attrs["face_names"] = faces


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


if __name__ == "__main__":
    unittest.main()
