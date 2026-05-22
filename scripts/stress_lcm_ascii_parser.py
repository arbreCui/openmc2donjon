#!/usr/bin/env python3
"""Stress-parse a large GANLIB/LCM ASCII file.

This is an opt-in local gate for real DRAGON/DONJON ASCII samples that are too
large or too site-specific for the default unit-test suite.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Sequence

from openmc2donjon import lcm_ascii


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    path = args.input
    if not path.is_file():
        parser.error(f"input file does not exist: {path}")

    start = perf_counter()
    blocks = lcm_ascii.read_lcm_ascii(path)
    seconds = perf_counter() - start

    name_counts = Counter(block.name for block in blocks if block.name)
    type_counts = Counter(block.type_code for block in blocks)
    signatures = Counter(
        block.data.strip()
        for block in blocks
        if block.name == "SIGNATURE" and isinstance(block.data, str)
    )
    summary = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "seconds": seconds,
        "block_count": len(blocks),
        "type_counts": {str(key): value for key, value in sorted(type_counts.items())},
        "name_count": len(name_counts),
        "trailing_count": sum(1 for block in blocks if block.trailing),
        "signature_counts": dict(sorted(signatures.items())),
    }

    failures = _check_expectations(
        args,
        block_count=len(blocks),
        seconds=seconds,
        name_counts=name_counts,
        signatures=signatures,
    )

    _print_summary(summary, failures)
    if args.summary_json is not None:
        args.summary_json.write_text(json.dumps(summary, indent=2) + "\n")

    return 1 if failures else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="LCM ASCII file to parse")
    parser.add_argument(
        "--min-blocks",
        type=int,
        default=1,
        help="fail if fewer blocks are parsed",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="fail if parsing takes longer than this wall time",
    )
    parser.add_argument(
        "--require-signature",
        action="append",
        default=[],
        help="require a SIGNATURE payload such as L_MULTICOMPO or L_LIBRARY",
    )
    parser.add_argument(
        "--require-block",
        action="append",
        default=[],
        help="require at least one named block, for example MIXTURES or MACROLIB",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="optional path for a JSON parse summary",
    )
    return parser


def _check_expectations(
    args: argparse.Namespace,
    *,
    block_count: int,
    seconds: float,
    name_counts: Counter[str],
    signatures: Counter[str],
) -> list[str]:
    failures: list[str] = []
    if block_count < args.min_blocks:
        failures.append(f"block_count {block_count} < --min-blocks {args.min_blocks}")
    if args.max_seconds is not None and seconds > args.max_seconds:
        failures.append(f"parse time {seconds:.3f}s > --max-seconds {args.max_seconds}")
    for signature in args.require_signature:
        if signatures[signature] == 0:
            failures.append(f"missing required SIGNATURE {signature!r}")
    for name in args.require_block:
        if name_counts[name] == 0:
            failures.append(f"missing required block {name!r}")
    return failures


def _print_summary(summary: dict[str, object], failures: Sequence[str]) -> None:
    print("LCM ASCII parser stress")
    print(f"  input: {summary['path']}")
    print(f"  size_bytes: {summary['size_bytes']}")
    print(f"  blocks: {summary['block_count']}")
    print(f"  seconds: {summary['seconds']:.3f}")
    print(f"  type_counts: {_format_counts(summary['type_counts'])}")
    print(f"  signatures: {_format_counts(summary['signature_counts'])}")
    print(f"  named_blocks: {summary['name_count']}")
    print(f"  trailing_tags: {summary['trailing_count']}")
    if failures:
        print("  decision: FAIL")
        for failure in failures:
            print(f"    {failure}")
    else:
        print("  decision: PASS")


def _format_counts(counts: object) -> str:
    if not isinstance(counts, dict):
        return str(counts)
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in counts.items())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
