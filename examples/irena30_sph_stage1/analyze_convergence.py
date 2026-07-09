#!/usr/bin/env python3
"""Summarize an SPH iteration trajectory from a handoff directory.

Reads the per-iteration ``openmc_sph_iterNN.csv`` tables and summaries and
prints, per iteration: the max |update - 1| over active (non-frozen) bins
from the summary JSON, the SPH range, and the SPH values of selected
groups. Works for single- and multi-mixture tables (Stage 1 and Stage 2):
with several mixtures the watch columns show, per group, the value with
the largest |sph - 1| across mixtures unless ``--mixture`` selects one.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


def read_table(path: Path, mixture: str | None) -> dict[int, float]:
    """Return group -> sph; across mixtures keep the value farthest from 1."""
    values: dict[int, float] = {}
    with path.open() as handle:
        for row in csv.DictReader(handle):
            if mixture is not None and row["mixture"] != mixture:
                continue
            group = int(row["group"])
            sph = float(row["sph"])
            if group not in values or abs(sph - 1.0) > abs(values[group] - 1.0):
                values[group] = sph
    if not values:
        raise SystemExit(f"{path}: no rows matched mixture={mixture!r}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-dir", type=Path, required=True)
    parser.add_argument("--watch-groups", default="1,5,10,15,20,25,28,29,30",
                        help="comma-separated DRAGON-order groups to print")
    parser.add_argument("--mixture", default=None,
                        help="restrict to one mixture name (default: worst across mixtures)")
    args = parser.parse_args()

    watch = [int(g) for g in args.watch_groups.split(",")]
    tables = sorted(args.handoff_dir.glob("openmc_sph_iter*.csv"))
    if not tables:
        raise SystemExit(f"no openmc_sph_iter*.csv found in {args.handoff_dir}")

    label = args.mixture or "worst-of-mixtures"
    print(f"columns: {label}")
    print(f"{'iter':>4} {'max|upd-1|':>11} {'sph_min':>8} {'sph_max':>8} "
          + " ".join(f"g{g:>02d}" for g in watch))
    final: dict[int, float] | None = None
    for table_path in tables:
        match = re.search(r"iter(\d+)", table_path.name)
        iteration = int(match.group(1)) if match else -1
        sph = read_table(table_path, args.mixture)
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
        final = sph

    if final is not None:
        active = {g: v for g, v in final.items() if abs(v - 1.0) > 1e-9}
        print(f"\nfinal iteration: {len(active)}/{len(final)} groups carry a "
              "non-identity SPH factor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
