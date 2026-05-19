from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.cli import build_parser, main as cli_main


class CliTests(unittest.TestCase):
    def test_version_option(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(SystemExit) as cm:
            build_parser().parse_args(["--version"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), "openmc2donjon 0.1.2")

    def test_check_command_accepts_valid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            write_valid_mgxs(path)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(["check", str(path), "--require-volume"])

        self.assertEqual(rc, 0)
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())

    def test_check_command_rejects_invalid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(["check", str(path)])

        self.assertEqual(rc, 1)
        self.assertIn("mgxs_input_contract_failed", stream.getvalue())
        self.assertIn("/energy_bounds dataset is missing", stream.getvalue())

    def test_inspect_command_reports_hdf5_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "mgxs.h5"
            summary_path = tmp / "inspect_summary.json"
            write_valid_mgxs(path)
            with h5py.File(path, "a") as h5:
                fuel = h5["mixtures/fuel"]
                fuel.create_dataset("H-FACTOR", data=np.array([10.0, 20.0]))
                adf = fuel.create_group("adf")
                adf.create_dataset("FD_XMIN", data=np.array([1.01, 0.99]))
                adf.create_dataset("FD_XMAX", data=np.array([1.02, 0.98]))

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "inspect",
                        str(path),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            payload = json.loads(summary_path.read_text(encoding="utf-8"))

        output = stream.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("OpenMC-to-DONJON MGXS inspect", output)
        self.assertIn("mixtures=1 calculations=1 state_points=1", output)
        self.assertIn("transport_total=1/1", output)
        self.assertIn("h_factor=1/1", output)
        self.assertIn("adf=1/1 faces=FD_XMAX,FD_XMIN", output)
        self.assertIn("fuel states=1", output)
        self.assertEqual(payload["schema"], "openmc2donjon.mgxs-inspect.v1")
        self.assertEqual(payload["inputs"][0]["mixture_count"], 1)
        self.assertEqual(payload["inputs"][0]["mixtures"][0]["name"], "fuel")
        self.assertEqual(
            set(payload["inputs"][0]["mixtures"][0]["adf_faces"]),
            {"FD_XMIN", "FD_XMAX"},
        )

    def test_convert_check_writes_output_for_valid_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "mgxs.h5"
            output_path = tmp / "out.mcompo.txt"
            summary_path = tmp / "check_summary.json"
            write_valid_mgxs(input_path)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        str(input_path),
                        "-o",
                        str(output_path),
                        "--check",
                        "--require-volume",
                        "--check-summary-json",
                        str(summary_path),
                    ]
                )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            output_exists = output_path.exists()

        self.assertEqual(rc, 0)
        self.assertTrue(output_exists)
        self.assertEqual(summary["decision"], "mgxs_input_contract_passed")
        self.assertIn("mgxs_input_contract_passed", stream.getvalue())

    def test_convert_check_rejects_invalid_hdf5_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_path = tmp / "bad.h5"
            output_path = tmp / "out.mcompo.txt"
            with h5py.File(input_path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main([str(input_path), "-o", str(output_path), "--check"])

        self.assertEqual(rc, 1)
        self.assertFalse(output_path.exists())
        self.assertIn("mgxs_input_contract_failed", stream.getvalue())


def write_valid_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["volume"] = 1.0
        fuel.create_dataset("total", data=np.array([0.5, 0.7]))
        fuel.create_dataset("absorption", data=np.array([0.05, 0.08]))
        fuel.create_dataset("fission", data=np.array([0.01, 0.015]))
        fuel.create_dataset("nu_fission", data=np.array([0.025, 0.03]))
        fuel.create_dataset("chi", data=np.array([1.0, 0.0]))
        fuel.create_dataset("transport_total", data=np.array([0.45, 0.63]))
        fuel.create_dataset(
            "scatter_matrix",
            data=np.array([[[0.2, 0.04], [0.0, 0.3]]]),
        )
