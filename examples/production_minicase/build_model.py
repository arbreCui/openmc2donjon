"""Write OpenMC XML inputs for the production minicase example."""

from __future__ import annotations

import argparse
from pathlib import Path

from minicase_model import RunSettings, export_openmc_xml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=Path("openmc_minicase"),
        help="directory where materials/geometry/settings/tallies XML are written",
    )
    parser.add_argument("--batches", type=int, default=RunSettings.batches)
    parser.add_argument("--inactive", type=int, default=RunSettings.inactive)
    parser.add_argument("--particles", type=int, default=RunSettings.particles)
    parser.add_argument("--seed", type=int, default=RunSettings.seed)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batches <= 0 or args.inactive < 0 or args.inactive >= args.batches:
        raise SystemExit("--batches must be positive and greater than --inactive")
    if args.particles <= 0:
        raise SystemExit("--particles must be positive")

    settings = RunSettings(
        batches=args.batches,
        inactive=args.inactive,
        particles=args.particles,
        seed=args.seed,
    )
    export_openmc_xml(args.case_dir, run_settings=settings)
    print(f"wrote OpenMC production minicase XML: {args.case_dir.resolve()}")
    print(
        "statepoint target: "
        f"{(args.case_dir / f'statepoint.{args.batches}.h5').resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
