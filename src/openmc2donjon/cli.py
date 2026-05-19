"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description="Convert an OpenMC MGXS HDF5 dump to DONJON ASCII LCM objects.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    parser.add_argument("input_h5", help="OpenMC MGXS library HDF5 file")
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib"),
        default="multicompo",
        help="output object format (default: multicompo)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "output ASCII path (default: out.mcompo.txt for multicompo, "
            "out.macrolib.txt for macrolib)"
        ),
    )
    parser.add_argument(
        "--root-name",
        default=DEFAULT_ROOT_NAME,
        help=f"top-level LCM directory name (default: {DEFAULT_ROOT_NAME})",
    )
    parser.add_argument(
        "--comment",
        default=None,
        help="COMMENT block text (default: derived from input filename)",
    )
    parser.add_argument(
        "--burnup",
        type=float,
        default=None,
        help=(
            "write a single-point BURN parameter axis with this value; useful "
            "for D2P/PMAXS workflows that require PARKEY metadata"
        ),
    )
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help=(
            "write this constant H-FACTOR when the input HDF5 does not provide "
            "one; intended for D2P plumbing smokes, not production physics"
        ),
    )
    parser.add_argument(
        "--mixture",
        action="append",
        default=None,
        help=(
            "write only the named mixture; repeat to keep several mixtures. "
            "D2P/PMAXS fuel smokes typically require a single-mixture MCO"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input_h5)
    if args.output:
        output_path = Path(args.output)
    elif args.format == "macrolib":
        output_path = Path("out.macrolib.txt")
    else:
        output_path = Path("out.mcompo.txt")

    if args.format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            input_path,
            output_path,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    else:
        convert_mgxs_hdf5(
            input_path,
            output_path,
            root_name=args.root_name,
            comment=args.comment,
            burnup=args.burnup,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
