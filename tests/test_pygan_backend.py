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
from openmc2donjon.pygan_backend import (
    PYGAN_MODULES,
    inspect_pygan_compo,
    probe_pygan,
    require_pygan,
)


class _FakeLcmNode:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def keys(self) -> list[str]:
        return list(self._payload)

    def __getitem__(self, key: object) -> object:
        return self._payload[key]  # type: ignore[index]


class _FakeLcmList:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def __getitem__(self, key: object) -> object:
        if not isinstance(key, int):
            raise KeyError(key)
        return self._values[key]


class _FakeArray:
    def __init__(self, values: list[int]) -> None:
        self._values = values

    def tolist(self) -> list[int]:
        return self._values


class _FakeLcmModule:
    def __init__(self) -> None:
        calc = _FakeLcmNode({"SIGNATURE": "L_LIBRARY", "NTOT0": _FakeArray([1, 2])})
        mixture = _FakeLcmNode({"CALCULATIONS": _FakeLcmList([calc]), "TREE": _FakeLcmNode({})})
        root = _FakeLcmNode(
            {
                "STATE-VECTOR": _FakeArray([1, 2, 7, 10, 0, 0, 0, 0, 0, 1, 0, 2006]),
                "MIXTURES": _FakeLcmList([mixture]),
                "GLOBAL": _FakeLcmNode({}),
            }
        )
        self._object = _FakeLcmNode({"SIGNATURE": "L_MULTICOMPO", "FUEL30": root})

    def new(self, pytype: str, name: str) -> _FakeLcmNode:
        if pytype != "LCM_INP":
            raise ValueError(pytype)
        if name != "fuel.compo":
            raise ValueError(name)
        return self._object


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

    def test_inspect_pygan_compo_summarizes_lcm_tree(self) -> None:
        fake_lcm = _FakeLcmModule()

        def fake_import(name: str) -> object:
            if name == "lcm":
                return fake_lcm
            return SimpleNamespace(__file__=f"/fake/{name}.so")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "fuel.compo"
            path.write_text("fake ascii payload\n", encoding="utf-8")
            with patch("openmc2donjon.pygan_backend.importlib.import_module", side_effect=fake_import):
                inspection = inspect_pygan_compo(path)

        self.assertEqual(inspection.signature, "L_MULTICOMPO")
        self.assertEqual(inspection.root_name, "FUEL30")
        self.assertEqual(inspection.state_vector[:4], (1, 2, 7, 10))
        self.assertEqual(inspection.mixture_count, 1)
        self.assertEqual(inspection.calculation_count, 7)
        self.assertEqual(inspection.first_mixture_keys, ("CALCULATIONS", "TREE"))
        self.assertIn("SIGNATURE", inspection.first_calculation_keys)

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

    def test_pygan_inspect_compo_command_writes_summary_json(self) -> None:
        fake_lcm = _FakeLcmModule()

        def fake_import(name: str) -> object:
            if name == "lcm":
                return fake_lcm
            return SimpleNamespace(__file__=f"/fake/{name}.so")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "fuel.compo"
            summary = Path(tmpdir) / "summary.json"
            path.write_text("fake ascii payload\n", encoding="utf-8")
            stream = io.StringIO()
            with patch("openmc2donjon.pygan_backend.importlib.import_module", side_effect=fake_import):
                with contextlib.redirect_stdout(stream):
                    rc = cli_main(
                        [
                            "pygan-inspect-compo",
                            str(path),
                            "--summary-json",
                            str(summary),
                        ]
                    )
            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertIn("PyGan COMPO inspection", stream.getvalue())
        self.assertEqual(payload["schema"], "openmc2donjon.pygan-compo-inspect.v1")
        self.assertEqual(payload["root_name"], "FUEL30")

    def test_pygan_inspect_compo_is_registered(self) -> None:
        args = build_command_parser().parse_args(["pygan-inspect-compo", "fuel.compo"])
        self.assertEqual(args.command, "pygan-inspect-compo")


if __name__ == "__main__":
    unittest.main()
