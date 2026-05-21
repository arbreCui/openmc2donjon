from __future__ import annotations

from pathlib import Path
import unittest


class ProductionMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in ("build_model.py", "export_recipe.py", "minicase_model.py"):
            path = _example_dir() / name
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_recipe_uses_explicit_domain_specs(self) -> None:
        text = (_example_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("volume=float(_minicase.DOMAIN_VOLUME_BY_ID[int(domain.id)])", text)
        self.assertIn('"source_domain_id"', text)

        model_text = (_example_dir() / "minicase_model.py").read_text(encoding="utf-8")
        self.assertIn('"energy_group_count"', model_text)
        self.assertIn('"legendre_order"', model_text)

    def test_readme_states_domain_to_mixture_mapping(self) -> None:
        text = (_example_dir() / "README.md").read_text(encoding="utf-8")

        self.assertIn("ASM_FUEL_LEFT  -> DONJON mixture 1", text)
        self.assertIn("ASM_MOD_RIGHT  -> DONJON mixture 2", text)
        self.assertIn("workflow example, not an", text)
        self.assertIn("--strict-dry-run", text)

    def test_smoke_script_references_production_minicase(self) -> None:
        text = (_repo_root() / "scripts/run_production_minicase_smoke.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("examples/production_minicase", text)
        self.assertIn("Strict production dry-run", text)
        self.assertIn("--strict-dry-run", text)
        self.assertIn("--force-run-dir", text)
        self.assertIn("--require-transport-dataset", text)
        self.assertIn("mgxs_input_contract_passed", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/production_minicase"


if __name__ == "__main__":
    unittest.main()
