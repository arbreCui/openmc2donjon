"""Shared logging setup for openmc2donjon command line entry points.

Output contract
---------------

The package separates two output streams by design:

- ``print()`` is for requested *results*: reports, paths, summaries, and
  any text the user invoked the command to receive. Stdout stays a clean
  result stream that can be redirected or parsed.
- ``logging`` is for *diagnostics*: progress, warnings, fallbacks, and
  debug detail. CLI logging is routed to stderr and shaped by the
  ``-v / -vv / -q / --log-level`` flags.

What stays a ``print()``
~~~~~~~~~~~~~~~~~~~~~~~~

Most of the codebase routes user-visible output through one of these
patterns, and every ``print()`` inside them is a *result*:

- Functions named ``print_report`` / ``_print_*`` / ``render_*`` /
  ``format_*`` (the convention for "render a frozen Report dataclass to
  stdout") and the dedicated report modules
  (``mgxs_input_report``, ``recipe_dry_run_report``).
- CLI handlers that announce a produced artifact, e.g.
  ``print(f"wrote {format}: {output_path}")``,
  ``print(f"exported {n} domains ...")``,
  ``print(f"injected ADF into HDF5: {hdf5_path}")``.
  These are confirmations the user asked for by running the command;
  silencing them with logger filters would break shell pipelines that
  read them.

What goes through ``logging``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Anything that is *not* a requested result and that a quiet user might
reasonably want to suppress:

- ``logger.error(...)`` for failures the CLI catches and surfaces (e.g.
  ``StatepointLoadError`` from a recipe load). These previously used
  ``print(..., file=sys.stderr)``.
- ``logger.warning(...)`` for non-fatal physics/contract anomalies that
  do not stop the run.
- ``logger.info(...)`` for progress milestones useful under ``-v``
  (e.g. "starting iteration k of N", "fallback X engaged").
- ``logger.debug(...)`` for internals, subprocess invocation lines,
  HDF5 path probing, etc., visible only under ``-vv``.

Use ``get_logger("<module-suffix>")`` at module scope to obtain a
package-scoped logger:

    logger = get_logger("from_openmc_cli")

The audit at ``tests/test_print_audit.py`` enforces this contract by
listing every ``print()`` call outside a render helper - if you add a
new one, either move it inside a ``print_*``/``render_*``/``format_*``
helper, replace it with a ``logger`` call, or add it to the explicit
whitelist there if it is a deliberate "I wrote X" result confirmation.
"""

from __future__ import annotations

import argparse
import logging
import sys


LOGGER_NAME = "openmc2donjon"
LOG_LEVEL_NAMES = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
_CLI_HANDLER_ATTR = "_openmc2donjon_cli_handler"

# Flag names that consume the following argv token (e.g. ``--log-level INFO``).
# Used by command dispatchers that scan argv before invoking argparse.
CLI_LOGGING_VALUE_FLAGS: tuple[str, ...] = ("--log-level",)


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


def is_cli_logging_flag(token: str) -> bool:
    """Return True if ``token`` is one of the CLI logging argparse flags.

    Command dispatchers use this to skip logging flags while scanning argv
    for a subcommand name. Keeping the recognition rules here means new
    logging flags do not need to be mirrored into the dispatcher.
    """

    if token in ("--verbose", "--quiet"):
        return True
    if token in CLI_LOGGING_VALUE_FLAGS:
        return True
    if any(token.startswith(f"{flag}=") for flag in CLI_LOGGING_VALUE_FLAGS):
        return True
    # argparse accepts short-flag clusters such as ``-vq``, ``-qv``, or
    # ``-vvq`` when each character is its own argument. Treat any cluster
    # built from ``v`` and ``q`` as a logging flag for dispatcher purposes.
    if (
        token.startswith("-")
        and not token.startswith("--")
        and len(token) > 1
        and set(token[1:]) <= {"v", "q"}
    ):
        return True
    return False


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
