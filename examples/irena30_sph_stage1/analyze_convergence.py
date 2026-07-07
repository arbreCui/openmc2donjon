#!/usr/bin/env python3
"""Summarize the Stage 1 SPH iteration trajectory from a handoff directory.

Reads the per-iteration ``openmc_sph_iterNN.csv`` tables and summaries and
prints, per iteration: the max |update - 1| over active (non-frozen) bins
from the summary JSON, the SPH range, and the SPH values of selected groups.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


def read_table(path: Path) -> dict[int, float]:
    values: dict[int, float] = {}
    with path.open() as handle:
        for row in csv.DictReader(handle):
            values[int(row["group"])] = float(row["sph"])
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-dir", type=Path, required=True)
    parser.add_argument("--watch-groups", default="1,5,10,15,20,25,28,29,30",
                        help="comma-separated DRAGON-order groups to print")
    args = parser.parse_args()

    watch = [int(g) for g in args.watch_groups.split(",")]
    tables = sorted(args.handoff_dir.glob("openmc_sph_iter*.csv"))
    if not tables:
        raise SystemExit(f"no openmc_sph_iter*.csv found in {args.handoff_dir}")

    print(f"{'iter':>4} {'max|upd-1|':>11} {'sph_min':>8} {'sph_max':>8} "
          + " ".join(f"g{g:>02d}" for g in watch))
    previous: dict[int, float] | None = None
    for table_path in tables:
        match = re.search(r"iter(\d+)", table_path.name)
        iteration = int(match.group(1)) if match else -1
        sph = read_table(table_path)
        summary_path = table_path.with_name(
            table_path.name.replace("openmc_sph_iter", "openmc_sph_summary_iter")
        ).with_suffix(".json")
        max_resid = math.nan
        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            lo = float(summary.get("raw_update_minimum", math.nan))
            hi = float(summary.get("raw_update_maximum", math.nan))
            max_resid = max(abs(lo - 1.0), abs(hi - 1.0))
        update_str = f"{max_resid:11.4f}" if not math.isnan(max_resid) else " " * 11
        row = " ".join(f"{sph.get(g, math.nan):.3f}" for g in watch)
        print(f"{iteration:>4} {update_str} {min(sph.values()):8.4f} "
              f"{max(sph.values()):8.4f} {row}")
        previous = sph

    if previous is not None:
        active = {g: v for g, v in previous.items() if abs(v - 1.0) > 1e-9}
        print(f"\nfinal iteration: {len(active)}/{len(previous)} groups carry a "
              "non-identity SPH factor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
