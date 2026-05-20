from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.openmc_surface_flux import (
    PASS_DECISION,
    SCHEMA,
    reconstruct_surface_flux_from_angular_currents,
    reshape_angular_surface_current,
    write_surface_flux_hdf5,
)


class OpenMCSurfaceFluxTests(unittest.TestCase):
    def test_reshape_angular_surface_current_reverses_energy_order(self) -> None:
        raw: list[float] = []
        for surface in range(8):
            raw.extend([10.0 + surface, 100.0 + surface])

        values = reshape_angular_surface_current(
            np.asarray(raw),
            mesh_shape=(1, 1),
            energy_groups=2,
            mu_edges=(0.0, 1.0),
        )

        self.assertEqual(values.shape, (1, 1, 2, 8, 1))
        np.testing.assert_allclose(values[0, 0, 0, :, 0], np.arange(100.0, 108.0))
        np.testing.assert_allclose(values[0, 0, 1, :, 0], np.arange(10.0, 18.0))

    def test_reconstruct_surface_flux_from_angular_currents(self) -> None:
        angular = np.zeros((1, 1, 1, 8, 2), dtype=float)
        angular[..., 0, :] = [2.0, 3.0]
        angular[..., 1, :] = [4.0, 6.0]
        angular_std = np.zeros_like(angular)

        _partial, _partial_std, surface_flux, surface_std = (
            reconstruct_surface_flux_from_angular_currents(
                angular,
                angular_std,
                mu_edges=(0.0, 0.5, 1.0),
                face_area=2.0,
            )
        )

        expected_xmin = ((2.0 / 0.25 + 3.0 / 0.75) + (4.0 / 0.25 + 6.0 / 0.75)) / 2.0
        np.testing.assert_allclose(surface_flux[0, 0, 0, 0], expected_xmin)
        np.testing.assert_allclose(surface_flux[0, 0, 0, 1:], 0.0)
        np.testing.assert_allclose(surface_std, 0.0)

    def test_write_surface_flux_hdf5(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            output = tmp / "openmc_surface_flux.h5"
            summary = tmp / "surface_flux_summary.json"
            flux = np.array(
                [
                    [
                        [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]],
                        [[2.0, 3.0, 4.0, 5.0], [6.0, 7.0, 8.0, 9.0]],
                    ]
                ],
                dtype=float,
            )

            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                report = write_surface_flux_hdf5(
                    output,
                    surface_flux=flux,
                    surface_flux_std_dev=np.zeros_like(flux),
                    energy_bounds=np.array([1.0e-5, 1.0, 1.0e7]),
                    mixture_names=("ASM_FUEL_LEFT", "ASM_MOD_RIGHT"),
                    face_names=("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX"),
                    tally_name="surface_tally",
                    mu_edges=(0.0, 0.5, 1.0),
                    face_area=4.0,
                    summary_json=summary,
                )

            payload = json.loads(summary.read_text(encoding="utf-8"))
            with h5py.File(output, "r") as h5:
                values = h5["surface_flux/mean"][:]
                mixture_names = tuple(_decode(value) for value in h5["mixture_names"][:].reshape(-1))
                face_names = tuple(_decode(value) for value in h5["face_names"][:])
                attrs = dict(h5.attrs)

        self.assertEqual(report.mesh_shape, (1, 2))
        self.assertIn(PASS_DECISION, stream.getvalue())
        np.testing.assert_allclose(values, flux)
        self.assertEqual(mixture_names, ("ASM_FUEL_LEFT", "ASM_MOD_RIGHT"))
        self.assertEqual(face_names, ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX"))
        self.assertEqual(attrs["schema"], SCHEMA)
        self.assertEqual(payload["decision"], PASS_DECISION)
        self.assertEqual(payload["mesh_shape"], [1, 2])
        self.assertEqual(payload["energy_groups"], 2)


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


if __name__ == "__main__":
    unittest.main()
