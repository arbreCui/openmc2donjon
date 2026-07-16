"""Optional PyGan integration helpers.

The production converter intentionally keeps the pure Python ASCII writer as
the default backend.  PyGan is treated as an optional DRAGON/DONJON integration
layer for validation, inspection, and future alternate writers.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from types import ModuleType
from typing import Any


PYGAN_MODULES = ("lcm", "lifo", "cle2000")
PYGAN_INSTALL_HINT = (
    "Install PyGan from the DRAGON/DONJON source tree, for example: "
    "cd <dragon-root>/PyGan && make pip=1 donjon"
)
PYGAN_ROLE = (
    "optional DRAGON/DONJON validation and integration backend; "
    "the default converter writer remains pure Python ASCII"
)


# PyGan's legacy LCM import/export API uses the process working directory as
# an implicit file argument.  ``os.chdir`` is process-global, so concurrent
# localhost Web requests must serialize every PyGan filesystem operation, not
# merely the two calls to ``os.chdir``.  An RLock is required because a full
# conversion enters the guard and then calls the lower-level guarded writer.
_PYGAN_PROCESS_LOCK = RLock()


@contextmanager
def pygan_process_guard() -> Iterator[None]:
    """Serialize a complete PyGan filesystem operation within this process.

    Callers should enter this guard *before* resolving relative paths.  This
    prevents another PyGan request from temporarily changing the process cwd
    while those paths are interpreted.
    """

    with _PYGAN_PROCESS_LOCK:
        yield


@contextmanager
def pygan_working_directory(path: str | Path) -> Iterator[Path]:
    """Temporarily enter ``path`` under the shared PyGan process lock.

    The original directory is restored in ``finally`` even when a PyGan
    extension raises.  On POSIX, an open directory descriptor makes recovery
    robust if the original directory is renamed while PyGan is running.
    """

    with pygan_process_guard():
        target = Path(path).expanduser().resolve()
        original = Path.cwd()
        restore_fd: int | None = None
        if hasattr(os, "fchdir"):
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            restore_fd = os.open(original, flags)
        try:
            os.chdir(target)
            yield target
        finally:
            try:
                if restore_fd is None:
                    os.chdir(original)
                else:
                    os.fchdir(restore_fd)
            finally:
                if restore_fd is not None:
                    os.close(restore_fd)


@dataclass(frozen=True, slots=True)
class PyGanModuleStatus:
    name: str
    available: bool
    module_file: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PyGanStatus:
    available: bool
    modules: tuple[PyGanModuleStatus, ...]
    role: str = PYGAN_ROLE
    install_hint: str = PYGAN_INSTALL_HINT

    @property
    def missing_modules(self) -> tuple[str, ...]:
        return tuple(module.name for module in self.modules if not module.available)

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "role": self.role,
            "install_hint": self.install_hint,
            "modules": [
                {
                    "name": module.name,
                    "available": module.available,
                    "module_file": module.module_file,
                    "error": module.error,
                }
                for module in self.modules
            ],
            "missing_modules": list(self.missing_modules),
        }


@dataclass(frozen=True, slots=True)
class PyGanCompoInspection:
    path: str
    object_name: str
    signature: str | None
    top_keys: tuple[str, ...]
    root_name: str
    root_keys: tuple[str, ...]
    state_vector: tuple[int, ...] | None
    mixture_count: int | None
    calculation_count: int | None
    first_mixture_keys: tuple[str, ...]
    first_calculation_keys: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "openmc2donjon.pygan-compo-inspect.v1",
            "path": self.path,
            "object_name": self.object_name,
            "signature": self.signature,
            "top_keys": list(self.top_keys),
            "root_name": self.root_name,
            "root_keys": list(self.root_keys),
            "state_vector": list(self.state_vector) if self.state_vector is not None else None,
            "mixture_count": self.mixture_count,
            "calculation_count": self.calculation_count,
            "first_mixture_keys": list(self.first_mixture_keys),
            "first_calculation_keys": list(self.first_calculation_keys),
        }


def probe_pygan() -> PyGanStatus:
    """Return import status for the optional PyGan modules."""

    with pygan_process_guard():
        modules = tuple(_probe_module(name) for name in PYGAN_MODULES)
        return PyGanStatus(
            available=all(module.available for module in modules),
            modules=modules,
        )


def require_pygan() -> tuple[ModuleType, ModuleType, ModuleType]:
    """Import PyGan modules or raise a user-facing error."""

    with pygan_process_guard():
        status = probe_pygan()
        if not status.available:
            missing = ", ".join(status.missing_modules)
            raise RuntimeError(
                f"PyGan backend is not available; missing: {missing}. {status.install_hint}"
            )
        return tuple(importlib.import_module(name) for name in PYGAN_MODULES)  # type: ignore[return-value]


def inspect_pygan_compo(path: str | Path, *, root_name: str | None = None) -> PyGanCompoInspection:
    """Inspect a DRAGON/DONJON LCM ASCII object using PyGan.

    PyGan's ``LCM_INP`` loader opens ``_<name>`` in the current directory rather
    than the literal path passed by the caller.  This helper hides that
    historical convention by creating a temporary ``_<basename>`` link to the
    requested file, then reading the object from that temporary directory.
    """

    with pygan_process_guard():
        source = Path(path).expanduser().resolve()
        lcm, _, _ = require_pygan()
        if not source.is_file():
            raise FileNotFoundError(source)
        if len(source.name) > 71:
            raise ValueError(f"{source.name!r} is too long for PyGan LCM_INP import")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir).resolve()
            import_name = source.name
            _stage_pygan_input(source, tmp / f"_{import_name}")
            with pygan_working_directory(tmp):
                try:
                    obj = lcm.new("LCM_INP", import_name)
                except Exception as exc:  # noqa: BLE001 - PyGan exposes extension-specific exceptions.
                    raise RuntimeError(f"PyGan failed to open {source}: {exc}") from exc
                return _inspect_lcm_object(
                    obj,
                    source=source,
                    object_name=import_name,
                    root_name=root_name,
                )


def _probe_module(name: str) -> PyGanModuleStatus:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - import can fail with loader-specific exceptions.
        return PyGanModuleStatus(
            name=name,
            available=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    return PyGanModuleStatus(
        name=name,
        available=True,
        module_file=getattr(module, "__file__", None),
    )


def _stage_pygan_input(source: Path, staged: Path) -> None:
    try:
        staged.symlink_to(source)
    except OSError:
        shutil.copy2(source, staged)


def _inspect_lcm_object(
    obj: Any,
    *,
    source: Path,
    object_name: str,
    root_name: str | None,
) -> PyGanCompoInspection:
    top_keys = _keys(obj)
    signature = _string_or_none(_maybe_get(obj, "SIGNATURE"))
    selected_root_name = _select_root_name(top_keys, root_name)
    root = _required_get(obj, selected_root_name, f"root {selected_root_name!r}")
    root_keys = _keys(root)
    state_vector = _int_tuple_or_none(_maybe_get(root, "STATE-VECTOR"))

    mixture_count = state_vector[0] if state_vector else None
    calculation_count = state_vector[2] if state_vector and len(state_vector) >= 3 else None
    first_mixture_keys: tuple[str, ...] = ()
    first_calculation_keys: tuple[str, ...] = ()
    first_mixture = _maybe_get_index(_maybe_get(root, "MIXTURES"), 0)
    if first_mixture is not None:
        first_mixture_keys = _keys(first_mixture)
        first_calculation = _maybe_get_index(_maybe_get(first_mixture, "CALCULATIONS"), 0)
        if first_calculation is not None:
            first_calculation_keys = _keys(first_calculation)

    return PyGanCompoInspection(
        path=str(source),
        object_name=object_name,
        signature=signature,
        top_keys=top_keys,
        root_name=selected_root_name,
        root_keys=root_keys,
        state_vector=state_vector,
        mixture_count=mixture_count,
        calculation_count=calculation_count,
        first_mixture_keys=first_mixture_keys,
        first_calculation_keys=first_calculation_keys,
    )


def _select_root_name(top_keys: tuple[str, ...], root_name: str | None) -> str:
    if root_name is not None:
        if root_name not in top_keys:
            raise KeyError(f"root {root_name!r} not found; available top-level keys: {', '.join(top_keys)}")
        return root_name
    candidates = tuple(key for key in top_keys if key != "SIGNATURE")
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise KeyError("no top-level LCM root found beside SIGNATURE")
    raise ValueError(f"multiple top-level roots found; pass --root-name ({', '.join(candidates)})")


def _keys(obj: Any) -> tuple[str, ...]:
    try:
        return tuple(str(key) for key in obj.keys())
    except Exception:  # noqa: BLE001 - PyGan list/object wrappers vary by node type.
        return ()


def _maybe_get(obj: Any, key: str) -> Any | None:
    if obj is None:
        return None
    try:
        return obj[key]
    except Exception:  # noqa: BLE001 - absent PyGan keys raise extension-specific exceptions.
        return None


def _required_get(obj: Any, key: str, label: str) -> Any:
    try:
        return obj[key]
    except Exception as exc:  # noqa: BLE001 - absent PyGan keys raise extension-specific exceptions.
        raise KeyError(f"{label} is missing") from exc


def _maybe_get_index(obj: Any, index: int) -> Any | None:
    if obj is None:
        return None
    try:
        return obj[index]
    except Exception:  # noqa: BLE001 - absent PyGan list items raise extension-specific exceptions.
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_tuple_or_none(value: Any) -> tuple[int, ...] | None:
    if value is None:
        return None
    raw = value.tolist() if hasattr(value, "tolist") else value
    try:
        return tuple(int(item) for item in raw)
    except TypeError:
        return None
