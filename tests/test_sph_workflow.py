from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon import lcm_ascii as lcm
from openmc2donjon.cli import main as cli_main
from openmc2donjon.macrolib import read_macrolib_ascii
from openmc2donjon.sph_workflow import PASS_DECISION


class SphWorkflowTests(unittest.TestCase):
    def test_cli_runs_non_c5g7_sph_iteration_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            reference = root / "reference_flux.h5"
            dump = root / "donjon_flux.result"
            output_dir = root / "workflow"
            summary = root / "workflow_summary.json"
            _write_mgxs(mgxs)
            _write_reference_flux(reference)
            _write_flux_dump(dump)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "run-sph-iteration",
                        str(mgxs),
                        "--output-dir",
                        str(output_dir),
                        "--reference-flux",
                        f"{reference}::openmc_volume_flux",
                        "--flux-dump",
                        str(dump),
                        "--scalar-flux-map",
                        "fuel=2,moderator=4",
                        "--damping",
                        "0.5",
                        "--sph-kind",
                        "unit-test-sph-workflow",
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn(PASS_DECISION, stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], PASS_DECISION)
            self.assertEqual(payload["output_format"], "macrolib")
            self.assertEqual(payload["mixture_count"], 2)
            self.assertEqual(payload["energy_groups"], 2)

            expected_sph = np.asarray(
                [
                    [2.0, 2.0],
                    [np.sqrt(2.0), np.sqrt(2.0)],
                ]
            )
            with h5py.File(output_dir / "donjon_volume_flux.h5", "r") as h5:
                np.testing.assert_allclose(
                    h5["donjon_volume_flux"][:],
                    [[20.0, 200.0], [40.0, 400.0]],
                )
            with h5py.File(output_dir / "next_sph.sidecar.h5", "r") as h5:
                np.testing.assert_allclose(h5["sph"][:], expected_sph)
                self.assertEqual(h5.attrs["sph_kind"], "unit-test-sph-workflow")
            with h5py.File(output_dir / "mgxs_with_sph.h5", "r") as h5:
                np.testing.assert_allclose(h5["mixtures/fuel/sph"][:], expected_sph[0])
                np.testing.assert_allclose(
                    h5["mixtures/moderator/sph"][:],
                    expected_sph[1],
                )

            macrolib = read_macrolib_ascii(output_dir / "out.macrolib.txt")
            self.assertIsNotNone(macrolib.sph)
            np.testing.assert_allclose(macrolib.sph, expected_sph, rtol=1.0e-8, atol=1.0e-8)


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        _write_mixture(mixtures.create_group("fuel"), fissionable=True)
        _write_mixture(mixtures.create_group("moderator"), fissionable=False)


def _write_mixture(group, *, fissionable: bool) -> None:
    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["volume"] = 10.0
    group.create_dataset("total", data=np.array([0.6, 0.8]))
    group.create_dataset("transport_total", data=np.array([0.5, 0.7]))
    group.create_dataset("absorption", data=np.array([0.1, 0.2]))
    group.create_dataset("fission", data=np.array([0.01, 0.02]) if fissionable else np.zeros(2))
    group.create_dataset(
        "nu_fission",
        data=np.array([0.025, 0.05]) if fissionable else np.zeros(2),
    )
    group.create_dataset("chi", data=np.array([1.0, 0.0]) if fissionable else np.zeros(2))
    group.create_dataset(
        "scatter_matrix",
        data=np.asarray([[[0.3, 0.1], [0.0, 0.4]]]),
    )


def _write_reference_flux(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        dataset = h5.create_dataset(
            "openmc_volume_flux",
            data=np.asarray([[80.0, 800.0], [80.0, 800.0]]),
        )
        dataset.attrs["mixture_names"] = np.asarray(("fuel", "moderator"), dtype="S")
        dataset.attrs["group_order"] = "mgxs_donjon"


def _write_flux_dump(path: Path) -> None:
    blocks = [
        lcm.list_item(1, 1),
        lcm.LcmBlock(
            1,
            0,
            2,
            4,
            data=(10.0, 20.0, 30.0, 40.0),
            trailing="00000001",
        ),
        lcm.list_item(1, 2),
        lcm.LcmBlock(
            1,
            0,
            2,
            4,
            data=(100.0, 200.0, 300.0, 400.0),
            trailing="00000002",
        ),
    ]
    lcm.write_lcm_ascii(blocks, path)


if __name__ == "__main__":
    unittest.main()
