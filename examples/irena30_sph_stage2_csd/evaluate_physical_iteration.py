"""Validate one strict SPH iteration summary and report convergence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


NOT_CONVERGED = 10


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--max-update-residual", type=float, required=True)
    parser.add_argument("--require-tie-mixtures", default=None)
    args = parser.parse_args(argv)

    payload = json.loads(args.summary.read_text(encoding="utf-8"))
    forbidden = {
        "clip_min": payload.get("clip_min"),
        "clip_max": payload.get("clip_max"),
        "flux_floor_rel": payload.get("flux_floor_rel"),
        "freeze_groups": payload.get("freeze_groups"),
    }
    active = {name: value for name, value in forbidden.items() if value is not None}
    if active:
        raise SystemExit(f"forbidden numerical exemptions are active: {active}")
    expected = {
        "sph_target": "rate",
        "flux_normalization": "power",
        "zero_flux_policy": "reject",
    }
    mismatches = {
        name: payload.get(name)
        for name, value in expected.items()
        if payload.get(name) != value
    }
    if mismatches:
        raise SystemExit(f"strict SPH provenance mismatch: {mismatches}")
    if args.require_tie_mixtures is not None:
        required_group = [
            item.strip()
            for item in args.require_tie_mixtures.split(",")
            if item.strip()
        ]
        if payload.get("tie_mixture_groups") != [required_group]:
            raise SystemExit(
                "strict SPH symmetry class mismatch: "
                f"{payload.get('tie_mixture_groups')!r} != {[required_group]!r}"
            )
    for counter in (
        "identity_bin_count",
        "floored_bin_count",
        "frozen_group_bin_count",
        "clipped_count",
    ):
        if int(payload.get(counter, -1)) != 0:
            raise SystemExit(f"strict SPH requires {counter}=0")

    raw_min = float(payload["raw_update_minimum"])
    raw_max = float(payload["raw_update_maximum"])
    residual = max(abs(raw_min - 1.0), abs(raw_max - 1.0))
    print(
        f"max rate fixed-point residual={residual:.8g}; "
        f"limit={args.max_update_residual:.8g}"
    )
    return 0 if residual <= args.max_update_residual else NOT_CONVERGED


if __name__ == "__main__":
    raise SystemExit(main())
