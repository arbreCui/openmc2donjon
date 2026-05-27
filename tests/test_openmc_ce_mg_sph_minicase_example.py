from __future__ import annotations

from pathlib import Path
import unittest


class OpenMCCeMgSphMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in (
            "build_ce_case.py",
            "colorset_model.py",
            "export_recipe.py",
            "prepare_mg_case.py",
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/openmc_ce_mg_33g_sph_minicase"


if __name__ == "__main__":
    unittest.main()
