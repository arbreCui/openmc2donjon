#!/usr/bin/env python3
"""Expand five legacy IRENA component records to its declared 91 positions."""

from __future__ import annotations

import argparse
from pathlib import Path

from layout import declared_positions
from openmc2donjon.component_library import ComponentPosition, expand_component_library


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component_library", type=Path)
    parser.add_argument("--library-summary", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = expand_component_library(
        args.component_library,
        args.library_summary,
        [ComponentPosition(name, component) for name, component in declared_positions()],
        args.output,
        summary_json=args.summary_json,
        force=args.force,
    )
    print(
        f"mapped {payload['position_count']} IRENA positions from "
        f"{len(payload['component_names'])} accepted component types"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
