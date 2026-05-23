"""FastAPI application factory for the openmc2donjon web UI.

M0 scope: a single ``/api/health`` endpoint that confirms the backend
is reachable and reports whether mock mode is on. Real CLI command
endpoints are added in later milestones.

The ``create_app`` factory keeps the mock flag out of module globals so
the CLI ``serve`` command can pass it in explicitly.
"""

from __future__ import annotations

from typing import Any

from .. import __version__
from .._logging import get_logger


logger = get_logger("web.server")


def create_app(*, mock_mode: bool = False, cors_origins: tuple[str, ...] | None = None) -> Any:
    """Build a configured FastAPI application instance.

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

    app = FastAPI(
        title="openmc2donjon",
        description="Web interface for the OpenMC -> DRAGON/DONJON handoff pipeline.",
        version=__version__,
    )

    allow_origins = list(
        cors_origins
        if cors_origins is not None
        else ("http://localhost:3000", "http://127.0.0.1:3000")
    )
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
        }

    if mock_mode:
        logger.info("openmc2donjon web server starting in MOCK mode")
    else:
        logger.info("openmc2donjon web server starting in LIVE mode")

    return app
