from __future__ import annotations

from pathlib import Path
import unittest


class OpenMCRecipeTemplateTests(unittest.TestCase):
    def test_export_recipe_template_is_parseable(self) -> None:
        path = _template_dir() / "export_recipe.py"
        compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_readme_states_domain_to_mixture_mapping(self) -> None:
        text = (_template_dir() / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "one exported OpenMC MGXS domain or subdomain -> one DONJON mixture",
            text,
        )


def _template_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "examples/openmc_recipe_template"


if __name__ == "__main__":
    unittest.main()
