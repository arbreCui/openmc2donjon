"""FastAPI application factory for the openmc2donjon web UI.

Endpoints (M1 scope):

- ``GET /api/health`` - backend liveness + mock flag + package version.
- ``GET /api/commands`` - web/CLI command catalog used by the command
  workspace page.
- ``GET /api/inspect?path=...`` - file-level summary of an MGXS HDF5
  handoff, plus standard energy-mesh ID match when present.
- ``GET /api/inspect/mixture?path=...&mixture=...&moment=0`` - per-mixture
  cross sections and one scatter moment.
- ``GET /api/openmc-sph-summary?path=...`` - read-only OpenMC CE/MG
  physics summary produced by the current OpenMC-side SPH route.
- ``GET /api/text-preview?path=...`` - bounded UTF-8/ASCII preview for
  generated text artifacts such as ``.mcompo.txt`` and ``.macrolib.txt``.
- ``GET /api/file-status?path=...`` - single-path existence / kind /
  size probe used by localhost workflow cards.
- ``GET /api/bundle/inspect?manifest=...`` - read-only bundle manifest
  validation summary used by converter delivery cards.

The ``create_app`` factory keeps the mock flag out of module globals so
the CLI ``serve`` command can pass it in explicitly. Mock mode returns
bundled fixture JSONs from ``src/openmc2donjon/web/fixtures/`` so the
frontend can be exercised without a real HDF5 on disk.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__
from .._logging import get_logger
from ..energy_groups import identify_mesh
from ..mgxs_inspect import _report_payload, inspect_file
from ..mgxs_physics_checks import scatter_moment_matrix
from ..pygan_backend import probe_pygan
from .bundle import register_bundle_routes
from .commands import register_command_routes
from .convert import register_convert_routes
from .filesystem import FilesystemScope
from .openmc_workflow import register_openmc_workflow_routes
from .openmc_sph_summary import register_openmc_sph_summary_routes
from .pygan import register_pygan_routes
from .text_preview import (
    TEXT_PREVIEW_SCHEMA as TEXT_PREVIEW_SCHEMA,
    register_text_preview_routes,
)


logger = get_logger("web.server")

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

INSPECT_SCHEMA = "openmc2donjon.mgxs-inspect.v1"
MIXTURE_SCHEMA = "openmc2donjon.mgxs-mixture.v1"
FILES_SCHEMA = "openmc2donjon.files.v1"
FILE_STATUS_SCHEMA = "openmc2donjon.file-status.v1"
FILES_ENTRY_LIMIT = 500
# Hard caps on the ``/api/inspect`` peek panel so a pathological HDF5
# (hundreds of root attrs, thousands of top-level datasets) can't blow
# up the response payload or the frontend layout. The totals stay
# accurate so the UI can honestly say "showing 200 of 1432 entries".
_PEEK_MAX_ROOT_ATTRS = 50
_PEEK_MAX_TOP_LEVEL_KEYS = 200

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

# Cross sections to extract when reading per-mixture detail. ``chi`` is
# included so the frontend can show source spectrum alongside reaction
# rates; it lives on a different axis than the absorption / fission
# group so the plot UI should treat it separately.
_MIXTURE_XS_DATASETS: tuple[str, ...] = (
    "total",
    "absorption",
    "fission",
    "nu_fission",
    "chi",
)


def create_app(
    *,
    mock_mode: bool = False,
    extra_origins: tuple[str, ...] = (),
    workspace_root: str | Path | None = None,
) -> Any:
    """Build a configured FastAPI application instance.

    The CORS allow-list always includes ``DEFAULT_CORS_ORIGINS`` (the
    Next.js dev server). Any ``extra_origins`` are appended and the
    resulting list is order-preserving deduplicated, so callers can
    grow the list without losing the defaults.

    Importing FastAPI lazily lets the package work without the ``web``
    extra installed for users who only need the CLI.
    """

    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - exercised via CLI handler
        raise RuntimeError(
            "openmc2donjon web extras are not installed. "
            'Install with: pip install -e ".[web]"',
        ) from exc

    filesystem_scope = FilesystemScope.from_raw_root(workspace_root)

    app = FastAPI(
        title="openmc2donjon",
        description="Web interface for the OpenMC -> DRAGON/DONJON handoff pipeline.",
        version=__version__,
    )

    allow_origins = list(dict.fromkeys((*DEFAULT_CORS_ORIGINS, *extra_origins)))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mock_mode": mock_mode,
            "version": __version__,
            "pygan_backend": _cached_pygan_status(),
            "filesystem_scope": filesystem_scope.as_dict(mock_mode=mock_mode),
        }

    register_command_routes(app)
    register_openmc_workflow_routes(
        app,
        mock_mode=mock_mode,
        filesystem_scope=filesystem_scope,
    )
    register_openmc_sph_summary_routes(
        app,
        mock_mode=mock_mode,
        filesystem_scope=filesystem_scope,
    )
    register_pygan_routes(app, mock_mode=mock_mode, filesystem_scope=filesystem_scope)

    @app.get("/api/inspect")
    def api_inspect(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _load_fixture("inspect_handoff.json")
        real_path = _validate_hdf5_path(path, HTTPException, filesystem_scope)
        try:
            report = inspect_file(real_path)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=422, detail=f"inspect failed: {exc}"
            ) from exc
        payload = _report_payload(report)
        payload["schema"] = INSPECT_SCHEMA
        bounds, mesh_match = _read_bounds_and_mesh(real_path)
        payload["energy_bounds"] = bounds
        payload["mesh_match"] = mesh_match
        # Generic HDF5 peek (root attrs + top-level entries) makes the
        # response useful even for files that don't match the MGXS
        # contract (boundary currents, ADF sidecars, etc.): the user
        # at least sees what KIND of HDF5 they pointed at instead of
        # a bare "0 mixtures, FAIL".
        peek = _read_top_level_peek(real_path)
        payload.update(peek)
        return payload

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

    register_text_preview_routes(
        app,
        mock_mode=mock_mode,
        filesystem_scope=filesystem_scope,
    )

    register_convert_routes(app, mock_mode=mock_mode, filesystem_scope=filesystem_scope)
    register_bundle_routes(app, mock_mode=mock_mode, filesystem_scope=filesystem_scope)

    @app.get("/api/inspect/mixture")
    def api_inspect_mixture(
        path: str = Query(..., min_length=1),
        mixture: str = Query(..., min_length=1),
        moment: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_mixture(mixture, moment, HTTPException)
        real_path = _validate_hdf5_path(path, HTTPException, filesystem_scope)
        try:
            return _read_mixture_detail(real_path, mixture, moment, HTTPException)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"mixture read failed: {exc}"
            ) from exc

    if mock_mode:
        logger.info("openmc2donjon web server starting in MOCK mode")
    else:
        logger.info("openmc2donjon web server starting in LIVE mode")

    return app


def _validate_hdf5_path(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> Path:
    """Resolve a user-supplied path and confirm it is a readable HDF5 file."""

    import h5py

    real = filesystem_scope.resolve(raw, http_exception)
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    try:
        is_hdf5 = h5py.is_hdf5(str(real))
    except OSError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read path: {exc}"
        ) from exc
    if not is_hdf5:
        raise http_exception(status_code=400, detail=f"not an HDF5 file: {raw}")
    return real


@lru_cache(maxsize=1)
def _cached_pygan_status() -> dict[str, object]:
    return probe_pygan().as_dict()


def _read_top_level_peek(real_path: Path) -> dict[str, Any]:
    """Read root attrs and one-level group/dataset names for a peek panel.

    Returns a dict with five keys:

    - ``root_attrs``: list of ``{name, value}`` (scalar / short-vector
      attrs only; unsupported dtypes are silently dropped).
    - ``top_level_keys``: list of ``{name, kind, shape, dtype}`` for
      the immediate children of the HDF5 root.
    - ``root_attrs_total``: total attribute count in the file (before
      cap / drop).
    - ``top_level_keys_total``: total root-level entry count in the
      file (before cap).
    - ``peek_truncated``: convenience flag — true when either list is
      shorter than its total. Frontend renders a "showing X of Y" hint
      so a 1432-entry file doesn't silently hide most of itself.

    Returns empty lists / zero totals if the file can't be opened.
    """

    import h5py

    empty = {
        "root_attrs": [],
        "top_level_keys": [],
        "root_attrs_total": 0,
        "top_level_keys_total": 0,
        "peek_truncated": False,
    }
    try:
        with h5py.File(real_path, "r") as h5:
            attr_names = list(h5.attrs.keys())
            root_attrs: list[dict[str, Any]] = []
            for name in attr_names:
                if len(root_attrs) >= _PEEK_MAX_ROOT_ATTRS:
                    break
                value = _attr_to_jsonable(h5.attrs[name])
                if value is None:
                    continue
                root_attrs.append({"name": str(name), "value": value})

            all_top_names = sorted(h5)
            top_level_keys: list[dict[str, Any]] = []
            for name in all_top_names[:_PEEK_MAX_TOP_LEVEL_KEYS]:
                node = h5[name]
                if isinstance(node, h5py.Group):
                    top_level_keys.append(
                        {
                            "name": str(name),
                            "kind": "group",
                            "shape": None,
                            "dtype": None,
                        }
                    )
                else:
                    dataset = node
                    try:
                        shape = list(dataset.shape)
                        dtype = str(dataset.dtype)
                    except (AttributeError, OSError):
                        shape = None
                        dtype = None
                    top_level_keys.append(
                        {
                            "name": str(name),
                            "kind": "dataset",
                            "shape": shape,
                            "dtype": dtype,
                        }
                    )
            root_attrs_total = len(attr_names)
            top_level_keys_total = len(all_top_names)
    except (OSError, ValueError, KeyError):
        return empty
    return {
        "root_attrs": root_attrs,
        "top_level_keys": top_level_keys,
        "root_attrs_total": root_attrs_total,
        "top_level_keys_total": top_level_keys_total,
        "peek_truncated": (
            len(root_attrs) < root_attrs_total
            or len(top_level_keys) < top_level_keys_total
        ),
    }


def _attr_to_jsonable(value: Any) -> Any:
    """Convert an HDF5 attribute value to a JSON-friendly scalar.

    Returns ``None`` for blobs we don't want to ship (large arrays,
    unsupported dtypes), the caller will skip them. Bytes / numpy
    strings are decoded; numpy scalars are unwrapped via ``.item()``.
    """

    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        return value
    if hasattr(value, "item") and not hasattr(value, "shape"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            return None
    if hasattr(value, "shape"):
        shape = value.shape
        if shape == ():
            try:
                return _attr_to_jsonable(value.item())
            except (AttributeError, ValueError):
                return None
        if len(shape) == 1 and shape[0] <= 8:
            # Short 1D vectors render nicely as a list (energy bounds,
            # small enumerations, etc.); anything bigger gets dropped
            # to keep the peek payload bounded.
            try:
                return [_attr_to_jsonable(v) for v in value.tolist()]
            except (AttributeError, ValueError):
                return None
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 8:
        return [_attr_to_jsonable(v) for v in value]
    return None


def _read_bounds_and_mesh(
    real_path: Path,
) -> tuple[list[float] | None, dict[str, Any] | None]:
    """Read ``/energy_bounds`` once and reuse it for mesh ID detection.

    Returns ``(bounds_list, mesh_dict)``. Either side can be ``None``: no
    ``energy_bounds`` dataset means no bounds and no mesh match; bounds
    present but no catalog hit means bounds list with ``mesh_dict=None``.
    """

    import h5py

    try:
        with h5py.File(real_path, "r") as h5:
            if "energy_bounds" not in h5:
                return None, None
            bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    except (OSError, KeyError, ValueError):
        return None, None
    bounds_list = bounds.tolist()
    mesh = identify_mesh(bounds)
    if mesh is None:
        return bounds_list, None
    return bounds_list, {
        "id": mesh.mesh_id,
        "name": mesh.name,
        "short": mesh.short,
        "n_groups": mesh.n_groups,
        "purpose": mesh.purpose,
        "description": mesh.description,
    }


def _read_mixture_detail(
    real_path: Path,
    mixture_name: str,
    moment: int,
    http_exception: Any,
) -> dict[str, Any]:
    """Pull per-mixture cross sections and one scatter moment out of HDF5."""

    import h5py

    with h5py.File(real_path, "r") as h5:
        mixtures = h5.get("mixtures")
        if mixtures is None:
            raise http_exception(
                status_code=422, detail="HDF5 has no /mixtures group"
            )
        mix_group = mixtures.get(mixture_name)
        if mix_group is None:
            raise http_exception(
                status_code=404,
                detail=f"mixture not found: {mixture_name}",
            )

        ngroups_attr = h5.attrs.get("energy_groups")
        try:
            ngroups = int(ngroups_attr) if ngroups_attr is not None else None
        except (TypeError, ValueError):
            ngroups = None

        legendre_attr = h5.attrs.get("legendre_order")
        try:
            legendre_order = int(legendre_attr) if legendre_attr is not None else None
        except (TypeError, ValueError):
            legendre_order = None

        cross_sections: dict[str, list[float] | None] = {}
        for name in _MIXTURE_XS_DATASETS:
            if name in mix_group:
                cross_sections[name] = np.asarray(
                    mix_group[name][:], dtype=float
                ).reshape(-1).tolist()
            else:
                cross_sections[name] = None

        volume = _float_attr(mix_group.attrs, "volume")
        temperature = _float_attr(mix_group.attrs, "temperature")

        scatter_payload = _scatter_moment_payload(
            mix_group, ngroups=ngroups, legendre_order=legendre_order, moment=moment
        )
        if scatter_payload is not None and not scatter_payload.get("values"):
            # Requested moment out of range; surface it as a 404 so the
            # frontend can fall back to moment=0 rather than render an
            # empty heatmap.
            raise http_exception(
                status_code=404,
                detail=(
                    f"scatter moment {moment} not available for "
                    f"mixture {mixture_name}"
                ),
            )

        return {
            "schema": MIXTURE_SCHEMA,
            "path": str(real_path),
            "mixture": mixture_name,
            "energy_groups": ngroups,
            "legendre_order": legendre_order,
            "volume": volume,
            "temperature": temperature,
            "cross_sections": cross_sections,
            "scatter": scatter_payload,
        }


def _scatter_moment_payload(
    mix_group: Any,
    *,
    ngroups: int | None,
    legendre_order: int | None,
    moment: int,
) -> dict[str, Any] | None:
    """Return ``{axes, shape, moment_index, values}`` for one scatter moment.

    Returns ``None`` if the mixture has no scatter dataset at all so the
    endpoint can tell the difference between "no scatter" (None) and
    "moment out of range" (dict with empty ``values``, surfaced as 404).
    """

    if "scatter_matrix" not in mix_group:
        return None
    dataset = mix_group["scatter_matrix"]
    axes_raw = dataset.attrs.get("axes")
    axes = (
        axes_raw.decode("utf-8")
        if isinstance(axes_raw, (bytes, bytearray))
        else axes_raw
        if isinstance(axes_raw, str)
        else None
    )
    arr = np.asarray(dataset[:], dtype=float)
    shape = list(arr.shape)
    if ngroups is None:
        # Best-effort fall back to whichever symmetric dimension matches.
        candidates = [s for s in shape if s > 0]
        ngroups = candidates[0] if candidates else 0
    matrix = scatter_moment_matrix(
        arr,
        axes,
        ngroups,
        legendre_order if legendre_order is not None else max(0, shape[0] - 1),
        moment=moment,
    )
    return {
        "axes": axes,
        "shape": shape,
        "moment_index": moment,
        "values": matrix.tolist() if matrix is not None else [],
    }


def _float_attr(attrs: Any, name: str) -> float | None:
    if name not in attrs:
        return None
    try:
        return float(attrs[name])
    except (TypeError, ValueError):
        return None


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
        raise http_exception(
            status_code=404, detail=f"path not found: {raw}"
        )
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


def _load_fixture(filename: str) -> dict[str, Any]:
    """Read a bundled fixture JSON from ``openmc2donjon.web.fixtures``."""

    text = resources.files("openmc2donjon.web.fixtures").joinpath(filename).read_text(
        encoding="utf-8"
    )
    return json.loads(text)


@lru_cache(maxsize=1)
def _mock_mixture_names() -> frozenset[str]:
    """Cached set of mixture names from the bundled handoff fixture.

    The fixture is read once per process; ``frozenset`` keeps the
    cached value immutable so callers can't accidentally mutate the
    shared object.
    """

    handoff = _load_fixture("inspect_handoff.json")
    return frozenset(mix["name"] for mix in handoff.get("mixtures", []))


@lru_cache(maxsize=1)
def _mock_non_fissionable_mixtures() -> frozenset[str]:
    """Cached set of non-fissionable mixture names from the handoff fixture."""

    handoff = _load_fixture("inspect_handoff.json")
    return frozenset(
        mix["name"]
        for mix in handoff.get("mixtures", [])
        if mix.get("fissionable") is False
    )


def _mock_mixture(mixture: str, moment: int, http_exception: Any) -> dict[str, Any]:
    """Serve the bundled per-mixture fixture for any mixture in the handoff.

    Mock mode previously ignored ``mixture`` / ``moment``. That made it
    impossible to develop the frontend selectors against the mock, and
    let regressions like "moment slider does nothing" slip through. The
    handoff fixture declares 9 mixtures and P1 scattering, so we accept
    those mixture names and moments 0 and 1, and synthesize a plausible
    P1 by scaling the bundled P0 values by 0.1 - enough non-zero
    structure for the frontend selectors and plot wiring to be exercised
    without us needing to ship a second hand-crafted fixture per moment.
    """

    if mixture not in _mock_mixture_names():
        raise http_exception(
            status_code=404, detail=f"mixture not found: {mixture}"
        )
    if moment >= 2:
        raise http_exception(
            status_code=404,
            detail=f"scatter moment {moment} not available for mixture {mixture}",
        )

    payload = _load_fixture("inspect_mixture.json")
    payload = dict(payload)
    payload["mixture"] = mixture
    if mixture in _mock_non_fissionable_mixtures():
        # Strip the fission family so the frontend exercises the
        # null-series guards in both the spectrum and the (M2-A)
        # heatmap. ``total`` / ``absorption`` / ``scatter`` stay
        # present - moderator / guide-tube mixtures absolutely still
        # have those.
        xs = dict(payload["cross_sections"])
        xs["fission"] = None
        xs["nu_fission"] = None
        xs["chi"] = None
        payload["cross_sections"] = xs
    if moment != 0:
        scatter = dict(payload["scatter"])
        scaled = [[float(v) * 0.1 for v in row] for row in scatter["values"]]
        scatter["values"] = scaled
        scatter["moment_index"] = moment
        payload["scatter"] = scatter
    return payload
