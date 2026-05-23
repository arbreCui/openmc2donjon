"""CLI subcommand: ``openmc2donjon serve`` — start the web UI backend."""

from __future__ import annotations

import argparse

from .._logging import get_logger
from .base import CommandSpec, parser_from_args


logger = get_logger("commands.web")


def build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon serve",
        description=(
            "Start the openmc2donjon web UI backend (FastAPI on uvicorn). "
            "Run `npm run dev` in the web/ directory in another shell to "
            "bring up the Next.js dev server."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address (default: 127.0.0.1, localhost only)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="bind port (default: 8000)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help=(
            "serve fixture data instead of calling real openmc2donjon "
            "APIs (development mode for the frontend)"
        ),
    )
    parser.add_argument(
        "--cors-origin",
        action="append",
        dest="cors_origins",
        metavar="ORIGIN",
        default=None,
        help=(
            "additional CORS origin to allow (repeatable); defaults to "
            "http://localhost:3000 and http://127.0.0.1:3000"
        ),
    )
    return parser


def serve_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        import uvicorn
    except ImportError:
        parser.exit(
            1,
            "openmc2donjon serve: web extras are not installed. "
            'Install with: pip install -e ".[web]"\n',
        )
    from ..web.server import create_app

    extra_origins = tuple(args.cors_origins) if args.cors_origins else ()
    app = create_app(mock_mode=bool(args.mock), extra_origins=extra_origins)
    mode = "mock" if args.mock else "live"
    logger.info(
        "Serving openmc2donjon web backend on http://%s:%d (%s mode)",
        args.host,
        args.port,
        mode,
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=_uvicorn_log_level(args),
    )
    return 0


def _uvicorn_log_level(args: argparse.Namespace) -> str:
    """Map the CLI logging flags onto uvicorn's ``log_level`` knob.

    ``--log-level`` wins, then ``--quiet``, then ``-vv`` -> debug. The
    default stays at ``info`` so uvicorn request logs remain visible
    during interactive use.
    """

    explicit = getattr(args, "log_level", None)
    if explicit:
        return str(explicit).lower()
    if getattr(args, "quiet", False):
        return "error"
    verbose = int(getattr(args, "verbose", 0) or 0)
    if verbose >= 2:
        return "debug"
    return "info"




def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "serve",
            build_serve_parser,
            serve_handler,
            "start the openmc2donjon web UI backend",
        ),
    )
