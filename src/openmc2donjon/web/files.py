"""File-browser and file-status routes for the localhost web UI."""

from __future__ import annotations

from typing import Any

from .filesystem import FilesystemScope


FILES_SCHEMA = "openmc2donjon.files.v1"
FILE_STATUS_SCHEMA = "openmc2donjon.file-status.v1"
FILES_ENTRY_LIMIT = 500

# Synthetic directory tree returned by the file browser when running in
# ``--mock``. Three levels deep, mimicking the typical ``$HOME/openmc-runs``
# layout users will navigate in production.
_MOCK_HOME = "/mock/home"
_MOCK_TREE: dict[str, list[tuple[str, str, int | None]]] = {
    _MOCK_HOME: [
        ("openmc-runs", "dir", None),
        ("scratch", "dir", None),
        ("notes.txt", "file", 1024),
    ],
    f"{_MOCK_HOME}/openmc-runs": [
        ("c5g7", "dir", None),
        ("openmc-sph-minicase", "dir", None),
        ("u238_33g", "dir", None),
    ],
    f"{_MOCK_HOME}/openmc-runs/c5g7": [
        ("handoff.h5", "file", 832_000),
        ("handoff_aug.h5", "file", 856_000),
        ("bundle", "dir", None),
        ("README.md", "file", 1_024),
    ],
    f"{_MOCK_HOME}/openmc-runs/c5g7/bundle": [
        ("manifest.json", "file", 2_048),
        ("handoff.h5", "file", 832_000),
        ("out.mcompo.txt", "file", 184_320),
        ("convert_summary.json", "file", 8_192),
    ],
    f"{_MOCK_HOME}/openmc-runs/openmc-sph-minicase": [
        ("mgxs_library.h5", "file", 96_000),
        ("ce_statepoint.h5", "file", 1_200_000),
        ("mg_statepoint.h5", "file", 1_080_000),
        ("openmc_ce_flux.h5", "file", 18_000),
        ("openmc_mg_flux.h5", "file", 18_000),
        ("openmc_sph_sidecar.h5", "file", 22_000),
        ("openmc_sph.csv", "file", 1_500),
        ("mgxs_with_openmc_sph.h5", "file", 104_000),
        ("out.mcompo.txt", "file", 36_000),
        ("out.macrolib.txt", "file", 42_000),
        ("physics_summary.json", "file", 3_800),
        ("physics_summary.md", "file", 1_600),
    ],
    f"{_MOCK_HOME}/openmc-runs/u238_33g": [
        ("mgxs.h5", "file", 1_240_000),
        ("mgxs_with_sph.h5", "file", 1_250_000),
    ],
    f"{_MOCK_HOME}/scratch": [
        ("tmp_run.h5", "file", 256_000),
    ],
}


def register_file_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope,
) -> None:
    """Register file browser and file-status endpoints."""

    from fastapi import HTTPException, Query

    @app.get("/api/files")
    def api_files(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _mock_list_dir(path, HTTPException)
        return _list_dir(path, HTTPException, filesystem_scope)

    @app.get("/api/file-status")
    def api_file_status(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _mock_file_status(path)
        return _file_status(path, HTTPException, filesystem_scope)


def _list_dir(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any]:
    """Real-filesystem implementation of ``/api/files`` (live mode)."""

    real = filesystem_scope.resolve(raw, http_exception)
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_dir():
        raise http_exception(
            status_code=400, detail=f"path is not a directory: {raw}"
        )
    try:
        children = sorted(real.iterdir(), key=lambda p: p.name.lower())
    except PermissionError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read directory: {exc}"
        ) from exc
    except OSError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read directory: {exc}"
        ) from exc

    entries: list[dict[str, Any]] = []
    for child in children[:FILES_ENTRY_LIMIT]:
        try:
            is_dir = child.is_dir()
            size: int | None = None
            if not is_dir:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = None
        except OSError:
            # Broken symlink or vanished mid-listing; skip it rather
            # than fail the whole request.
            continue
        entries.append(
            {
                "name": child.name,
                "kind": "dir" if is_dir else "file",
                "size": size,
            }
        )
    parent = None if real.parent == real else str(real.parent)
    return _files_payload(
        str(real),
        parent,
        entries,
        total_entries=len(children),
        entry_limit=FILES_ENTRY_LIMIT,
    )


def _file_status(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> dict[str, Any]:
    """Single-path status probe for live-mode workflow hints.

    Missing paths are a normal status, not an HTTP error: the frontend
    uses this to tell users which smoke artifacts still need to be
    generated. Permission / OS errors are surfaced in the payload so a
    card can show "unreadable" without breaking the whole page.
    """

    real = filesystem_scope.resolve(raw, http_exception)
    try:
        if not real.exists():
            return _file_status_payload(
                path=str(real),
                exists=False,
                kind="missing",
                size=None,
                detail="path not found",
            )
        if real.is_dir():
            return _file_status_payload(
                path=str(real),
                exists=True,
                kind="dir",
                size=None,
                detail=None,
            )
        if real.is_file():
            try:
                size = real.stat().st_size
            except OSError:
                size = None
            return _file_status_payload(
                path=str(real),
                exists=True,
                kind="file",
                size=size,
                detail=None,
            )
        return _file_status_payload(
            path=str(real),
            exists=True,
            kind="other",
            size=None,
            detail="path exists but is not a regular file or directory",
        )
    except OSError as exc:
        return _file_status_payload(
            path=str(real),
            exists=False,
            kind="unknown",
            size=None,
            detail=f"cannot stat path: {exc}",
        )


def _mock_list_dir(raw: str, http_exception: Any) -> dict[str, Any]:
    """Mock-mode implementation of ``/api/files`` (returns the bundled tree)."""

    resolved = _resolve_mock_path(raw)

    if resolved not in _MOCK_TREE:
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    entries = [
        {"name": name, "kind": kind, "size": size}
        for name, kind, size in _MOCK_TREE[resolved]
    ]
    # Parent navigation is honest about the mock universe: only walk
    # up if the would-be parent is itself a node in the tree. That
    # way ``/mock/home`` ends up with ``parent = None`` (disables the
    # frontend "up" button) instead of pointing at ``/mock`` which
    # would 404 on the next request.
    parent_candidate = resolved.rsplit("/", 1)[0]
    parent = parent_candidate if parent_candidate in _MOCK_TREE else None
    return _files_payload(resolved, parent, entries)


def _mock_file_status(raw: str) -> dict[str, Any]:
    """Mock-mode single-path status probe using ``_MOCK_TREE``."""

    resolved = _resolve_mock_path(raw)
    if resolved in _MOCK_TREE:
        return _file_status_payload(
            path=resolved,
            exists=True,
            kind="dir",
            size=None,
            detail=None,
        )
    parent, _, name = resolved.rpartition("/")
    for entry_name, kind, size in _MOCK_TREE.get(parent, []):
        if entry_name == name:
            return _file_status_payload(
                path=resolved,
                exists=True,
                kind=kind,
                size=size,
                detail=None,
            )
    return _file_status_payload(
        path=resolved,
        exists=False,
        kind="missing",
        size=None,
        detail="path not found",
    )


def _resolve_mock_path(raw: str) -> str:
    if raw in ("~", "~/"):
        resolved = _MOCK_HOME
    elif raw.startswith("~/"):
        resolved = f"{_MOCK_HOME}/{raw[2:]}"
    else:
        resolved = raw
    return resolved.rstrip("/") or "/"


def _files_payload(
    path: str,
    parent: str | None,
    entries: list[dict[str, Any]],
    *,
    total_entries: int | None = None,
    entry_limit: int | None = None,
) -> dict[str, Any]:
    total = len(entries) if total_entries is None else total_entries
    limit = len(entries) if entry_limit is None else entry_limit
    return {
        "schema": FILES_SCHEMA,
        "path": path,
        "parent": parent,
        "entries": entries,
        "total_entries": total,
        "entry_limit": limit,
        "truncated": total > len(entries),
    }


def _file_status_payload(
    *,
    path: str,
    exists: bool,
    kind: str,
    size: int | None,
    detail: str | None,
) -> dict[str, Any]:
    return {
        "schema": FILE_STATUS_SCHEMA,
        "path": path,
        "exists": exists,
        "kind": kind,
        "size": size,
        "detail": detail,
    }
