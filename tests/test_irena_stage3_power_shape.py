from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "irena30_sph_stage3_fullcore"
    / "compare_power_shape.py"
)
SPEC = importlib.util.spec_from_file_location("irena30_compare_power_shape", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_flux(path: Path, values: np.ndarray) -> None:
    with h5py.File(path, "w") as h5:
        h5.create_dataset("flux", data=values)


class IrenaStage3PowerShapeTests(unittest.TestCase):
    def test_corrected_shape_uses_sph_scaled_kappa_and_improves(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mgxs = root / "mgxs.h5"
            names = ("A", "B")
            with h5py.File(mgxs, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.create_dataset("mixture_names", data=np.asarray(names, dtype="S"))
                mixtures = h5.create_group("mixtures")
                for name in names:
                    group = mixtures.create_group(name)
                    group.create_dataset("kappa_fission", data=[1.0, 1.0])

            reference = root / "reference.h5"
            uncorrected = root / "uncorrected.h5"
            corrected = root / "corrected.h5"
            _write_flux(reference, np.asarray([[1.0, 1.0], [1.0, 1.0]]))
            _write_flux(uncorrected, np.asarray([[2.0, 2.0], [1.0, 1.0]]))
            _write_flux(corrected, np.asarray([[1.2, 1.2], [1.0, 1.0]]))

            sidecar = root / "sph.h5"
            with h5py.File(sidecar, "w") as h5:
                sph = h5.create_dataset("sph", data=[[1.2, 1.2], [1.0, 1.0]])
                sph.attrs["mixture_names"] = np.asarray(names, dtype="S")

            payload = MODULE.compare_power_shapes(
                mgxs,
                reference_flux=f"{reference}::flux",
                uncorrected_flux=f"{uncorrected}::flux",
                corrected_flux=f"{corrected}::flux",
                corrected_sph=sidecar,
            )

            self.assertTrue(payload["corrected_improved"])
            self.assertAlmostEqual(
                payload["corrected"]["maximum_absolute_relative_error"], 0.0
            )
            self.assertGreater(
                payload["uncorrected"]["maximum_absolute_relative_error"], 0.3
            )

    def test_rejects_flux_shape_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "flux.h5"
            _write_flux(path, np.ones((1, 2)))
            with self.assertRaisesRegex(ValueError, "flux shape"):
                MODULE._load_flux(
                    f"{path}::flux",
                    shape=(2, 2),
                    default_dataset="flux",
                )


if __name__ == "__main__":
    unittest.main()
