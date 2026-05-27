"""Write continuous-energy OpenMC XML for the CE/MG SPH colorset minicase."""

from __future__ import annotations

import argparse
from pathlib import Path

from colorset_model import (
    MG_MACRO_HISTOGRAM_BINS,
    MG_MACRO_LEGENDRE_ORDER,
    MG_MACRO_SCATTER_FORMAT,
    RunSettings,
    export_ce_xml,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir",
        type=Path,
        required=True,
        help="directory where CE materials/geometry/settings/tallies XML are written",
    )
    parser.add_argument("--batches", type=int, default=RunSettings.batches)
    parser.add_argument("--inactive", type=int, default=RunSettings.inactive)
    parser.add_argument("--particles", type=int, default=RunSettings.particles)
    parser.add_argument("--seed", type=int, default=RunSettings.seed)
    parser.add_argument(
        "--mg-macro-scatter-format",
        choices=("histogram", "legendre"),
        default=MG_MACRO_SCATTER_FORMAT,
        help=(
            "scatter-angle treatment tallied for the OpenMC MG macro solve "
            "(default: histogram, i.e. Hn)"
        ),
    )
    parser.add_argument(
        "--mg-macro-histogram-bins",
        type=int,
        default=MG_MACRO_HISTOGRAM_BINS,
        help="number of Hn angular histogram bins for the OpenMC MG macro solve",
    )
    parser.add_argument(
        "--mg-macro-legendre-order",
        type=int,
        default=MG_MACRO_LEGENDRE_ORDER,
        help="Legendre order if --mg-macro-scatter-format=legendre",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batches <= 0 or args.inactive < 0 or args.inactive >= args.batches:
        raise SystemExit("--batches must be positive and greater than --inactive")
    if args.particles <= 0:
        raise SystemExit("--particles must be positive")
    if args.mg_macro_histogram_bins <= 0:
        raise SystemExit("--mg-macro-histogram-bins must be positive")
    if args.mg_macro_legendre_order < 0:
        raise SystemExit("--mg-macro-legendre-order must be non-negative")
    settings = RunSettings(
        batches=args.batches,
        inactive=args.inactive,
        particles=args.particles,
        seed=args.seed,
    )
    export_ce_xml(
        args.case_dir,
        run_settings=settings,
        mg_macro_scatter_format=args.mg_macro_scatter_format,
        mg_macro_histogram_bins=args.mg_macro_histogram_bins,
        mg_macro_legendre_order=args.mg_macro_legendre_order,
    )
    print(f"wrote OpenMC CE colorset XML: {args.case_dir.resolve()}")
    if args.mg_macro_scatter_format == "histogram":
        print(f"MG macro scatter treatment: H{args.mg_macro_histogram_bins}")
    else:
        print(f"MG macro scatter treatment: P{args.mg_macro_legendre_order}")
    print(
        "statepoint target: "
        f"{(args.case_dir / f'statepoint.{args.batches}.h5').resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
