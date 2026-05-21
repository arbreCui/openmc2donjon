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
from openmc2donjon.donjon_flux import PASS_DECISION


class DonjonFluxTests(unittest.TestCase):
    def test_cli_extracts_volume_flux_from_explicit_scalar_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            dump = root / "flux.result"
            flux = root / "donjon_volume_flux.h5"
            sph_table = root / "sph.csv"
            summary = root / "summary.json"
            _write_mgxs(mgxs)
            _write_flux_dump(dump)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "extract-donjon-volume-flux",
                        str(mgxs),
                        "--flux-dump",
                        str(dump),
                        "-o",
                        str(flux),
                        "--scalar-flux-map",
                        "fuel=2,moderator=4",
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn(PASS_DECISION, stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], PASS_DECISION)
            self.assertEqual(payload["map_kind"], "scalar_flux_map")
            self.assertEqual(payload["scalar_flux_ids"], [2, 4])
            self.assertEqual(
                payload["mixture_flux"],
                [
                    {
                        "mixture": "fuel",
                        "scalar_flux_id": 2,
                        "minimum": 20.0,
                        "maximum": 200.0,
                    },
                    {
                        "mixture": "moderator",
                        "scalar_flux_id": 4,
                        "minimum": 40.0,
                        "maximum": 400.0,
                    },
                ],
            )
            self.assertEqual(payload["warnings"], [])
            with h5py.File(flux, "r") as h5:
                self.assertEqual(h5.attrs["flux_map_kind"], "scalar_flux_map")
                np.testing.assert_allclose(
                    h5["volume_flux"][:],
                    [[20.0, 200.0], [40.0, 400.0]],
                )
                np.testing.assert_allclose(
                    h5["donjon_volume_flux"][:],
                    [[20.0, 200.0], [40.0, 400.0]],
                )
                np.testing.assert_allclose(h5["mixture_flux_minimum"][:], [20.0, 40.0])
                np.testing.assert_allclose(h5["mixture_flux_maximum"][:], [200.0, 400.0])
                names = tuple(_decode(value) for value in h5["mixture_names"][:])
            self.assertEqual(names, ("fuel", "moderator"))

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "make-sph-update-table",
                        str(mgxs),
                        "-o",
                        str(sph_table),
                        "--reference-flux",
                        str(flux),
                        "--low-order-flux",
                        f"{flux}::donjon_volume_flux",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertIn("fuel,1,1", sph_table.read_text(encoding="utf-8"))

    def test_cli_extracts_volume_flux_from_kn_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            dump = root / "flux.result"
            mapping = root / "map.h5"
            flux = root / "donjon_volume_flux.h5"
            summary = root / "summary.json"
            _write_mgxs(mgxs)
            _write_flux_dump(dump)
            with h5py.File(mapping, "w") as h5:
                h5.create_dataset(
                    "mixture_names",
                    data=np.asarray([["moderator", "fuel", "reflector"]], dtype="S"),
                )
                h5.create_dataset("kn", data=np.asarray([[4, 99], [2, 99], [0, 99]], dtype=int))

            with contextlib.redirect_stdout(io.StringIO()):
                rc = cli_main(
                    [
                        "extract-donjon-volume-flux",
                        str(mgxs),
                        "--flux-dump",
                        str(dump),
                        "-o",
                        str(flux),
                        "--map-h5",
                        str(mapping),
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["map_kind"], "map_h5:/kn")
            self.assertEqual(payload["mesh_shape"], [1, 3])
            self.assertEqual(payload["mesh_zero_or_negative_id_count"], 1)
            self.assertEqual(payload["mesh_unknown_mixture_names"], ["reflector"])
            self.assertIn("nonpositive scalar flux id", payload["warnings"][0])
            with h5py.File(flux, "r") as h5:
                np.testing.assert_allclose(
                    h5["volume_flux"][:],
                    [[20.0, 200.0], [40.0, 400.0]],
                )
                np.testing.assert_array_equal(h5["scalar_flux_ids"][:], [2, 4])
                np.testing.assert_array_equal(h5["mesh_scalar_flux_ids"][:], [[4, 2, 0]])
                np.testing.assert_allclose(
                    h5["mesh_volume_flux"][:, :, :],
                    [[[40.0, 400.0], [20.0, 200.0], [np.nan, np.nan]]],
                    equal_nan=True,
                )

    def test_duplicate_scalar_ids_are_reported_as_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            dump = root / "flux.result"
            flux = root / "donjon_volume_flux.h5"
            summary = root / "summary.json"
            _write_mgxs(mgxs)
            _write_flux_dump(dump)

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(
                    [
                        "extract-donjon-volume-flux",
                        str(mgxs),
                        "--flux-dump",
                        str(dump),
                        "-o",
                        str(flux),
                        "--scalar-flux-map",
                        "fuel=2,moderator=2",
                        "--summary-json",
                        str(summary),
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertIn("duplicate scalar flux id mapping", stream.getvalue())
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["duplicate_scalar_flux_ids"],
                [{"scalar_flux_id": 2, "mixtures": ["fuel", "moderator"]}],
            )
            self.assertIn("duplicate scalar flux id mapping", payload["warnings"][0])


def _write_mgxs(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        mixtures = h5.create_group("mixtures")
        for name in ("fuel", "moderator"):
            group = mixtures.create_group(name)
            group.attrs["volume"] = 1.0
            group.create_dataset("total", data=np.ones(2))
            group.create_dataset("absorption", data=np.zeros(2))
            group.create_dataset("fission", data=np.zeros(2))
            group.create_dataset("nu_fission", data=np.zeros(2))
            group.create_dataset("chi", data=np.zeros(2))
            group.create_dataset("scatter_matrix", data=np.zeros((1, 2, 2)))


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


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


if __name__ == "__main__":
    unittest.main()
