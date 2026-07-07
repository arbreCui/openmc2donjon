#!/usr/bin/env python3
"""Compare per-position fission-rate (power shape) distributions.

OpenMC side: the JSON written by ``extract_openmc_fission.py`` (52 fuel
positions, normalized to sum = 1).

DONJON side: the ``L_EDIT`` ASCII dump produced by the SN8 deck's
``EDI: ... MERG MIX COND SAVE``. After merging by mixture and condensing to
one group, the edition macrolib carries one ``NUSIGF`` (nu-fission XS) and
one ``FLUX-INTG`` (volume-integrated flux) value per mixture, so the
nu-fission (fission source) rate of mixture ``i`` is
``NUSIGF[i] * FLUX-INTG[i]``. Mixture order is the
multicompo order (ring/position), so fuel mixtures are matched to the
OpenMC positions by index.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from openmc2donjon import lcm_ascii

N_HEX = 91


def read_edi_fission_rates(edi_path: Path) -> np.ndarray:
    """Return the per-mixture fission rates (length 91) from the L_EDIT dump."""
    blocks = lcm_ascii.read_lcm_ascii(edi_path)
    by_name: dict[str, list[np.ndarray]] = {}
    for block in blocks:
        if block.name and isinstance(block.data, tuple) and len(block.data) == N_HEX:
            arr = np.asarray(block.data)
            if arr.dtype.kind == "f":
                by_name.setdefault(block.name, []).append(arr.astype(float))

    for key in ("NUSIGF", "FLUX-INTG"):
        if key not in by_name:
            raise SystemExit(
                f"{edi_path}: no {N_HEX}-entry {key!r} record found; "
                f"candidates: {sorted(by_name)}"
            )
        if len(by_name[key]) != 1:
            raise SystemExit(
                f"{edi_path}: expected exactly one condensed {key!r} record, "
                f"found {len(by_name[key])} (was the edition condensed to one group?)"
            )
    return by_name["NUSIGF"][0] * by_name["FLUX-INTG"][0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openmc-fission", type=Path, required=True)
    parser.add_argument("--edi", type=Path, required=True)
    parser.add_argument("--max-rel", type=float, default=0.02,
                        help="acceptance threshold on the worst per-position relative error")
    parser.add_argument("--max-rms", type=float, default=0.01,
                        help="acceptance threshold on the RMS relative error")
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    openmc_payload = json.loads(args.openmc_fission.read_text(encoding="utf-8"))
    positions = openmc_payload["positions"]
    names = sorted(positions)

    donjon_rates = read_edi_fission_rates(args.edi)
    # Mixture i (1-based) is multicompo order = (ring, position) order; the
    # OpenMC JSON name R{ring}P{pos}_{label} encodes the same order, so the
    # fuel mixture index is recovered from the position name.
    ring_sizes = [1, 6, 12, 18, 24, 30]
    ring_offsets = [sum(ring_sizes[:i]) for i in range(len(ring_sizes))]

    donjon = {}
    for name in names:
        ring = int(name[1])
        pos = int(name[3:5])
        donjon[name] = float(donjon_rates[ring_offsets[ring] + pos])
    total = sum(donjon.values())
    if total <= 0:
        raise SystemExit("DONJON fuel fission rates sum to zero")

    rel_errors = {}
    for name in names:
        openmc_rate = positions[name]["fission_rate"]
        donjon_rate = donjon[name] / total
        rel_errors[name] = (donjon_rate - openmc_rate) / openmc_rate

    worst_name = max(rel_errors, key=lambda k: abs(rel_errors[k]))
    max_rel = abs(rel_errors[worst_name])
    rms = math.sqrt(sum(v * v for v in rel_errors.values()) / len(rel_errors))
    passed = max_rel <= args.max_rel and rms <= args.max_rms

    summary = {
        "schema": "openmc2donjon.irena30-zrefl-power-comparison.v1",
        "decision": "irena30_zrefl_power_comparison_passed" if passed
        else "irena30_zrefl_power_comparison_failed",
        "positions": len(names),
        "max_rel_error": max_rel,
        "max_rel_error_position": worst_name,
        "rms_rel_error": rms,
        "max_rel_threshold": args.max_rel,
        "max_rms_threshold": args.max_rms,
        "openmc_fission": str(args.openmc_fission),
        "edi": str(args.edi),
        "per_position_rel_error": {name: rel_errors[name] for name in names},
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("IRENA-30 ZREFL power-shape comparison")
    print(f"  positions: {len(names)} fuel hexes")
    print(f"  max |rel error|: {max_rel * 100:.2f}% at {worst_name} (threshold {args.max_rel * 100:.1f}%)")
    print(f"  RMS rel error:   {rms * 100:.2f}% (threshold {args.max_rms * 100:.1f}%)")
    print(f"  summary: {args.summary}")
    if not passed:
        raise SystemExit("power-shape comparison failed")
    print("  decision: irena30_zrefl_power_comparison_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
