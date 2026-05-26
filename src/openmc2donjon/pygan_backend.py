"""Optional PyGan integration helpers.

The production converter intentionally keeps the pure Python ASCII writer as
the default backend.  PyGan is treated as an optional DRAGON/DONJON integration
layer for validation, inspection, and future alternate writers.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from types import ModuleType


PYGAN_MODULES = ("lcm", "lifo", "cle2000")
PYGAN_INSTALL_HINT = (
    "Install PyGan from the DRAGON/DONJON source tree, for example: "
    "cd /Users/wen/dragon-5.1/PyGan && make pip=1 donjon"
)
PYGAN_ROLE = (
    "optional DRAGON/DONJON validation and integration backend; "
    "the default converter writer remains pure Python ASCII"
)


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


def probe_pygan() -> PyGanStatus:
    """Return import status for the optional PyGan modules."""

    modules = tuple(_probe_module(name) for name in PYGAN_MODULES)
    return PyGanStatus(
        available=all(module.available for module in modules),
        modules=modules,
    )


def require_pygan() -> tuple[ModuleType, ModuleType, ModuleType]:
    """Import PyGan modules or raise a user-facing error."""

    status = probe_pygan()
    if not status.available:
        missing = ", ".join(status.missing_modules)
        raise RuntimeError(f"PyGan backend is not available; missing: {missing}. {status.install_hint}")
    return tuple(importlib.import_module(name) for name in PYGAN_MODULES)  # type: ignore[return-value]


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
