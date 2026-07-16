"""Gate the reaction-rate coverage of the selected Stage-2 MG energy domain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import openmc

from irena_csd_colorset_model import (
    ENERGY_COVERAGE_SCORES,
    ENERGY_COVERAGE_TALLY_NAME,
    ENERGY_MESH_ID,
    FULL_ENERGY_MAX_EV,
    FULL_ENERGY_MIN_EV,
    N_ASSEMBLIES,
    energy_bounds_ev,
    energy_coverage_segments,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("statepoint", type=Path)
    parser.add_argument("--max-outside-fraction", type=float, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    args = parser.parse_args(argv)

    with openmc.StatePoint(str(args.statepoint)) as statepoint:
        tally = statepoint.get_tally(name=ENERGY_COVERAGE_TALLY_NAME)
        segment_labels, _coverage_bounds = energy_coverage_segments()
        values = np.asarray(tally.mean, dtype=float).reshape(
            N_ASSEMBLIES, len(segment_labels), len(ENERGY_COVERAGE_SCORES)
        )

    by_energy = np.sum(values, axis=0)
    by_segment = {
        label: by_energy[index] for index, label in enumerate(segment_labels)
    }
    scores: dict[str, dict[str, float | bool]] = {}
    passed = True
    for score_index, score in enumerate(ENERGY_COVERAGE_SCORES):
        low = float(by_segment.get("low_tail", np.zeros(len(ENERGY_COVERAGE_SCORES)))[score_index])
        retained = float(by_segment["retained"][score_index])
        high = float(by_segment.get("high_tail", np.zeros(len(ENERGY_COVERAGE_SCORES)))[score_index])
        total = low + retained + high
        outside_fraction = float((low + high) / total) if total > 0.0 else float("inf")
        score_passed = bool(
            np.isfinite(outside_fraction)
            and outside_fraction <= args.max_outside_fraction
        )
        passed = passed and score_passed
        scores[score] = {
            "low_tail": low,
            "retained": retained,
            "high_tail": high,
            "outside_fraction": outside_fraction,
            "passed": score_passed,
        }

    mg_bounds = energy_bounds_ev()
    payload = {
        "schema": "openmc2donjon.energy-coverage.v1",
        "decision": "passed" if passed else "failed",
        "statepoint": str(args.statepoint.resolve()),
        "energy_mesh_id": ENERGY_MESH_ID,
        "full_energy_min_ev": FULL_ENERGY_MIN_EV,
        "mg_energy_min_ev": mg_bounds[0],
        "mg_energy_max_ev": mg_bounds[-1],
        "full_energy_max_ev": FULL_ENERGY_MAX_EV,
        "max_outside_fraction": args.max_outside_fraction,
        "scores": scores,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for score, result in scores.items():
        print(
            f"{score}: outside={float(result['outside_fraction']):.6g} "
            f"limit={args.max_outside_fraction:.6g} "
            f"{'PASS' if result['passed'] else 'FAIL'}"
        )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
