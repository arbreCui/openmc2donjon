"""Shared pieces for argparse-backed CLI subcommands."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    parser_builder: Callable[[], argparse.ArgumentParser]
    handler: Callable[[argparse.Namespace], int]
    help: str
    aliases: tuple[str, ...] = ()


def parser_from_args(args: argparse.Namespace) -> argparse.ArgumentParser:
    return getattr(args, "_parser")

