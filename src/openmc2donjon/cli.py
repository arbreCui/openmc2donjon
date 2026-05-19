"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_diff import diff_hdf5_files
from .mgxs_inspect import inspect_files
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description=(
            "Convert an OpenMC MGXS HDF5 dump to DONJON ASCII LCM objects. "
            "Use 'openmc2donjon inspect <input_h5>' to inspect an HDF5 handoff "
            "'openmc2donjon diff <reference_h5> <candidate_h5>' to compare two "
            "handoffs, or 'openmc2donjon check <input_h5>' for input-contract preflight."
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="run HDF5 input-contract preflight before conversion",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="with --check, require ADF data for every mixture",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="with --check, comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="with --check, require explicit transport_total datasets",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="with --check, require positive volume attributes",
    )
    parser.add_argument(
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
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


def build_inspect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon inspect",
        description="Inspect OpenMC MGXS HDF5 files without converting them.",
    )
    parser.add_argument("input_h5", type=Path, nargs="+", help="MGXS HDF5 input file")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="number of mixtures to list per file (default: 20)",
    )
    parser.add_argument(
        "--all-mixtures",
        action="store_true",
        help="list every mixture instead of applying --limit",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable inspection JSON",
    )
    return parser


def build_diff_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon diff",
        description="Compare two OpenMC MGXS HDF5 handoff files.",
    )
    parser.add_argument("reference_h5", type=Path, help="reference MGXS HDF5 file")
    parser.add_argument("candidate_h5", type=Path, help="candidate MGXS HDF5 file")
    parser.add_argument(
        "--rtol",
        type=float,
        default=0.0,
        help="relative tolerance for numeric datasets and numeric attributes (default: 0)",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=0.0,
        help="absolute tolerance for numeric datasets and numeric attributes (default: 0)",
    )
    parser.add_argument(
        "--ignore-attrs",
        action="store_true",
        help="compare HDF5 object tree and datasets only, ignoring all attributes",
    )
    parser.add_argument(
        "--ignore-attr",
        action="append",
        default=[],
        help="ignore an attribute name wherever it appears; repeat as needed",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable diff JSON",
    )
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=20,
        help="maximum number of differences to print (default: 20)",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the diff report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and raw_argv[0] == "diff":
        return _diff_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "inspect":
        return _inspect_main(raw_argv[1:])
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

    if args.check:
        ok = run_preflight(
            [input_path],
            output_format=args.format,
            output_path=output_path,
            require_adf=args.require_adf,
            expected_adf_faces=args.expected_adf_faces,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            summary_json=args.check_summary_json,
        )
        if not ok:
            return 1

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
    ok = run_preflight(
        args.input_h5,
        output_format=args.format,
        output_path=args.output,
        require_adf=args.require_adf,
        expected_adf_faces=args.expected_adf_faces,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        summary_json=args.summary_json,
    )
    return 0 if ok or args.no_fail else 1


def _inspect_main(argv: list[str]) -> int:
    args = build_inspect_parser().parse_args(argv)
    reports = inspect_files(
        args.input_h5,
        limit=args.limit,
        all_mixtures=args.all_mixtures,
        summary_json=args.summary_json,
    )
    return 0 if all(report.ok for report in reports) else 1


def _diff_main(argv: list[str]) -> int:
    args = build_diff_parser().parse_args(argv)
    report = diff_hdf5_files(
        args.reference_h5,
        args.candidate_h5,
        rtol=args.rtol,
        atol=args.atol,
        compare_attrs=not args.ignore_attrs,
        ignored_attrs=tuple(args.ignore_attr),
        summary_json=args.summary_json,
        max_diffs=args.max_diffs,
    )
    return 0 if report.ok or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
