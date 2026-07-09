"""Write continuous-energy OpenMC XML for the IRENA SPH Stage 2 CSD colorset assembly."""

from __future__ import annotations

import argparse
from pathlib import Path

from irena_csd_colorset_model import RunSettings, export_ce_xml


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--batches", type=int, default=RunSettings.batches)
    parser.add_argument("--inactive", type=int, default=RunSettings.inactive)
    parser.add_argument("--particles", type=int, default=RunSettings.particles)
    parser.add_argument("--seed", type=int, default=RunSettings.seed)
    args = parser.parse_args(argv)

    export_ce_xml(
        args.case_dir,
        RunSettings(
            batches=args.batches,
            inactive=args.inactive,
            particles=args.particles,
            seed=args.seed,
        ),
    )
    print(f"wrote IRENA SPH Stage 2 CSD colorset CE case: {args.case_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
