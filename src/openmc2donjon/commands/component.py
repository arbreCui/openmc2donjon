"""CLI commands for assembling accepted downstream component libraries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .base import USER_FACING_EXCEPTIONS, CommandSpec, exit_with_command_error, parser_from_args
from ..component_library import (
    AcceptedComponent,
    ComponentPosition,
    assemble_accepted_component_library,
    expand_component_library,
)


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "assemble-component-library",
            build_assemble_component_library_parser,
            assemble_component_library_handler,
            "assemble physically accepted native-SPH components for a downstream model",
        ),
        CommandSpec(
            "expand-component-library",
            build_expand_component_library_parser,
            expand_component_library_handler,
            "map accepted component types onto declared downstream positions",
        ),
    )


def build_assemble_component_library_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon assemble-component-library",
        description=(
            "Select named mixtures from production-ready native DRAGON SPH "
            "MACROLIBs and assemble one downstream component MACROLIB."
        ),
    )
    parser.add_argument(
        "--component",
        action="append",
        required=True,
        metavar="NAME=MACROLIB::SOURCE_MIXTURE",
        help="declared output name, accepted SPH MACROLIB, and source mixture name",
    )
    parser.add_argument(
        "--physics-summary",
        action="append",
        required=True,
        metavar="NAME=PHYSICS_SUMMARY.json",
        help="native-SPH physics summary for the matching component name",
    )
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def assemble_component_library_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        declarations = _component_declarations(args.component, args.physics_summary)
        payload = assemble_accepted_component_library(
            declarations,
            args.output,
            summary_json=args.summary_json,
            force=args.force,
        )
        print_component_library_result(payload)
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "assemble-component-library", exc)
    return 0


def build_expand_component_library_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon expand-component-library",
        description=(
            "Duplicate accepted component records onto an explicit downstream "
            "position map without averaging, fitting, or rerunning SPH."
        ),
    )
    parser.add_argument("component_library", type=Path)
    parser.add_argument("--library-summary", type=Path, required=True)
    parser.add_argument(
        "--position",
        action="append",
        required=True,
        metavar="POSITION=COMPONENT",
        help="position name and accepted component type, in consumer order",
    )
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def expand_component_library_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        positions = [
            ComponentPosition(name, component)
            for name, component in (
                _parse_named_value(value, "position") for value in args.position
            )
        ]
        payload = expand_component_library(
            args.component_library,
            args.library_summary,
            positions,
            args.output,
            summary_json=args.summary_json,
            force=args.force,
        )
        print_component_library_result(payload)
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "expand-component-library", exc)
    return 0


def _component_declarations(
    components: list[str], summaries: list[str]
) -> list[AcceptedComponent]:
    summary_by_name = dict(_parse_named_path(value, "physics summary") for value in summaries)
    declarations: list[AcceptedComponent] = []
    seen: set[str] = set()
    for value in components:
        if "=" not in value or "::" not in value.split("=", 1)[1]:
            raise ValueError(
                "component must use NAME=MACROLIB::SOURCE_MIXTURE syntax"
            )
        name, selection = value.split("=", 1)
        macrolib, source_mixture = selection.rsplit("::", 1)
        name = name.strip()
        if not name or not macrolib.strip() or not source_mixture.strip():
            raise ValueError(
                "component must use NAME=MACROLIB::SOURCE_MIXTURE syntax"
            )
        if name in seen:
            raise ValueError(f"duplicate component declaration: {name}")
        if name not in summary_by_name:
            raise ValueError(f"component {name} has no matching --physics-summary")
        seen.add(name)
        declarations.append(
            AcceptedComponent(
                name=name,
                macrolib=Path(macrolib.strip()),
                physics_summary=summary_by_name[name],
                source_mixture=source_mixture.strip(),
            )
        )
    extras = sorted(set(summary_by_name) - seen)
    if extras:
        raise ValueError(f"physics summaries have no matching component: {', '.join(extras)}")
    return declarations


def _parse_named_path(value: str, label: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"{label} must use NAME=PATH syntax")
    name, path = (part.strip() for part in value.split("=", 1))
    if not name or not path:
        raise ValueError(f"{label} must use NAME=PATH syntax")
    return name, Path(path)


def _parse_named_value(value: str, label: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"{label} must use NAME=VALUE syntax")
    name, target = (part.strip() for part in value.split("=", 1))
    if not name or not target:
        raise ValueError(f"{label} must use NAME=VALUE syntax")
    return name, target


def print_component_library_result(payload: dict[str, object]) -> None:
    """Render the assembled component-library receipt as CLI JSON."""

    print(json.dumps(payload, indent=2, sort_keys=True))
