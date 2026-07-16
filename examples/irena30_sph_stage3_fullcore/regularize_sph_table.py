#!/usr/bin/env python3
"""Tie IRENA-30 SPH factors over exact 120-degree symmetry orbits.

The fine and assembly-homogenized full-core models are invariant under a
120-degree rotation.
For ring ``r > 0``, positions ``p``, ``p + 2r`` and ``p + 4r`` are therefore
the same physical environment.  This helper replaces their independently
tallied factors by a geometric mean and broadcasts that value back to all
three positions.  Geometric averaging is the natural choice for the
multiplicative SPH update and prevents position-wise Monte Carlo noise from
being accumulated as a real correction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re


SCHEMA = "openmc2donjon.irena30-sph-symmetry-regularization.v1"
MIXTURE_PATTERN = re.compile(r"R(?P<ring>\d+)P(?P<position>\d+)_(?P<label>[A-Za-z0-9]+)")


def symmetry_orbit(mixture: str) -> str:
    """Return the 120-degree orbit key for a Stage 3 mixture name."""

    match = MIXTURE_PATTERN.fullmatch(mixture)
    if match is None:
        raise ValueError(f"invalid IRENA full-core mixture name: {mixture!r}")
    ring = int(match.group("ring"))
    position = int(match.group("position"))
    label = match.group("label")
    if ring == 0:
        if position != 0:
            raise ValueError(f"ring 0 mixture must use position 0: {mixture!r}")
        return f"R0_CENTER_{label}"
    if position >= 6 * ring:
        raise ValueError(
            f"position {position} is outside ring {ring} (expected 0..{6 * ring - 1})"
        )
    return f"R{ring}O{position % (2 * ring):02d}_{label}"


def regularize_sph_table(
    input_table: Path,
    output_table: Path,
    *,
    force: bool = False,
    summary_json: Path | None = None,
) -> dict[str, object]:
    """Geometrically average a long-form SPH table over symmetry orbits."""

    input_table = Path(input_table)
    output_table = Path(output_table)
    if not input_table.is_file():
        raise FileNotFoundError(f"SPH table does not exist: {input_table}")
    if output_table.exists() and not force:
        raise FileExistsError(f"output already exists; use --force: {output_table}")
    rows: list[tuple[str, int, float]] = []
    seen: set[tuple[str, int]] = set()
    mixture_order: list[str] = []
    groups_by_mixture: dict[str, set[int]] = {}
    orbit_values: dict[tuple[str, int], list[float]] = {}
    orbit_members: dict[str, set[str]] = {}
    with input_table.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not {"mixture", "group", "sph"}.issubset(
            reader.fieldnames
        ):
            raise ValueError("SPH table must contain mixture,group,sph columns")
        for row_number, row in enumerate(reader, start=2):
            mixture = str(row.get("mixture", "")).strip()
            try:
                group = int(str(row.get("group", "")).strip())
                value = float(str(row.get("sph", "")).strip())
            except ValueError as exc:
                raise ValueError(f"invalid SPH row {row_number}") from exc
            if group < 1:
                raise ValueError(f"row {row_number}: group must be >= 1")
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"row {row_number}: SPH must be positive and finite")
            key = (mixture, group)
            if key in seen:
                raise ValueError(f"duplicate SPH row for {mixture} group {group}")
            seen.add(key)
            if mixture not in groups_by_mixture:
                mixture_order.append(mixture)
                groups_by_mixture[mixture] = set()
            groups_by_mixture[mixture].add(group)
            orbit = symmetry_orbit(mixture)
            orbit_values.setdefault((orbit, group), []).append(value)
            orbit_members.setdefault(orbit, set()).add(mixture)
            rows.append((mixture, group, value))

    if not rows:
        raise ValueError("SPH table contains no data rows")
    expected_groups = set(range(1, max(group for _, group, _ in rows) + 1))
    for mixture in mixture_order:
        if groups_by_mixture[mixture] != expected_groups:
            raise ValueError(f"{mixture}: SPH groups are incomplete")
    for orbit, members in orbit_members.items():
        expected_members = 1 if orbit.startswith("R0_") else 3
        if len(members) != expected_members:
            raise ValueError(
                f"symmetry orbit {orbit} has {len(members)} member(s), "
                f"expected {expected_members}"
            )

    orbit_means = {
        key: math.exp(sum(math.log(value) for value in values) / len(values))
        for key, values in orbit_values.items()
    }
    regularized: list[tuple[str, int, float]] = []
    max_spread = 0.0
    for mixture, group, _value in rows:
        orbit = symmetry_orbit(mixture)
        values = orbit_values[(orbit, group)]
        max_spread = max(max_spread, max(values) / min(values) - 1.0)
        regularized.append((mixture, group, orbit_means[(orbit, group)]))

    output_table.parent.mkdir(parents=True, exist_ok=True)
    with output_table.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("mixture", "group", "sph"))
        for mixture, group, value in regularized:
            writer.writerow((mixture, group, f"{value:.12g}"))

    values = [value for _, _, value in regularized]
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "input_table": str(input_table),
        "output_table": str(output_table),
        "mixture_count": len(mixture_order),
        "energy_groups": len(expected_groups),
        "orbit_count": len(orbit_members),
        "orbit_member_counts": {
            orbit: len(members) for orbit, members in sorted(orbit_members.items())
        },
        "method": "120-degree-orbit-geometric-mean",
        "input_max_within_orbit_relative_spread": max_spread,
        "sph_min": min(values),
        "sph_max": max(values),
        "decision": "openmc2donjon_irena30_sph_symmetry_regularization_passed",
    }
    if summary_json is not None:
        summary_json = Path(summary_json)
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_table", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        payload = regularize_sph_table(
            args.input_table,
            args.output,
            force=args.force,
            summary_json=args.summary_json,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        parser.error(str(exc))
    print("IRENA-30 SPH symmetry regularization")
    print(f"  input: {payload['input_table']}")
    print(f"  output: {payload['output_table']}")
    print(
        f"  mixtures={payload['mixture_count']} groups={payload['energy_groups']} "
        f"orbits={payload['orbit_count']}"
    )
    print(
        f"  SPH range: {payload['sph_min']:g}..{payload['sph_max']:g}; "
        "max input orbit spread: "
        f"{payload['input_max_within_orbit_relative_spread']:.1%}"
    )
    print("  openmc2donjon_irena30_sph_symmetry_regularization_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
