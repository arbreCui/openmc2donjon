from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from threading import Event, Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.pygan_backend import inspect_pygan_compo
from openmc2donjon.pygan_writer import convert_mgxs_hdf5_with_pygan
from openmc2donjon.writer_compare import compare_writer_backends
from tests.web_test_utils import WEB_AVAILABLE, TestClient


@dataclass(frozen=True, slots=True)
class _History:
    nstates: int
    calculations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ExportObject:
    name: str
    blocks: tuple[lcm_ascii.LcmBlock, ...]


class _FakeArray:
    def __init__(self, values: list[int]) -> None:
        self._values = values

    def tolist(self) -> list[int]:
        return self._values


class _FakeNode:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def keys(self) -> list[str]:
        return list(self._payload)

    def __getitem__(self, key: object) -> object:
        return self._payload[key]  # type: ignore[index]


class _FakeList:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def __getitem__(self, key: object) -> object:
        if not isinstance(key, int):
            raise KeyError(key)
        return self._values[key]


class _InterleavingLcmModule:
    """Exercise the real cwd convention used by PyGan's LCM extension."""

    __file__ = "/fake/lcm.so"

    def __init__(self) -> None:
        self.first_entered = Event()
        self.release_first = Event()
        self._state_lock = Lock()
        self._active = 0
        self._calls = 0
        self.max_active = 0
        self.cwd_violations: list[tuple[Path, Path]] = []

    def new(self, pytype: str, name: str | None = None, **kwargs: object) -> object:
        if pytype == "ASCII":
            pyobj = kwargs.get("pyobj")
            if not isinstance(pyobj, _ExportObject):
                raise TypeError("ASCII export requires an export object")

            def export() -> _ExportObject:
                # Deliberately relative: this is the legacy PyGan behaviour
                # whose process-wide side effect the production lock protects.
                lcm_ascii.write_lcm_ascii(pyobj.blocks, Path(f"_{pyobj.name}"))
                return pyobj

            return self._run_filesystem_call(export)

        if pytype == "LCM_INP":
            if not isinstance(name, str):
                raise TypeError("LCM_INP requires an object name")

            def inspect() -> _FakeNode:
                marker = Path(f"_{name}").read_text(encoding="utf-8").strip()
                calculation = _FakeNode({"MARKER": marker})
                mixture = _FakeNode({"CALCULATIONS": _FakeList([calculation])})
                root = _FakeNode(
                    {
                        "STATE-VECTOR": _FakeArray([1, 1, 1]),
                        "MIXTURES": _FakeList([mixture]),
                    }
                )
                return _FakeNode(
                    {
                        "SIGNATURE": "L_MULTICOMPO",
                        f"ROOT_{marker}": root,
                    }
                )

            return self._run_filesystem_call(inspect)

        raise ValueError(pytype)

    def _run_filesystem_call(self, operation: object) -> object:
        expected_cwd = Path.cwd()
        with self._state_lock:
            self._active += 1
            self._calls += 1
            is_first = self._calls == 1
            self.max_active = max(self.max_active, self._active)
        try:
            if is_first:
                self.first_entered.set()
                if not self.release_first.wait(timeout=5.0):
                    raise TimeoutError("test did not release first PyGan call")
            # Release the GIL inside every extension call so queued Web-style
            # worker threads get a real opportunity to overlap.
            time.sleep(0.004)
            actual_cwd = Path.cwd()
            if actual_cwd != expected_cwd:
                with self._state_lock:
                    self.cwd_violations.append((expected_cwd, actual_cwd))
            if not callable(operation):
                raise TypeError("operation must be callable")
            return operation()
        finally:
            with self._state_lock:
                self._active -= 1


class _FailingLcmModule:
    __file__ = "/fake/lcm.so"

    def new(self, pytype: str, name: str | None = None, **kwargs: object) -> object:
        if pytype == "ASCII":
            raise RuntimeError("synthetic PyGan export failure")
        raise ValueError(pytype)


def _tag_blocks(tag: str) -> list[lcm_ascii.LcmBlock]:
    return [
        lcm_ascii.string_block(1, "SIGNATURE", "L_TEST", width=8),
        lcm_ascii.string_block(1, "TAG", tag, width=16),
    ]


def _fake_history_reader(
    input_h5: str | Path,
    *,
    h_factor_default: float | None = None,
) -> tuple[list[_History], np.ndarray, None]:
    del h_factor_default
    source = Path(input_h5)
    if not source.is_absolute():
        raise AssertionError(f"PyGan input was not made absolute: {source}")
    tag = _read_test_tag(source)
    return [_History(nstates=1, calculations=(tag,))], np.array([1.0, 2.0]), None


def _fake_block_builder(
    calculations: list[str],
    energy_bounds: np.ndarray,
    **kwargs: object,
) -> list[lcm_ascii.LcmBlock]:
    del energy_bounds, kwargs
    return _tag_blocks(calculations[0])


def _fake_pygan_object(
    lcm_module: object,
    blocks: list[lcm_ascii.LcmBlock],
    *,
    object_name: str,
) -> _ExportObject:
    del lcm_module
    return _ExportObject(name=object_name, blocks=tuple(blocks))


def _fake_ascii_converter(
    input_h5: str | Path,
    output_path: str | Path,
    **kwargs: object,
) -> None:
    del kwargs
    source = Path(input_h5)
    output = Path(output_path)
    if not source.is_absolute() or not output.is_absolute():
        raise AssertionError(f"comparison paths were not absolute: {source}, {output}")
    tag = _read_test_tag(source)
    lcm_ascii.write_lcm_ascii(_tag_blocks(tag), output)


def _fake_import(lcm_module: object, name: str) -> object:
    if name == "lcm":
        return lcm_module
    return SimpleNamespace(__file__=f"/fake/{name}.so")


def _read_test_tag(source: Path) -> str:
    import h5py

    if h5py.is_hdf5(source):
        with h5py.File(source, "r") as h5:
            return str(h5.attrs["test_tag"])
    return source.read_text(encoding="utf-8").strip()


class PyGanConcurrencyTests(unittest.TestCase):
    def test_convert_compare_and_inspect_do_not_cross_working_directories(self) -> None:
        fake_lcm = _InterleavingLcmModule()
        original_cwd = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            for index in range(5):
                (root / f"convert-{index}.h5").write_text(
                    f"CONVERT_{index}", encoding="utf-8"
                )
                (root / f"compare-{index}.h5").write_text(
                    f"COMPARE_{index}", encoding="utf-8"
                )
                (root / f"inspect-{index}.compo").write_text(
                    f"INSPECT_{index}", encoding="utf-8"
                )

            os.chdir(root)
            try:
                with (
                    patch(
                        "openmc2donjon.pygan_writer.read_mgxs_hdf5_histories",
                        side_effect=_fake_history_reader,
                    ),
                    patch(
                        "openmc2donjon.pygan_writer.build_multicompo_blocks",
                        side_effect=_fake_block_builder,
                    ),
                    patch(
                        "openmc2donjon.pygan_writer._blocks_to_pygan_object",
                        side_effect=_fake_pygan_object,
                    ),
                    patch(
                        "openmc2donjon.writer_compare.convert_mgxs_hdf5",
                        side_effect=_fake_ascii_converter,
                    ),
                    patch(
                        "openmc2donjon.pygan_backend.importlib.import_module",
                        side_effect=lambda name: _fake_import(fake_lcm, name),
                    ),
                ):
                    futures: list[Future[tuple[str, int, object]]] = []
                    with ThreadPoolExecutor(max_workers=12) as pool:
                        first = pool.submit(self._run_convert, 0)
                        self.assertTrue(fake_lcm.first_entered.wait(timeout=5.0))
                        futures.append(first)
                        for index in range(1, 5):
                            futures.append(pool.submit(self._run_convert, index))
                        for index in range(5):
                            futures.append(pool.submit(self._run_compare, index))
                            futures.append(pool.submit(self._run_inspect, index))
                        try:
                            # The first extension call is still deliberately
                            # blocked. All other requests must be waiting at
                            # the same process guard rather than entering PyGan.
                            time.sleep(0.05)
                            self.assertEqual(fake_lcm.max_active, 1)
                        finally:
                            fake_lcm.release_first.set()
                        results = [future.result(timeout=10.0) for future in futures]

                self.assertEqual(Path.cwd(), root)
            finally:
                fake_lcm.release_first.set()
                os.chdir(original_cwd)

            self.assertEqual(fake_lcm.max_active, 1)
            self.assertEqual(fake_lcm.cwd_violations, [])
            for kind, index, result in results:
                if kind == "convert":
                    self.assertEqual(
                        (root / f"convert-{index}.out").read_text(encoding="utf-8"),
                        lcm_ascii.format_lcm_ascii(_tag_blocks(f"CONVERT_{index}")),
                    )
                elif kind == "compare":
                    self.assertTrue(result.ok)  # type: ignore[union-attr]
                    self.assertEqual(result.input_h5, str(root / f"compare-{index}.h5"))  # type: ignore[union-attr]
                    pygan_output = root / f"compare-{index}-keep" / "pygan.mcompo.txt"
                    self.assertEqual(
                        [
                            block.semantic_tuple()
                            for block in lcm_ascii.read_lcm_ascii(pygan_output)
                        ],
                        [
                            block.semantic_tuple()
                            for block in _tag_blocks(f"COMPARE_{index}")
                        ],
                    )
                else:
                    self.assertEqual(result.path, str(root / f"inspect-{index}.compo"))  # type: ignore[union-attr]
                    self.assertEqual(result.root_name, f"ROOT_INSPECT_{index}")  # type: ignore[union-attr]

    @unittest.skipUnless(WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
    def test_live_web_requests_and_inspection_share_the_same_process_guard(self) -> None:
        import h5py

        from openmc2donjon.web.server import create_app

        fake_lcm = _InterleavingLcmModule()
        original_cwd = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            for index in range(3):
                for prefix in ("web-convert", "web-compare"):
                    with h5py.File(root / f"{prefix}-{index}.h5", "w") as h5:
                        h5.attrs["test_tag"] = f"{prefix.upper().replace('-', '_')}_{index}"
                (root / f"web-inspect-{index}.compo").write_text(
                    f"WEB_INSPECT_{index}", encoding="utf-8"
                )

            if TestClient is None:  # pragma: no cover - guarded by skipUnless
                self.fail("TestClient is unavailable")
            client = TestClient(create_app(mock_mode=False, workspace_root=root))
            os.chdir(root)
            try:
                with (
                    patch(
                        "openmc2donjon.pygan_writer.read_mgxs_hdf5_histories",
                        side_effect=_fake_history_reader,
                    ),
                    patch(
                        "openmc2donjon.pygan_writer.build_multicompo_blocks",
                        side_effect=_fake_block_builder,
                    ),
                    patch(
                        "openmc2donjon.pygan_writer._blocks_to_pygan_object",
                        side_effect=_fake_pygan_object,
                    ),
                    patch(
                        "openmc2donjon.writer_compare.convert_mgxs_hdf5",
                        side_effect=_fake_ascii_converter,
                    ),
                    patch(
                        "openmc2donjon.pygan_backend.importlib.import_module",
                        side_effect=lambda name: _fake_import(fake_lcm, name),
                    ),
                ):
                    futures: list[Future[tuple[str, int, object]]] = []
                    with ThreadPoolExecutor(max_workers=9) as pool:
                        first = pool.submit(self._run_web_convert, client, 0)
                        self.assertTrue(fake_lcm.first_entered.wait(timeout=5.0))
                        futures.append(first)
                        for index in range(1, 3):
                            futures.append(pool.submit(self._run_web_convert, client, index))
                        for index in range(3):
                            futures.append(
                                pool.submit(self._run_web_compare, client, root, index)
                            )
                            futures.append(pool.submit(self._run_web_inspect, index))
                        try:
                            time.sleep(0.05)
                            self.assertEqual(fake_lcm.max_active, 1)
                        finally:
                            fake_lcm.release_first.set()
                        results = [future.result(timeout=10.0) for future in futures]

                self.assertEqual(Path.cwd(), root)
            finally:
                fake_lcm.release_first.set()
                os.chdir(original_cwd)

            self.assertEqual(fake_lcm.max_active, 1)
            self.assertEqual(fake_lcm.cwd_violations, [])
            for kind, index, result in results:
                if kind == "web-convert":
                    self.assertEqual(result.status_code, 200)  # type: ignore[union-attr]
                    self.assertTrue(result.json()["converted"])  # type: ignore[union-attr]
                    output = root / f"web-convert-{index}.out"
                    self.assertEqual(
                        [block.semantic_tuple() for block in lcm_ascii.read_lcm_ascii(output)],
                        [
                            block.semantic_tuple()
                            for block in _tag_blocks(f"WEB_CONVERT_{index}")
                        ],
                    )
                elif kind == "web-compare":
                    self.assertEqual(result.status_code, 200)  # type: ignore[union-attr]
                    self.assertTrue(result.json()["ok"])  # type: ignore[union-attr]
                    pygan_output = (
                        root / f"web-compare-{index}-keep" / "pygan.mcompo.txt"
                    )
                    self.assertEqual(
                        [
                            block.semantic_tuple()
                            for block in lcm_ascii.read_lcm_ascii(pygan_output)
                        ],
                        [
                            block.semantic_tuple()
                            for block in _tag_blocks(f"WEB_COMPARE_{index}")
                        ],
                    )
                else:
                    self.assertEqual(result.path, str(root / f"web-inspect-{index}.compo"))  # type: ignore[union-attr]
                    self.assertEqual(result.root_name, f"ROOT_WEB_INSPECT_{index}")  # type: ignore[union-attr]

    def test_pygan_exception_restores_original_working_directory(self) -> None:
        original_cwd = Path.cwd()
        blocks = _tag_blocks("FAILURE")
        fake_lcm = _FailingLcmModule()

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir).resolve() / "failed.out"
            with (
                patch(
                    "openmc2donjon.pygan_writer._blocks_to_pygan_object",
                    side_effect=_fake_pygan_object,
                ),
                patch(
                    "openmc2donjon.pygan_backend.importlib.import_module",
                    side_effect=lambda name: _fake_import(fake_lcm, name),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic PyGan export failure"):
                    from openmc2donjon.pygan_writer import write_lcm_blocks_with_pygan

                    write_lcm_blocks_with_pygan(blocks, output)

        self.assertEqual(Path.cwd(), original_cwd)

    @staticmethod
    def _run_convert(index: int) -> tuple[str, int, None]:
        convert_mgxs_hdf5_with_pygan(
            f"convert-{index}.h5",
            f"convert-{index}.out",
        )
        return "convert", index, None

    @staticmethod
    def _run_compare(index: int) -> tuple[str, int, object]:
        report = compare_writer_backends(
            f"compare-{index}.h5",
            keep_dir=f"compare-{index}-keep",
        )
        return "compare", index, report

    @staticmethod
    def _run_inspect(index: int) -> tuple[str, int, object]:
        inspection = inspect_pygan_compo(f"inspect-{index}.compo")
        return "inspect", index, inspection

    @staticmethod
    def _run_web_convert(client: object, index: int) -> tuple[str, int, object]:
        response = client.post(  # type: ignore[attr-defined]
            "/api/convert",
            json={
                "input_path": f"~/web-convert-{index}.h5",
                "output_path": f"~/web-convert-{index}.out",
                "format": "multicompo",
                "writer_backend": "pygan",
                "dry_run": False,
                "overwrite": True,
                "check": False,
                "production": False,
            },
        )
        return "web-convert", index, response

    @staticmethod
    def _run_web_compare(
        client: object,
        root: Path,
        index: int,
    ) -> tuple[str, int, object]:
        response = client.post(  # type: ignore[attr-defined]
            "/api/pygan/compare-writers",
            json={
                "input_h5": f"~/web-compare-{index}.h5",
                "format": "multicompo",
                "keep_dir": str(root / f"web-compare-{index}-keep"),
            },
        )
        return "web-compare", index, response

    @staticmethod
    def _run_web_inspect(index: int) -> tuple[str, int, object]:
        inspection = inspect_pygan_compo(f"web-inspect-{index}.compo")
        return "web-inspect", index, inspection


if __name__ == "__main__":
    unittest.main()
