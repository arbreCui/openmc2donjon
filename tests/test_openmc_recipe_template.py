from __future__ import annotations

from pathlib import Path
import unittest


class OpenMCRecipeTemplateTests(unittest.TestCase):
    def test_export_recipe_template_is_parseable(self) -> None:
        path = _template_dir() / "export_recipe.py"
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_export_recipe_template_has_production_hooks(self) -> None:
        text = (_template_dir() / "export_recipe.py").read_text(encoding="utf-8")

        self.assertIn("from openmc2donjon import DomainExportSpec", text)
        self.assertIn("DOMAIN_VOLUME_BY_ID_CM3", text)
        self.assertIn("DEFAULT_DOMAIN_VOLUME_CM3", text)
        self.assertIn("def domain_specs(library):", text)
        self.assertIn("volume=domain_volume_cm3(domain)", text)
        self.assertIn('"scatter matrix"', text)

    def test_readme_states_domain_to_mixture_mapping(self) -> None:
        text = (_template_dir() / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "one exported OpenMC MGXS domain or subdomain -> one DONJON mixture",
            text,
        )
        self.assertIn("--strict-dry-run", text)
        self.assertIn("DOMAIN_VOLUME_BY_ID_CM3", text)


def _template_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "examples/openmc_recipe_template"


if __name__ == "__main__":
    unittest.main()
