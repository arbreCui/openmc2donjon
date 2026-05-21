from __future__ import annotations

from pathlib import Path
import unittest


class DocsEntrypointTests(unittest.TestCase):
    def test_readme_points_reviewers_to_handoff_snapshot(self) -> None:
        root = _repo_root()
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("[Current handoff snapshot](docs/HANDOFF_SNAPSHOT.md)", readme)
        self.assertTrue((root / "docs" / "HANDOFF_SNAPSHOT.md").exists())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
