from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from openmc2donjon import lcm_ascii as lcm
from openmc2donjon.cli import build_parser, main as cli_main
from openmc2donjon.pygan_writer import write_lcm_blocks_with_pygan


class _FakePyGanNode:
    def __init__(self, name: str, *, is_list: bool = False, length: int | None = None) -> None:
        self.name = name
        self.is_list = is_list
        self.length = length
        self.values: dict[object, object] = {}

    def rep(self, key: object) -> "_FakePyGanNode":
        if self.is_list and not isinstance(key, int):
            raise TypeError("list rep key must be an integer")
        child = _FakePyGanNode(str(key))
        self.values[key] = child
        return child

    def lis(self, key: object, length: int) -> "_FakePyGanNode":
        if self.is_list and not isinstance(key, int):
            raise TypeError("list lis key must be an integer")
        child = _FakePyGanNode(str(key), is_list=True, length=length)
        self.values[key] = child
        return child

    def __setitem__(self, key: object, value: object) -> None:
        self.values[key] = value


class _FakePyGanLcmModule:
    def __init__(self) -> None:
        self.root: _FakePyGanNode | None = None

    def new(self, pytype: str, name: str | None = None, **kwargs: object) -> _FakePyGanNode:
        if pytype == "LCM":
            if not isinstance(name, str):
                raise TypeError("LCM object requires a name")
            self.root = _FakePyGanNode(name)
            return self.root
        if pytype == "ASCII":
            pyobj = kwargs.get("pyobj")
            if not isinstance(pyobj, _FakePyGanNode):
                raise TypeError("ASCII export requires pyobj")
            Path(f"_{pyobj.name}").write_text("fake pygan ascii\n", encoding="utf-8")
            return pyobj
        raise ValueError(pytype)


class PyGanWriterTests(unittest.TestCase):
    def test_writer_loads_lcm_blocks_into_pygan_tree_and_exports(self) -> None:
        fake_lcm = _FakePyGanLcmModule()

        def fake_import(name: str) -> object:
            if name == "lcm":
                return fake_lcm
            return SimpleNamespace(__file__=f"/fake/{name}.so")

        blocks = [
            lcm.string_block(1, "SIGNATURE", "L_TEST", width=8),
            lcm.block(1, "ROOT", 0, count=-1),
            lcm.block(2, "INTS", 1, [1, 2, 3]),
            lcm.block(2, "REALS", 2, [1.25, 2.5]),
            lcm.block(2, "ITEMS", 10, count=2),
            lcm.list_item(3, 1),
            lcm.string_block(4, "NAME", "A", width=4),
            lcm.list_item(3, 2),
            lcm.string_block(4, "NAME", "B", width=4),
            lcm.control(-2),
            lcm.control(-1),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.mcompo.txt"
            with patch("openmc2donjon.pygan_backend.importlib.import_module", side_effect=fake_import):
                write_lcm_blocks_with_pygan(blocks, out)

            self.assertEqual(out.read_text(encoding="utf-8"), "fake pygan ascii\n")

        root = fake_lcm.root
        self.assertIsNotNone(root)
        assert root is not None
        self.assertEqual(root.values["SIGNATURE"], "L_TEST  ")
        root_dir = root.values["ROOT"]
        self.assertIsInstance(root_dir, _FakePyGanNode)
        assert isinstance(root_dir, _FakePyGanNode)
        self.assertEqual(root_dir.values["INTS"].dtype, np.dtype("int32"))
        self.assertEqual(root_dir.values["REALS"].dtype, np.dtype("float32"))
        items = root_dir.values["ITEMS"]
        self.assertIsInstance(items, _FakePyGanNode)
        assert isinstance(items, _FakePyGanNode)
        self.assertEqual(items.length, 2)
        self.assertEqual(items.values[0].values["NAME"], "A   ")
        self.assertEqual(items.values[1].values["NAME"], "B   ")

    def test_cli_accepts_pygan_writer_backend(self) -> None:
        args = build_parser().parse_args(["input.h5", "--writer-backend", "pygan"])

        self.assertEqual(args.writer_backend, "pygan")

    def test_direct_conversion_dispatches_to_pygan_backend_and_reports_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_h5 = root / "input.h5"
            output = root / "out.mcompo.txt"
            summary = root / "summary.json"
            input_h5.write_text("not read because converter is patched\n", encoding="utf-8")

            def fake_convert(*args: object, **kwargs: object) -> None:
                output.write_text("fake output\n", encoding="utf-8")

            with patch("openmc2donjon.cli.convert_mgxs_hdf5_with_pygan", side_effect=fake_convert) as convert:
                rc = cli_main(
                    [
                        str(input_h5),
                        "--writer-backend",
                        "pygan",
                        "-o",
                        str(output),
                        "--summary-json",
                        str(summary),
                    ]
                )
            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        convert.assert_called_once()
        self.assertEqual(payload["writer_backend"], "pygan")
        self.assertTrue(payload["converted"])


if __name__ == "__main__":
    unittest.main()
