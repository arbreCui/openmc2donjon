from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LcmAsciiStressScriptTests(unittest.TestCase):
    def test_stress_script_accepts_real_repo_fixture(self) -> None:
        root = _repo_root()
        script = root / "scripts" / "stress_lcm_ascii_parser.py"
        fixture = root / "tests" / "fixtures" / "donjon_multicompo_reflector_full.txt"

        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.json"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(fixture),
                    "--min-blocks",
                    "250",
                    "--require-signature",
                    "L_MULTICOMPO",
                    "--require-signature",
                    "L_LIBRARY",
                    "--require-block",
                    "MACROLIB",
                    "--require-block",
                    "TREE",
                    "--summary-json",
                    str(summary),
                ],
                check=False,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("decision: PASS", result.stdout)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["block_count"], 292)
            self.assertEqual(payload["signature_counts"]["L_MULTICOMPO"], 1)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
