#!/usr/bin/env python3
"""Compare DONJON k-effective against the paired OpenMC IRENA ZREFL run."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import openmc

SN8_PATTERN = r"OPENMC2DONJON IRENA30 ZREFL NCR SN8 K-EFFECTIVE\s+([0-9.+\-Ee]+)"
MCFD_PATTERN = r"OPENMC2DONJON IRENA30 ZREFL NCR MCFD DIFFUSION K-EFFECTIVE\s+([0-9.+\-Ee]+)"


def read_donjon_keff(result: Path, pattern: str) -> float:
    text = result.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(pattern, text)
    if not matches:
        raise SystemExit(f"no DONJON k-effective found in {result}")
    value = float(matches[-1])
    if value != value:  # NaN
        raise SystemExit(f"DONJON k-effective is NaN in {result}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statepoint", type=Path, required=True)
    parser.add_argument("--sn8-result", type=Path, required=True)
    parser.add_argument("--mcfd-result", type=Path, required=True)
    parser.add_argument("--multicompo", type=Path, required=True)
    parser.add_argument("--max-delta-pcm", type=float, default=300.0,
                        help="acceptance threshold on the SN8 transport delta")
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    with openmc.StatePoint(str(args.statepoint)) as sp:
        openmc_keff = float(sp.keff.nominal_value)
        openmc_std = float(sp.keff.std_dev)

    sn8_keff = read_donjon_keff(args.sn8_result, SN8_PATTERN)
    mcfd_keff = read_donjon_keff(args.mcfd_result, MCFD_PATTERN)

    def delta_pcm(donjon: float) -> float:
        return (donjon - openmc_keff) / openmc_keff * 1.0e5

    sn8_delta = delta_pcm(sn8_keff)
    mcfd_delta = delta_pcm(mcfd_keff)
    openmc_std_pcm = openmc_std / openmc_keff * 1.0e5
    passed = abs(sn8_delta) <= args.max_delta_pcm

    summary = {
        "schema": "openmc2donjon.irena30-zrefl-keff-comparison.v1",
        "decision": "irena30_zrefl_keff_comparison_passed" if passed
        else "irena30_zrefl_keff_comparison_failed",
        "openmc_keff": openmc_keff,
        "openmc_std": openmc_std,
        "openmc_std_pcm": openmc_std_pcm,
        "donjon_sn8_keff": sn8_keff,
        "donjon_sn8_delta_pcm": sn8_delta,
        "donjon_mcfd_diffusion_keff": mcfd_keff,
        "donjon_mcfd_diffusion_delta_pcm": mcfd_delta,
        "max_delta_pcm": args.max_delta_pcm,
        "statepoint": str(args.statepoint),
        "multicompo": str(args.multicompo),
        "sn8_result": str(args.sn8_result),
        "mcfd_result": str(args.mcfd_result),
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("IRENA-30 ZREFL k-eff comparison")
    print(f"  OpenMC:          {openmc_keff:.6f} +/- {openmc_std_pcm:.1f} pcm")
    print(f"  DONJON SN8:      {sn8_keff:.6f}  delta {sn8_delta:+.1f} pcm")
    print(f"  DONJON MCFD dif: {mcfd_keff:.6f}  delta {mcfd_delta:+.1f} pcm (diagnostic)")
    print(f"  summary: {args.summary}")
    if not passed:
        raise SystemExit(
            f"SN8 comparison failed: |{sn8_delta:.1f}| pcm > {args.max_delta_pcm:.1f} pcm"
        )
    print("  decision: irena30_zrefl_keff_comparison_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
