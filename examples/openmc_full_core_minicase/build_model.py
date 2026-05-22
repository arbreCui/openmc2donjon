#!/usr/bin/env python3
"""Build OpenMC XML files for the full-core assembly-wise minicase."""

from __future__ import annotations

import argparse
from pathlib import Path

import full_core_model


def main() -> int:
    args = _parse_args()
    full_core_model.export_openmc_xml(
        args.case_dir,
        run_settings=full_core_model.RunSettings(
            batches=args.batches,
            inactive=args.inactive,
            particles=args.particles,
            seed=args.seed,
        ),
    )
    print(f"wrote OpenMC full-core minicase XML to {args.case_dir}")
    print(f"assembly domains: {len(full_core_model.DOMAIN_IDS)}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=Path("openmc_full_core_minicase"))
    parser.add_argument("--particles", type=int, default=3000)
    parser.add_argument("--batches", type=int, default=14)
    parser.add_argument("--inactive", type=int, default=4)
    parser.add_argument("--seed", type=int, default=91)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
