"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import (
    FAIL_DECISION,
    PASS_DECISION,
    SCHEMA as MGXS_INPUT_CONTRACT_SCHEMA,
    output_name_issue,
    print_report,
    split_csv,
    validate_input,
    write_summary,
)
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description=(
            "Convert an OpenMC MGXS HDF5 dump to DONJON ASCII LCM objects. "
            "Use 'openmc2donjon check <input_h5>' for input-contract preflight."
        ),
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


def build_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon check",
        description="Validate OpenMC MGXS HDF5 files against the openmc2donjon input contract.",
    )
    parser.add_argument("input_h5", type=Path, nargs="+", help="MGXS HDF5 input file")
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib", "any"),
        default="any",
        help="expected converter output format for --output name checks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional intended converter output path; checks production extension",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="require ADF data for every mixture",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="require an explicit transport_total dataset, not only P1-derived STRD",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="require a positive volume attribute on every mixture",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable summary JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the preflight report",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and raw_argv[0] == "check":
        return _check_main(raw_argv[1:])

    args = build_parser().parse_args(raw_argv)
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


def _check_main(argv: list[str]) -> int:
    args = build_check_parser().parse_args(argv)
    expected_faces = split_csv(args.expected_adf_faces)
    reports = [
        validate_input(
            path,
            require_adf=args.require_adf,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            expected_adf_faces=expected_faces,
        )
        for path in args.input_h5
    ]
    output_issue = output_name_issue(args.output, args.format)
    ok = all(report.ok for report in reports) and output_issue is None
    decision = PASS_DECISION if ok else FAIL_DECISION

    print("OpenMC-to-DONJON MGXS input contract")
    print(f"  schema: {MGXS_INPUT_CONTRACT_SCHEMA}")
    print()
    for report in reports:
        print_report(report)
    if args.output:
        status = "PASS" if output_issue is None else "FAIL"
        print(f"  {status}  output name: {args.output}")
        if output_issue:
            print(f"        {output_issue}")
        print()
    print("MGXS input contract decision")
    print(f"  {decision}")

    if args.summary_json:
        write_summary(args.summary_json, reports, decision, output_issue)

    return 0 if ok or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
