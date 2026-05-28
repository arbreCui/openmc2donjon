"""FastAPI application factory for the openmc2donjon web UI.

Core endpoints:

- ``GET /api/health`` - backend liveness + mock flag + package version.
- ``GET /api/commands`` - web/CLI command catalog used by the command
  workspace page.
- ``GET /api/inspect?path=...`` and ``GET /api/inspect/mixture`` -
  MGXS HDF5 inspection endpoints registered by ``web.inspect``.
- ``GET /api/openmc-sph-summary?path=...`` - read-only OpenMC CE/MG
  physics summary produced by the current OpenMC-side SPH route.
- ``GET /api/text-preview?path=...`` - bounded UTF-8/ASCII preview for
  generated text artifacts such as ``.mcompo.txt`` and ``.macrolib.txt``.
- ``GET /api/file-status?path=...`` and ``GET /api/files`` - file
  browser endpoints registered by ``web.files``.
- ``GET /api/bundle/inspect?manifest=...`` - read-only bundle manifest
  validation summary used by converter delivery cards.

The ``create_app`` factory keeps the mock flag out of module globals so
the CLI ``serve`` command can pass it in explicitly. Mock mode returns
bundled fixture JSONs so the frontend can be exercised without a real
HDF5 on disk.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import __version__
from .._logging import get_logger
from ..pygan_backend import probe_pygan
from .bundle import register_bundle_routes
from .commands import register_command_routes
from .convert import register_convert_routes
from .files import (
    FILES_ENTRY_LIMIT as FILES_ENTRY_LIMIT,
    FILES_SCHEMA as FILES_SCHEMA,
    FILE_STATUS_SCHEMA as FILE_STATUS_SCHEMA,
    register_file_routes,
)
from .filesystem import FilesystemScope
from .inspect import (
    INSPECT_SCHEMA as INSPECT_SCHEMA,
    MIXTURE_SCHEMA as MIXTURE_SCHEMA,
    _PEEK_MAX_ROOT_ATTRS as _PEEK_MAX_ROOT_ATTRS,
    register_inspect_routes,
)
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
        from fastapi import FastAPI
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
    register_inspect_routes(
        app,
        mock_mode=mock_mode,
        filesystem_scope=filesystem_scope,
    )
    register_file_routes(
        app,
        mock_mode=mock_mode,
        filesystem_scope=filesystem_scope,
    )

    register_text_preview_routes(
        app,
        mock_mode=mock_mode,
        filesystem_scope=filesystem_scope,
    )

    register_convert_routes(app, mock_mode=mock_mode, filesystem_scope=filesystem_scope)
    register_bundle_routes(app, mock_mode=mock_mode, filesystem_scope=filesystem_scope)

    if mock_mode:
        logger.info("openmc2donjon web server starting in MOCK mode")
    else:
        logger.info("openmc2donjon web server starting in LIVE mode")

    return app


@lru_cache(maxsize=1)
def _cached_pygan_status() -> dict[str, object]:
    return probe_pygan().as_dict()
