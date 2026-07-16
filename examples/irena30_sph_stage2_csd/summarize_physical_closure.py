"""Assemble a permanently withdrawn Stage-2 colorset diagnostic record."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import openmc


def _keff(path: Path) -> dict[str, float]:
    with openmc.StatePoint(str(path)) as statepoint:
        value = statepoint.keff
        return {
            "mean": float(value.nominal_value),
            "std_dev": float(value.std_dev),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ce-statepoint", type=Path, required=True)
    parser.add_argument("--uncorrected-mg-statepoint", type=Path, required=True)
    parser.add_argument("--corrected-mg-statepoint", type=Path, required=True)
    parser.add_argument("--energy-coverage", type=Path, required=True)
    parser.add_argument("--validation-iteration", type=Path, required=True)
    parser.add_argument("--corrected-h5", type=Path, required=True)
    parser.add_argument("--converter-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    ce = _keff(args.ce_statepoint)
    uncorrected = _keff(args.uncorrected_mg_statepoint)
    corrected = _keff(args.corrected_mg_statepoint)
    validation = json.loads(args.validation_iteration.read_text(encoding="utf-8"))
    raw_min = float(validation["raw_update_minimum"])
    raw_max = float(validation["raw_update_maximum"])
    residual = max(abs(raw_min - 1.0), abs(raw_max - 1.0))

    def comparison(candidate: dict[str, float]) -> dict[str, float]:
        delta = candidate["mean"] - ce["mean"]
        sigma = math.sqrt(candidate["std_dev"] ** 2 + ce["std_dev"] ** 2)
        return {
            "delta_k": delta,
            "delta_pcm": delta * 1.0e5,
            "combined_std_dev_pcm": sigma * 1.0e5,
        }

    payload = {
        "schema": "openmc2donjon.irena30-withdrawn-colorset-diagnostic.v1",
        "decision": "withdrawn_diagnostic_rejected",
        "diagnostic_completed": True,
        "physics_accepted": False,
        "production_ready": False,
        "model_scope": "withdrawn explicit seven-assembly local colorset diagnostic",
        "fullcore_acceptance_eligible": False,
        "withdrawal_reasons": [
            "OpenMC MG-side apply-sph is not the current IRENA native-DRAGON SPH route",
            "a local colorset does not establish the 91-position full-core leakage environment",
            "the current IRENA candidate requires 91 independent domains or "
            "21 exact D3 orbits pooled during OpenMC transport",
        ],
        "ce": {"statepoint": str(args.ce_statepoint.resolve()), "keff": ce},
        "mg_uncorrected": {
            "statepoint": str(args.uncorrected_mg_statepoint.resolve()),
            "keff": uncorrected,
            "comparison_to_ce": comparison(uncorrected),
        },
        "mg_sph_corrected": {
            "statepoint": str(args.corrected_mg_statepoint.resolve()),
            "keff": corrected,
            "comparison_to_ce": comparison(corrected),
        },
        "rate_fixed_point": {
            "max_update_residual": residual,
            "raw_update_minimum": raw_min,
            "raw_update_maximum": raw_max,
            "validation_summary": str(args.validation_iteration.resolve()),
        },
        "energy_coverage_summary": str(args.energy_coverage.resolve()),
        "corrected_handoff_h5": str(args.corrected_h5.resolve()),
        "converter_output": str(args.converter_output.resolve()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
