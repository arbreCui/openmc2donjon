from __future__ import annotations

from pathlib import Path
import unittest


class OpenMCFullCoreMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in (
            "build_model.py",
            "export_recipe.py",
            "full_core_model.py",
        ):
            path = _example_dir() / name
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_model_declares_full_core_domain_map(self) -> None:
        text = (_example_dir() / "full_core_model.py").read_text(encoding="utf-8")

        self.assertIn('DOMAIN_MODE = "full_core_assembly"', text)
        self.assertIn("CORE_SHAPE = (3, 3)", text)
        self.assertIn("AXIAL_LAYERS = 1", text)
        self.assertIn("ASM_Y{y_index:02d}_X{x_index:02d}", text)
        self.assertIn("DOMAIN_VOLUME_BY_ID", text)
        self.assertIn("VOLUME_FLUX_TALLY_NAME", text)
        self.assertIn("reverse_openmc_energy_filter_flux", text)
        self.assertIn("write_openmc_volume_flux_hdf5", text)
        self.assertIn('"spatial_mapping"', text)

    def test_recipe_preserves_one_domain_per_assembly_position(self) -> None:
        text = (_example_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("volume=float(_full_core.DOMAIN_VOLUME_BY_ID[int(domain.id)])", text)
        self.assertIn('"source_domain_id"', text)
        self.assertIn('"assembly_x"', text)
        self.assertIn('"assembly_y"', text)
        self.assertIn('"axial_layer"', text)
        self.assertIn("append_volume_flux_hdf5", text)

    def test_readme_states_full_core_mapping(self) -> None:
        text = (_example_dir() / "README.md").read_text(encoding="utf-8")

        self.assertIn("OpenMC builds one 3D core", text)
        self.assertIn("ASM_Y01_X01", text)
        self.assertIn("ASM_Y03_X03", text)
        self.assertIn("one MGXS domain per assembly position", text)
        self.assertIn("openmc2donjon-from-openmc --production", text)

    def test_smoke_script_uses_production_entrypoint(self) -> None:
        text = (_example_dir() / "run_smoke.sh").read_text(encoding="utf-8")

        self.assertIn("Strict production dry-run", text)
        self.assertIn("--production", text)
        self.assertIn("--require-openmc-volume-flux", text)
        self.assertIn("OPENMC2DONJON_FULL_CORE_MINICASE_DIR", text)
        self.assertIn("OPENMC2DONJON-FULL-CORE-MINICASE-2G", text)
        self.assertIn("full-core assembly-wise readback OK", text)
        self.assertIn("h5[\"mixture_names\"]", text)
        self.assertIn("unexpected declared mixture order", text)
        self.assertIn("source_domain_index", text)
        self.assertIn("summary mixture names mismatch", text)
        self.assertIn("openmc_volume_flux is not tagged as MGXS/DONJON group order", text)
        self.assertIn("bundle manifest missing", text)
        self.assertIn("h_factor_datasets", text)
        self.assertIn("transport_total_datasets", text)
        self.assertIn("volume_attributes", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/openmc_full_core_minicase"


if __name__ == "__main__":
    unittest.main()
