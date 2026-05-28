"""CLI subcommand: ``openmc2donjon serve`` — start the web UI backend."""

from __future__ import annotations

import argparse
from ipaddress import ip_address
from pathlib import Path

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
    parser.add_argument(
        "--workspace-root",
        default=None,
        metavar="PATH",
        help=(
            "constrain live-mode file reads/writes to PATH. Required when "
            "binding live mode to a non-loopback host unless --unsafe-remote "
            "is also set"
        ),
    )
    parser.add_argument(
        "--unsafe-remote",
        action="store_true",
        help=(
            "allow unrestricted live-mode filesystem access on non-loopback "
            "hosts. Intended only for trusted local networks"
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

    workspace_root = _resolve_workspace_root(getattr(args, "workspace_root", None), parser)
    if _requires_workspace_guard(
        host=str(args.host),
        mock=bool(args.mock),
        workspace_root=workspace_root,
        unsafe_remote=bool(args.unsafe_remote),
    ):
        parser.exit(
            2,
            "openmc2donjon serve: refusing to expose unrestricted live-mode "
            "filesystem access on a non-loopback host. Use --workspace-root "
            "PATH to constrain access, or --unsafe-remote if this is an "
            "intentional trusted-network server.\n",
        )

    extra_origins = tuple(args.cors_origins) if args.cors_origins else ()
    app = create_app(
        mock_mode=bool(args.mock),
        extra_origins=extra_origins,
        workspace_root=workspace_root,
    )
    mode = "mock" if args.mock else "live"
    if not args.mock and workspace_root is None and bool(args.unsafe_remote):
        logger.warning(
            "Live web backend has unrestricted local filesystem access on a "
            "non-loopback host because --unsafe-remote was set"
        )
    elif not args.mock and workspace_root is None:
        logger.info(
            "Live web backend has unrestricted local filesystem access on a "
            "loopback-only host"
        )
    elif workspace_root is not None:
        logger.info("Web filesystem access constrained to %s", workspace_root)
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


def _resolve_workspace_root(raw: str | None, parser: argparse.ArgumentParser) -> Path | None:
    if raw is None or not str(raw).strip():
        return None
    root = Path(str(raw)).expanduser().resolve()
    if not root.exists():
        parser.exit(2, f"openmc2donjon serve: workspace root not found: {root}\n")
    if not root.is_dir():
        parser.exit(
            2,
            f"openmc2donjon serve: workspace root is not a directory: {root}\n",
        )
    return root


def _requires_workspace_guard(
    *,
    host: str,
    mock: bool,
    workspace_root: Path | None,
    unsafe_remote: bool,
) -> bool:
    return (
        not mock
        and workspace_root is None
        and not unsafe_remote
        and not _is_loopback_host(host)
    )


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "serve",
            build_serve_parser,
            serve_handler,
            "start the openmc2donjon web UI backend",
        ),
    )
