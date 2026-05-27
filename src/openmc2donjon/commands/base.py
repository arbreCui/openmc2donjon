"""Shared pieces for argparse-backed CLI subcommands."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass


USER_FACING_EXCEPTIONS = (OSError, ValueError, KeyError, RuntimeError)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    parser_builder: Callable[[], argparse.ArgumentParser]
    handler: Callable[[argparse.Namespace], int]
    help: str
    aliases: tuple[str, ...] = ()
    hidden: bool = False


def parser_from_args(args: argparse.Namespace) -> argparse.ArgumentParser:
    return args._parser


def exit_with_command_error(
    parser: argparse.ArgumentParser,
    command: str,
    exc: BaseException,
) -> None:
    parser.exit(1, f"openmc2donjon {command}: error: {exc}\n")
