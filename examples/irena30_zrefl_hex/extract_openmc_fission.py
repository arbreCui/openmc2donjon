#!/usr/bin/env python3
"""Extract per-position nu-fission (fission source) rates from the IRENA
ZREFL statepoint.

Uses the same mgxs library tallies the MGXS export consumes: for every fuel
domain (INT/EXT labels) the nu-fission reaction-rate tally is summed over
energy groups. nu-fission is used because the converted multicompo carries
NUSIGF (not NFTOT), so the DONJON edition can only reconstruct the
nu-fission rate. The normalized distribution (total fuel source = 1) is
written as JSON keyed by mixture name (R{ring}P{pos}_{label}).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import openmc

FUEL_LABELS = ("INT", "EXT")


def _load_irena_module():
    path = Path(__file__).with_name("irena_model.py")
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_model_fission", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True,
                        help="OpenMC case directory (geometry/materials XML)")
    parser.add_argument("--statepoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="JSON output")
    args = parser.parse_args()

    irena = _load_irena_module()
    library = irena.build_library(case_dir=args.case_dir)
    with openmc.StatePoint(str(args.statepoint)) as statepoint:
        library.load_from_statepoint(statepoint)

    rates: dict[str, dict[str, float]] = {}
    for domain in library.domains:
        match = irena._CORE_CELL_RE.match(domain.name or "")
        ring, pos, label = int(match.group(1)), int(match.group(2)), match.group(3)
        if label not in FUEL_LABELS:
            continue
        nu_fission = library.get_mgxs(domain, "nu-fission")
        tally = nu_fission.rxn_rate_tally
        mean = float(np.sum(tally.mean))
        std = float(np.sqrt(np.sum(np.asarray(tally.std_dev) ** 2)))
        rates[irena.domain_name(ring, pos, label)] = {"mean": mean, "std": std}

    total = sum(entry["mean"] for entry in rates.values())
    payload = {
        "schema": "openmc2donjon.irena30-zrefl-nu-fission-rates.v1",
        "statepoint": str(args.statepoint),
        "normalization": "sum over fuel positions = 1",
        "positions": {
            name: {
                "fission_rate": entry["mean"] / total,
                "fission_rate_std": entry["std"] / total,
            }
            for name, entry in sorted(rates.items())
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(rates)} fuel-position fission rates to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
