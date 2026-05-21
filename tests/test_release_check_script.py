from __future__ import annotations

from pathlib import Path
import unittest


class ReleaseCheckScriptTests(unittest.TestCase):
    def test_default_release_check_runs_openmc_hex_minicase(self) -> None:
        text = _release_check().read_text(encoding="utf-8")

        default_section, remainder = text.split(
            'if [[ "$RUN_LOCAL_CANDIDATES" -eq 1 ]]; then',
            maxsplit=1,
        )
        candidate_section, accepted_section = remainder.split(
            'echo "== Accepted baseline manifest =="',
            maxsplit=1,
        )
        self.assertIn("== OpenMC hex minicase smoke ==", default_section)
        self.assertIn("examples/openmc_hex_minicase/run_smoke.sh", default_section)
        self.assertIn("== C5G7 ADF source reconstruction smoke ==", accepted_section)
        self.assertIn("scripts/run_c5g7_adf_source_smoke.sh", accepted_section)
        self.assertIn("== C5G7 from-OpenMC flux-ratio ADF smoke ==", accepted_section)
        self.assertIn("scripts/run_c5g7_from_openmc_adf_smoke.sh", accepted_section)
        self.assertNotIn("examples/openmc_hex_minicase/run_smoke.sh", candidate_section)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _release_check() -> Path:
    return _repo_root() / "scripts/release_check.sh"


if __name__ == "__main__":
    unittest.main()
