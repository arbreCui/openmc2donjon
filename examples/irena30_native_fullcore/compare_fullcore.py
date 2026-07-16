#!/usr/bin/env python3
"""Compare IRENA component-full-core k-effective and leakage to OpenMC CE."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import openmc

from openmc2donjon import lcm_ascii


N_POSITIONS = 91
PATTERNS = {
    "sn": r"OPENMC2DONJON IRENA30 COMPONENT FULLCORE SN K-EFFECTIVE\s+([0-9.+\-Ee]+)",
    "spn": r"OPENMC2DONJON IRENA30 COMPONENT FULLCORE SPN K-EFFECTIVE\s+([0-9.+\-Ee]+)",
}


def read_keff(path: Path, solver: str) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(PATTERNS[solver], text)
    if not matches:
        raise ValueError(f"no {solver.upper()} k-effective found in {path}")
    value = float(matches[-1])
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"invalid {solver.upper()} k-effective in {path}: {value}")
    return value


def read_edi_balance(path: Path, keff: float) -> dict[str, float]:
    blocks = lcm_ascii.read_lcm_ascii(path)
    records: dict[str, list[np.ndarray]] = {}
    for block in blocks:
        if block.name and isinstance(block.data, tuple) and len(block.data) == N_POSITIONS:
            values = np.asarray(block.data)
            if values.dtype.kind == "f":
                records.setdefault(block.name, []).append(values.astype(float))
    required = ("NUSIGF", "FLUX-INTG", "NTOT0", "SIGS00")
    selected: dict[str, np.ndarray] = {}
    for name in required:
        candidates = records.get(name, [])
        if len(candidates) != 1:
            raise ValueError(
                f"{path}: expected one {N_POSITIONS}-entry {name} record, "
                f"found {len(candidates)}"
            )
        selected[name] = candidates[0]
    production = float(np.sum(selected["NUSIGF"] * selected["FLUX-INTG"]))
    net_collision_loss = float(
        np.sum(
            (selected["NTOT0"] - selected["SIGS00"])
            * selected["FLUX-INTG"]
        )
    )
    source = production / keff
    leakage = source - net_collision_loss
    leakage_fraction = leakage / source
    if source <= 0.0 or not math.isfinite(leakage_fraction):
        raise ValueError(f"{path}: invalid condensed neutron balance")
    return {
        "fission_production": production,
        "net_collision_loss": net_collision_loss,
        "leakage_rate_from_balance": leakage,
        "leakage_fraction_from_balance": leakage_fraction,
    }


def _openmc_leakage(statepoint: openmc.StatePoint) -> tuple[float, float]:
    for row in statepoint.global_tallies:
        name = row["name"].decode() if isinstance(row["name"], bytes) else str(row["name"])
        if name == "leakage":
            return float(row["mean"]), float(row["std_dev"])
    raise ValueError("OpenMC statepoint has no global leakage tally")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statepoint", type=Path, required=True)
    parser.add_argument("--sn-result", type=Path, required=True)
    parser.add_argument("--spn-result", type=Path, required=True)
    parser.add_argument("--sn-edi", type=Path, required=True)
    parser.add_argument("--spn-edi", type=Path, required=True)
    parser.add_argument("--max-delta-pcm", type=float, default=300.0)
    parser.add_argument("--max-leakage-delta", type=float, default=0.005)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    with openmc.StatePoint(str(args.statepoint)) as statepoint:
        openmc_keff = float(statepoint.keff.nominal_value)
        openmc_keff_std = float(statepoint.keff.std_dev)
        openmc_leakage, openmc_leakage_std = _openmc_leakage(statepoint)
    solvers = {}
    passed = True
    for solver, result_path, edi_path in (
        ("sn", args.sn_result, args.sn_edi),
        ("spn", args.spn_result, args.spn_edi),
    ):
        keff = read_keff(result_path, solver)
        balance = read_edi_balance(edi_path, keff)
        delta_pcm = (keff - openmc_keff) / openmc_keff * 1.0e5
        z = (keff - openmc_keff) / openmc_keff_std
        leakage_delta = balance["leakage_fraction_from_balance"] - openmc_leakage
        solver_passed = (
            abs(delta_pcm) <= args.max_delta_pcm
            and abs(leakage_delta) <= args.max_leakage_delta
        )
        passed = passed and solver_passed
        solvers[solver] = {
            "keff": keff,
            "delta_pcm_relative": delta_pcm,
            "delta_openmc_sigma": z,
            **balance,
            "leakage_fraction_delta": leakage_delta,
            "passed": solver_passed,
            "result": str(result_path.resolve()),
            "edi": str(edi_path.resolve()),
        }

    payload = {
        "schema": "openmc2donjon.irena30-component-fullcore-physics.v1",
        "decision": (
            "irena30_component_fullcore_keff_leakage_passed"
            if passed
            else "irena30_component_fullcore_review_required"
        ),
        "openmc": {
            "statepoint": str(args.statepoint.resolve()),
            "keff": openmc_keff,
            "keff_std_dev": openmc_keff_std,
            "leakage_fraction": openmc_leakage,
            "leakage_fraction_std_dev": openmc_leakage_std,
        },
        "criteria": {
            "max_abs_relative_delta_pcm": args.max_delta_pcm,
            "max_abs_leakage_fraction_delta": args.max_leakage_delta,
            "empirical_eigenvalue_multiplier_used": False,
            "fullcore_sph_used": False,
        },
        "solvers": solvers,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"OpenMC CE k-effective: {openmc_keff:.8f} +/- {openmc_keff_std:.8f}")
    print(f"OpenMC CE leakage:     {openmc_leakage:.6f} +/- {openmc_leakage_std:.6f}")
    for solver, row in solvers.items():
        print(
            f"DONJON {solver.upper()}: k={row['keff']:.8f}, "
            f"delta={row['delta_pcm_relative']:+.1f} pcm, "
            f"leakage={row['leakage_fraction_from_balance']:.6f}"
        )
    print(f"decision: {payload['decision']}")
    if not passed:
        raise SystemExit("full-core k-effective/leakage comparison requires review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
