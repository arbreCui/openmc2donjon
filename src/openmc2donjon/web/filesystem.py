"""Filesystem scope helpers for localhost web routes.

The web server is primarily a localhost convenience layer, but users can
bind it to a non-loopback host. In that case every live-mode endpoint
that reads or writes local paths should go through ``FilesystemScope``
so a configured workspace root is enforced consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FilesystemScope:
    """Optional workspace-root guard for live-mode filesystem access."""

    root: Path | None = None

    @classmethod
    def from_raw_root(cls, raw: str | Path | None) -> "FilesystemScope":
        if raw is None:
            return cls(root=None)
        return cls(root=Path(raw).expanduser().resolve())

    @property
    def mode(self) -> str:
        return "workspace" if self.root is not None else "unrestricted"

    def as_dict(self, *, mock_mode: bool) -> dict[str, str | None]:
        if mock_mode:
            return {"mode": "mock", "workspace_root": None}
        return {
            "mode": self.mode,
            "workspace_root": str(self.root) if self.root is not None else None,
        }

    def resolve(self, raw: str | Path, http_exception: Any) -> Path:
        """Resolve ``raw`` and reject it when outside the configured root."""

        real = self._path(raw).resolve()
        return self.enforce(real, http_exception)

    def enforce(self, path: Path, http_exception: Any) -> Path:
        """Reject ``path`` when this scope has a root and path escapes it."""

        real = self._path(path).resolve()
        if self.root is not None and not _is_relative_to(real, self.root):
            raise http_exception(
                status_code=403,
                detail=(
                    "path is outside web workspace root: "
                    f"{real} (workspace root: {self.root})"
                ),
            )
        return real

    def candidate(self, raw: str | Path) -> Path:
        """Return a user-facing path with workspace ``~`` aliases applied."""

        return self._path(raw)

    def _path(self, raw: str | Path) -> Path:
        if self.root is not None and isinstance(raw, str):
            stripped = raw.strip()
            if stripped in {"~", "."}:
                return self.root
            if stripped.startswith("~/"):
                return self.root / stripped[2:]
        return Path(raw).expanduser()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
