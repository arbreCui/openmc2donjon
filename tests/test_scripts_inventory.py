from __future__ import annotations

from pathlib import Path
import unittest


class ScriptsInventoryTests(unittest.TestCase):
    def test_every_top_level_script_is_classified(self) -> None:
        root = _repo_root()
        inventory = (root / "scripts" / "README.md").read_text(encoding="utf-8")
        scripts = sorted(
            path.name
            for path in (root / "scripts").iterdir()
            if path.suffix in {".py", ".sh"}
        )

        self.assertGreater(len(scripts), 0)
        for script in scripts:
            with self.subTest(script=script):
                self.assertIn(f"`{script}`", inventory)

    def test_inventory_marks_release_and_diagnostic_groups(self) -> None:
        inventory = (_repo_root() / "scripts" / "README.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("## Release Gates", inventory)
        self.assertIn("## C5G7 Accepted-Baseline Gates", inventory)
        self.assertIn("## Diagnostics", inventory)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
