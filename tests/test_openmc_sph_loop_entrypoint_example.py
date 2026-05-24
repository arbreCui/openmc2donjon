from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import h5py
import numpy as np


EXPECTED_REFERENCE_FLUX = np.asarray(
    [
        [617.96762, 156.844407],
        [47.4604219, 4.87293612],
    ],
    dtype=float,
)
EXPECTED_REFERENCE_FLUX_STD_DEV = np.abs(EXPECTED_REFERENCE_FLUX) * 1.0e-3


class OpenmcSphLoopEntrypointExampleTests(unittest.TestCase):
    def test_recipe_postprocess_writes_reference_flux(self) -> None:
        root = _repo_root()
        recipe_path = root / "examples/openmc_sph_loop_entrypoint/export_recipe.py"
        module = _load_module(recipe_path)
        library = module.build_library()
        library.loaded_statepoint = "statepoint.fake.h5"
        summary = type(
            "Summary",
            (),
            {
                "domains": [
                    type("Domain", (), {"name": "FUEL_A"}),
                    type("Domain", (), {"name": "MOD_A"}),
                ]
            },
        )()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "mgxs_library.h5"
            with h5py.File(output, "w"):
                pass
            module.postprocess_hdf5(output_path=output, summary=summary)

            with h5py.File(output, "r") as h5:
                np.testing.assert_allclose(
                    h5["openmc_volume_flux"][:],
                    EXPECTED_REFERENCE_FLUX,
                )
                np.testing.assert_allclose(
                    h5["openmc_volume_flux_std_dev"][:],
                    EXPECTED_REFERENCE_FLUX_STD_DEV,
                )
                np.testing.assert_array_equal(
                    h5["openmc_volume_flux"].attrs["mixture_names"],
                    np.asarray(["FUEL_A", "MOD_A"], dtype="S"),
                )
                np.testing.assert_array_equal(
                    h5["openmc_volume_flux_std_dev"].attrs["mixture_names"],
                    np.asarray(["FUEL_A", "MOD_A"], dtype="S"),
                )
                self.assertEqual(
                    h5["openmc_volume_flux"].attrs["group_order"],
                    "mgxs_donjon",
                )
                self.assertEqual(
                    h5["openmc_volume_flux_std_dev"].attrs["group_order"],
                    "mgxs_donjon",
                )
                self.assertEqual(
                    h5["openmc_volume_flux_std_dev"].attrs["std_dev_of"],
                    "openmc_volume_flux",
                )

    def test_smoke_script_uses_handoff_entrypoint(self) -> None:
        root = _repo_root()
        text = (root / "examples/openmc_sph_loop_entrypoint/run_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("prepare-openmc-sph-loop", text)
        self.assertIn("--production", text)
        self.assertIn("openmc_volume_flux", text)
        self.assertIn("openmc_volume_flux_std_dev", text)
        self.assertIn("--require-std-dev-coverage", text)
        self.assertIn("--acceptance-require-reference-flux-std-dev", text)
        self.assertIn("--acceptance-max-reference-flux-std-dev-rel", text)
        self.assertIn("FUEL_A=2,MOD_A=4", text)
        self.assertIn("loop_config.json", text)
        self.assertIn('config["acceptance"]["preset"] == "production"', text)
        self.assertIn("RUN_REAL_DONJON", text)
        self.assertIn("real_sph_loop_summary.json", text)
        self.assertIn("OpenMC SPH loop entrypoint real DONJON loop OK", text)
        self.assertIn("openmc2donjon_openmc_sph_loop_handoff_passed", text)
        self.assertIn("OpenMC SPH loop entrypoint smoke: PASS", text)


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("_openmc_sph_loop_recipe", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
