"""Shared logging setup for openmc2donjon command line entry points.

Output contract:
- ``print()`` is for requested results: reports, paths, summaries, and text
  that users may redirect or parse.
- ``logging`` is for diagnostics: progress, warnings, fallbacks, and debug
  detail. CLI logging is routed to stderr so stdout remains a result stream.
"""

from __future__ import annotations

import argparse
import logging
import sys


LOGGER_NAME = "openmc2donjon"
LOG_LEVEL_NAMES = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
_CLI_HANDLER_ATTR = "_openmc2donjon_cli_handler"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package-scoped logger."""

    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def add_cli_logging_arguments(
    parser: argparse.ArgumentParser,
    *,
    defaults: bool = True,
) -> None:
    """Add standard CLI logging flags to an argparse parser."""

    verbose_default: int | str = 0 if defaults else argparse.SUPPRESS
    quiet_default: bool | str = False if defaults else argparse.SUPPRESS
    log_level_default: None | str = None if defaults else argparse.SUPPRESS
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=verbose_default,
        help="increase diagnostic logging verbosity; repeat for DEBUG",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=quiet_default,
        help="suppress warning diagnostics; only errors are logged",
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVEL_NAMES,
        type=str.upper,
        default=log_level_default,
        help="set diagnostic logging level explicitly",
    )


def configure_cli_logging(
    verbose: int = 0,
    quiet: bool = False,
    log_level: str | None = None,
) -> logging.Logger:
    """Configure package CLI diagnostics and return the package logger."""

    logger = get_logger()
    logger.setLevel(_resolve_log_level(verbose=verbose, quiet=quiet, log_level=log_level))
    logger.propagate = False

    for handler in tuple(logger.handlers):
        if getattr(handler, _CLI_HANDLER_ATTR, False):
            logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _CLI_HANDLER_ATTR, True)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    handler.setLevel(logging.NOTSET)
    logger.addHandler(handler)
    return logger


def configure_cli_logging_from_args(args: argparse.Namespace) -> logging.Logger:
    """Configure CLI diagnostics from standard logging argparse attributes."""

    return configure_cli_logging(
        verbose=int(getattr(args, "verbose", 0) or 0),
        quiet=bool(getattr(args, "quiet", False)),
        log_level=getattr(args, "log_level", None),
    )


def _resolve_log_level(verbose: int, quiet: bool, log_level: str | None) -> int:
    if log_level is not None:
        normalized = log_level.upper()
        if normalized not in LOG_LEVEL_NAMES:
            raise ValueError(f"unsupported log level: {log_level}")
        return int(logging.getLevelName(normalized))
    if quiet:
        return logging.ERROR
    if verbose >= 2:
        return logging.DEBUG
    if verbose == 1:
        return logging.INFO
    return logging.WARNING
