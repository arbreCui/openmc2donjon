from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openmc2donjon.cli import build_command_parser, main as cli_main
from openmc2donjon.pygan_backend import PYGAN_MODULES, probe_pygan, require_pygan


class PyGanBackendTests(unittest.TestCase):
    def test_probe_pygan_reports_all_modules_available(self) -> None:
        def fake_import(name: str) -> SimpleNamespace:
            return SimpleNamespace(__file__=f"/fake/{name}.so")

        with patch("openmc2donjon.pygan_backend.importlib.import_module", side_effect=fake_import):
            status = probe_pygan()

        self.assertTrue(status.available)
        self.assertEqual([module.name for module in status.modules], list(PYGAN_MODULES))
        self.assertEqual(status.missing_modules, ())
        self.assertEqual(status.modules[0].module_file, "/fake/lcm.so")

    def test_probe_pygan_reports_missing_modules(self) -> None:
        def fake_import(name: str) -> SimpleNamespace:
            if name == "lcm":
                return SimpleNamespace(__file__="/fake/lcm.so")
            raise ModuleNotFoundError(name)

        with patch("openmc2donjon.pygan_backend.importlib.import_module", side_effect=fake_import):
            status = probe_pygan()

        self.assertFalse(status.available)
        self.assertEqual(status.missing_modules, ("lifo", "cle2000"))
        self.assertIn("ModuleNotFoundError", status.modules[1].error or "")

    def test_require_pygan_raises_actionable_error(self) -> None:
        with patch(
            "openmc2donjon.pygan_backend.importlib.import_module",
            side_effect=ModuleNotFoundError("lcm"),
        ):
            with self.assertRaisesRegex(RuntimeError, "PyGan backend is not available"):
                require_pygan()

    def test_pygan_doctor_command_writes_summary_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "pygan.json"
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = cli_main(["pygan-doctor", "--summary-json", str(summary)])
            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertIn(rc, {0, 1})
        self.assertIn("pygan_backend=", stream.getvalue())
        self.assertIn("modules", payload)
        self.assertEqual([module["name"] for module in payload["modules"]], list(PYGAN_MODULES))

    def test_pygan_doctor_is_registered(self) -> None:
        args = build_command_parser().parse_args(["pygan-doctor"])
        self.assertEqual(args.command, "pygan-doctor")


if __name__ == "__main__":
    unittest.main()
