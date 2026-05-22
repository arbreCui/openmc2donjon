from __future__ import annotations

from pathlib import Path
import unittest


class OpenMCHexMinicaseExampleTests(unittest.TestCase):
    def test_example_python_files_are_parseable(self) -> None:
        for name in ("build_model.py", "export_recipe.py", "hex_model.py"):
            path = _example_dir() / name
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_recipe_uses_explicit_domain_specs(self) -> None:
        text = (_example_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("volume=float(_hex.DOMAIN_VOLUME_BY_ID[int(domain.id)])", text)
        self.assertIn('"source_domain_id"', text)
        self.assertIn('"hex_pitch_cm"', text)

        model_text = (_example_dir() / "hex_model.py").read_text(encoding="utf-8")
        self.assertIn("DOMAIN_VOLUME_BY_ID", model_text)
        self.assertIn('"energy_group_count"', model_text)
        self.assertIn('"legendre_order"', model_text)

    def test_readme_states_domain_to_mixture_mapping(self) -> None:
        text = (_example_dir() / "README.md").read_text(encoding="utf-8")

        self.assertIn("Each cell domain becomes one DONJON mixture", text)
        self.assertIn("explicit `DomainExportSpec`", text)
        self.assertIn("strict recipe dry-run", text)
        self.assertIn("not an accepted physics", text)

    def test_smoke_script_has_production_gates(self) -> None:
        text = (_example_dir() / "run_smoke.sh").read_text(encoding="utf-8")

        self.assertIn("Strict production dry-run", text)
        self.assertIn("--strict-dry-run", text)
        self.assertIn("--force-run-dir", text)
        self.assertIn("--production", text)
        self.assertIn("--uncertainty-production-fail", text)
        self.assertIn("mgxs_input_contract_passed", text)
        self.assertIn("did not see seven hex domains", text)
        self.assertIn("did not see one H-FACTOR dataset per domain", text)
        self.assertIn("non-fissionable kappa_fission is not zero", text)
        self.assertIn("unexpected hex fissionable split", text)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _example_dir() -> Path:
    return _repo_root() / "examples/openmc_hex_minicase"


if __name__ == "__main__":
    unittest.main()
