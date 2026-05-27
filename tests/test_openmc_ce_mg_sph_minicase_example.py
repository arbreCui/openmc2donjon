from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np


class OpenMCCeMgSphMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in (
            "build_ce_case.py",
            "colorset_model.py",
            "export_recipe.py",
            "prepare_mg_case.py",
            "summarize_outputs.py",
        ):
            path = _example_dir() / name
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_model_declares_openmc_ce_mg_sph_contract(self) -> None:
        text = (_example_dir() / "colorset_model.py").read_text(encoding="utf-8")

        self.assertIn('ENERGY_MESH_ID = "ecco_33"', text)
        self.assertIn("LEGENDRE_ORDER = 3", text)
        self.assertIn("DOMAIN_IDS = (FUEL_CELL_ID, MODERATOR_CELL_ID, ABSORBER_CELL_ID)", text)
        self.assertIn("VOLUME_FLUX_TALLY_NAME", text)
        self.assertIn("reverse_openmc_energy_filter_flux", text)
        self.assertIn("write_openmc_volume_flux_hdf5", text)
        self.assertIn('"sph_route"', text)
        self.assertIn("OpenMC CE reference + OpenMC MG 33g same geometry", text)

    def test_recipe_uses_explicit_domain_specs_and_flux_postprocess(self) -> None:
        text = (_example_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("colorset_region", text)
        self.assertIn("def extra_tallies(library):", text)
        self.assertIn("build_volume_flux_tally", text)
        self.assertIn("def postprocess_hdf5(output_path, statepoint_path, summary):", text)
        self.assertIn("append_volume_flux_hdf5", text)

    def test_prepare_mg_case_builds_openmc_mg_model_from_ce_statepoint(self) -> None:
        text = (_example_dir() / "prepare_mg_case.py").read_text(encoding="utf-8")

        self.assertIn("library.create_mg_mode()", text)
        self.assertIn('energy_mode="multi-group"', text)
        self.assertIn("mgxs_path = (mg_dir / args.mgxs_name).resolve()", text)
        self.assertIn("materials.cross_sections = str(mgxs_path)", text)
        self.assertIn("mgxs_file.export_to_hdf5", text)
        self.assertIn("build_mg_tallies", text)

    def test_readme_and_workflow_keep_donjon_loop_out_of_the_route(self) -> None:
        readme = (_example_dir() / "README.md").read_text(encoding="utf-8")
        script = (_example_dir() / "run_workflow.sh").read_text(encoding="utf-8")

        self.assertIn("OpenMC continuous-energy reference", readme)
        self.assertIn("OpenMC multi-group 33g macro calculation", readme)
        self.assertIn("CS_FUEL  -> DONJON mixture 1", readme)
        self.assertIn("CS_MOD   -> DONJON mixture 2", readme)
        self.assertIn("CS_ABS   -> DONJON mixture 3", readme)
        self.assertIn("does **not** use a DONJON feedback loop", readme)
        self.assertIn("Angular/Hn-dependent SPH is a later extension", readme)

        self.assertIn("build_ce_case.py", script)
        self.assertIn("prepare_mg_case.py", script)
        self.assertIn("--dataset-name openmc_volume_flux", script)
        self.assertIn("--dataset-name openmc_mg_flux", script)
        self.assertIn("make-openmc-sph-sidecar", script)
        self.assertIn("--require-reference-flux-std-dev", script)
        self.assertIn("--require-mg-flux-std-dev", script)
        self.assertIn("OPENMC_LIB_DIR", readme)
        self.assertIn("OPENMC_LIB_DIR", script)
        self.assertIn("DYLD_LIBRARY_PATH", script)
        self.assertIn("LD_LIBRARY_PATH", script)
        self.assertNotIn("run-sph-loop", script)

    def test_summary_script_writes_physics_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp)
            _write_summary_fixture(handoff)
            module = _load_summary_module()

            rc = module.main(["--handoff-dir", str(handoff)])

            self.assertEqual(rc, 0)
            payload = json.loads((handoff / "physics_summary.json").read_text(encoding="utf-8"))
            markdown = (handoff / "physics_summary.md").read_text(encoding="utf-8")
            self.assertEqual(
                payload["schema"],
                "openmc2donjon.openmc-ce-mg-33g-sph-physics-summary.v1",
            )
            self.assertEqual(payload["mixture_count"], 2)
            self.assertEqual(payload["energy_groups"], 2)
            self.assertEqual(payload["legendre_order"], 3)
            self.assertEqual(payload["handoff"]["ascii_nsp_block_count"], 1)
            self.assertEqual(payload["handoff"]["accepted_sph_consumption_format"], "macrolib")
            self.assertEqual(payload["handoff"]["macrolib_ascii_nsp_block_count"], 1)
            self.assertTrue(payload["handoff"]["augmented_hdf5_has_sph"])
            self.assertIn("OpenMC CE/MG 33g SPH Physics Summary", markdown)
            self.assertIn("Accepted SPH consumption format", markdown)
            self.assertIn("CS_FUEL", markdown)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/openmc_ce_mg_33g_sph_minicase"


def _load_summary_module():
    path = _example_dir() / "summarize_outputs.py"
    spec = importlib.util.spec_from_file_location("_openmc2donjon_minicase_summary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_summary_fixture(handoff: Path) -> None:
    names = np.array(["CS_FUEL", "CS_MOD"], dtype=h5py.string_dtype(encoding="utf-8"))
    energy_bounds = np.array([0.0, 1.0, 2.0])
    sph = {
        "CS_FUEL": np.array([0.9, 1.1]),
        "CS_MOD": np.array([1.0, 1.2]),
    }
    with h5py.File(handoff / "mgxs_library.h5", "w") as h5:
        h5.attrs["legendre_order"] = 3
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset("mixture_names", data=names)
    with h5py.File(handoff / "mgxs_with_openmc_sph.h5", "w") as h5:
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset("mixture_names", data=names)
        mixtures = h5.create_group("mixtures")
        for name, values in sph.items():
            mixtures.create_group(name).create_dataset("sph", data=values)
    _write_flux_h5(
        handoff / "openmc_ce_flux.h5",
        "openmc_volume_flux",
        np.array([[1.0, 2.0], [3.0, 4.0]]),
    )
    _write_flux_h5(
        handoff / "openmc_mg_flux.h5",
        "openmc_mg_flux",
        np.array([[0.9, 2.2], [3.0, 4.8]]),
    )
    with h5py.File(handoff / "openmc_sph_sidecar.h5", "w") as h5:
        h5.create_dataset("sph", data=np.array([[0.9, 1.1], [1.0, 1.2]]))
    (handoff / "openmc_sph_summary.json").write_text(
        json.dumps(
            {
                "decision": "openmc2donjon_openmc_sph_sidecar_passed",
                "flux_normalization": "power",
                "formula": "sph = normalized_openmc_mg_flux / openmc_ce_reference_flux",
                "normalization_factor": 1.0,
                "sph_kind": "openmc-ce-mg",
                "sph_real": True,
                "clipped_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (handoff / "sph_augment_summary.json").write_text(
        json.dumps(
            {
                "decision": "openmc2donjon_sph_augment_passed",
                "sph_applied": False,
            }
        ),
        encoding="utf-8",
    )
    (handoff / "out_with_openmc_sph.mcompo.txt").write_text("NSPH\n", encoding="utf-8")
    (handoff / "out_with_openmc_sph.macrolib.txt").write_text("NSPH\n", encoding="utf-8")


def _write_flux_h5(path: Path, dataset_name: str, values: np.ndarray) -> None:
    with h5py.File(path, "w") as h5:
        h5.create_dataset(dataset_name, data=values)
        h5.create_dataset(f"{dataset_name}_std_dev", data=values * 0.01)


if __name__ == "__main__":
    unittest.main()
