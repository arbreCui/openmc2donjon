"""Zero-flux fill CLI command for fast-spectrum MGXS handoffs."""

from __future__ import annotations

import argparse
from pathlib import Path

from .base import (
    USER_FACING_EXCEPTIONS,
    CommandSpec,
    exit_with_command_error,
    parser_from_args,
)
from ..zero_flux_fill import (
    DEFAULT_LABEL_ATTR,
    fill_zero_flux_groups,
    print_report as print_zero_flux_fill_report,
    write_summary as write_zero_flux_fill_summary,
)


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "fill-zero-flux",
            build_fill_zero_flux_parser,
            fill_zero_flux_handler,
            "substitute macrolib XS into zero-flux (mixture, group) bins",
        ),
    )


def build_fill_zero_flux_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon fill-zero-flux",
        description=(
            "Substitute exact material XS from an OpenMC MG macrolib into "
            "the (mixture, group) bins of a converter MGXS HDF5 where the "
            "flux-weighted tallies are zero: bins with total == 0, or "
            "transport_total <= 0 when that dataset is present. Optional "
            "uncertainty and scatter-row overshoot criteria cover nonzero "
            "micro-flux bins whose rate/flux estimators are unphysical. This is a "
            "mandatory step for fast-spectrum cores whose thermal groups "
            "carry no Monte Carlo flux. Mixtures are matched to macrolib "
            "materials through a mixture label attribute."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="converter MGXS HDF5 file to fill")
    parser.add_argument(
        "--macrolib",
        type=Path,
        required=True,
        help="OpenMC MG macrolib HDF5 the transport run consumed",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="filled MGXS HDF5 output path (copy of the input)",
    )
    destination.add_argument(
        "--in-place",
        action="store_true",
        help="edit the input HDF5 in place instead of writing a copy",
    )
    parser.add_argument(
        "--label-attr",
        default=DEFAULT_LABEL_ATTR,
        help=(
            "mixture attribute naming the macrolib material to substitute "
            f"from (default: {DEFAULT_LABEL_ATTR})"
        ),
    )
    parser.add_argument(
        "--max-total-rel-std-dev",
        type=float,
        default=None,
        help=(
            "also fill bins whose total XS relative std_dev exceeds this "
            "threshold (micro-flux noise bins with unphysical rate/flux "
            "spikes; degenerate single-score bins carry rel std sqrt(2))"
        ),
    )
    parser.add_argument(
        "--max-scatter-row-overshoot-rel",
        type=float,
        default=None,
        help=(
            "also fill bins whose P0 out-scatter row exceeds total XS by "
            "more than this relative tolerance (solver-destabilizing "
            "micro-flux noise)"
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable zero-flux fill summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the filled output HDF5 if it already exists",
    )
    return parser


def fill_zero_flux_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        report = fill_zero_flux_groups(
            args.input_h5,
            macrolib=args.macrolib,
            output_h5=args.output,
            in_place=args.in_place,
            label_attr=args.label_attr,
            force=args.force,
            max_total_rel_std_dev=args.max_total_rel_std_dev,
            max_scatter_row_overshoot_rel=args.max_scatter_row_overshoot_rel,
        )
        print_zero_flux_fill_report(report)
        if args.summary_json is not None:
            write_zero_flux_fill_summary(args.summary_json, report)
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "fill-zero-flux", exc)
    return 0
