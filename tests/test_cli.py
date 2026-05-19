from __future__ import annotations

import contextlib
import io
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
