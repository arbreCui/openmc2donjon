#!/usr/bin/env python3
"""Preflight, convert, and read back a production MGXS HDF5 handoff file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

DEFAULT_PACKAGE_SRC = Path("/Users/wen/openmc-workspace/openmc2donjon/src")
PACKAGE_SRC = Path(os.environ.get("OPENMC2DONJON_SRC", DEFAULT_PACKAGE_SRC))
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from openmc2donjon import lcm_ascii  # noqa: E402
from openmc2donjon.macrolib import convert_mgxs_hdf5_to_macrolib  # noqa: E402
from openmc2donjon.multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5  # noqa: E402

from validate_mgxs_input_contract import (  # noqa: E402
    FAIL_DECISION,
    PASS_DECISION,
    output_name_issue,
    split_csv,
    validate_input,
)


SCHEMA = "openmc2donjon.convert-with-preflight.v1"


def main() -> int:
    args = parse_args()
    input_path = args.input_h5.resolve()
    output_path = output_path_for(args).resolve()
    expected_faces = split_csv(args.expected_adf_faces)

    print("OpenMC-to-DONJON convert with preflight")
    print(f"  schema: {SCHEMA}")
    print(f"  package_src: {PACKAGE_SRC}")
    print(f"  input: {input_path}")
    print(f"  output: {output_path}")
    print(f"  format: {args.format}")
    print()

    report = validate_input(
        input_path,
        require_adf=args.require_adf,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        expected_adf_faces=expected_faces,
    )
    name_issue = output_name_issue(output_path, args.format)
    if name_issue:
        report.fail(name_issue)

    print_preflight(report, name_issue)
    if not report.ok:
        print()
        print("Conversion decision")
        print(f"  {FAIL_DECISION}")
        write_summary_if_requested(args.summary_json, args, report, None, FAIL_DECISION)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    convert(input_path, output_path, args)
    readback = readback_output(output_path, args.format)

    print()
    print("Readback")
    print(f"  PASS  blocks={readback['block_count']} first={readback['first_name']}")
    print(f"        signature={readback['signature']}")
    print()
    print("Conversion decision")
    print("  convert_mgxs_with_preflight_passed")

    write_summary_if_requested(
        args.summary_json,
        args,
        report,
        readback,
        "convert_mgxs_with_preflight_passed",
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_h5", type=Path, help="converter-facing MGXS HDF5 file")
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib"),
        default="multicompo",
        help="output object format (default: multicompo)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output ASCII path (default: out.mco or out.macrolib.txt)",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="require ADF data for every mixture before conversion",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="require explicit transport_total instead of P1-derived STRD",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="require positive volume attributes on every mixture",
    )
    parser.add_argument(
        "--root-name",
        default=DEFAULT_ROOT_NAME,
        help=f"MULTICOMPO top-level LCM directory name (default: {DEFAULT_ROOT_NAME})",
    )
    parser.add_argument(
        "--comment",
        default=None,
        help="MULTICOMPO COMMENT block text",
    )
    parser.add_argument(
        "--burnup",
        type=float,
        default=None,
        help="write a single-point BURN axis for MULTICOMPO output",
    )
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help="write a constant H-FACTOR when the HDF5 does not provide one",
    )
    parser.add_argument(
        "--mixture",
        action="append",
        default=None,
        help="write only the named mixture; repeat to keep several mixtures",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable conversion summary",
    )
    return parser.parse_args()


def output_path_for(args: argparse.Namespace) -> Path:
    if args.output is not None:
        return args.output
    if args.format == "macrolib":
        return Path("out.macrolib.txt")
    return Path("out.mco")


def print_preflight(report, name_issue: str | None) -> None:
    status = "PASS" if report.ok else "FAIL"
    calculation_count = report.calculations or report.mixtures
    print("Preflight")
    print(f"  {status}  input contract")
    print(
        "        "
        f"energy_groups={report.energy_groups} legendre_order={report.legendre_order} "
        f"mixtures={report.mixtures} calculations={calculation_count}"
    )
    print(
        "        "
        f"state_points={report.state_points} "
        f"burnup_axis={report.burnup_axis_path or 'none'}"
    )
    print(
        "        "
        f"transport_total={report.transport_total_datasets}/{calculation_count} "
        f"strd_ready={report.transport_total_derivable}/{calculation_count}"
    )
    if report.adf_mixtures:
        print(
            "        "
            f"adf={report.adf_mixtures}/{calculation_count} "
            f"faces={','.join(report.adf_faces)}"
        )
    else:
        print("        adf=none")
    if name_issue:
        print(f"        FAIL: {name_issue}")
    for issue in report.issues[:12]:
        if issue != name_issue:
            print(f"        FAIL: {issue}")
    if len(report.issues) > 12:
        print(f"        ... {len(report.issues) - 12} more issue(s)")
    for warning in report.warnings[:6]:
        print(f"        WARN: {warning}")
    if len(report.warnings) > 6:
        print(f"        ... {len(report.warnings) - 6} more warning(s)")


def convert(input_path: Path, output_path: Path, args: argparse.Namespace) -> None:
    print()
    print("Convert")
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
    print(f"  PASS  wrote {output_path}")


def readback_output(output_path: Path, output_format: str) -> dict[str, Any]:
    blocks = lcm_ascii.read_lcm_ascii(output_path)
    if not blocks:
        raise ValueError(f"{output_path}: no LCM ASCII blocks read")

    first_name = next((block.name for block in blocks if block.name), None)
    signature = next(
        (
            str(block.data).strip()
            for block in blocks
            if block.name == "SIGNATURE" and isinstance(block.data, str)
        ),
        None,
    )
    expected = "L_MACROLIB" if output_format == "macrolib" else "L_MULTICOMPO"
    if signature != expected:
        raise ValueError(f"{output_path}: signature={signature!r}, expected {expected!r}")
    return {
        "block_count": len(blocks),
        "first_name": first_name,
        "signature": signature,
    }


def write_summary_if_requested(
    path: Path | None,
    args: argparse.Namespace,
    report,
    readback: dict[str, Any] | None,
    decision: str,
) -> None:
    if path is None:
        return
    payload = {
        "schema": SCHEMA,
        "decision": decision,
        "format": args.format,
        "input": str(args.input_h5),
        "output": str(output_path_for(args)),
        "preflight": {
            "decision": PASS_DECISION if report.ok else FAIL_DECISION,
            "ok": report.ok,
            "energy_groups": report.energy_groups,
            "legendre_order": report.legendre_order,
            "mixtures": report.mixtures,
            "stateful_mixtures": report.stateful_mixtures,
            "state_points": report.state_points,
            "calculations": report.calculations,
            "burnup_axis_path": report.burnup_axis_path,
            "burnup_axis_values": report.burnup_axis_values,
            "fissionable_mixtures": report.fissionable_mixtures,
            "transport_total_datasets": report.transport_total_datasets,
            "transport_total_derivable": report.transport_total_derivable,
            "adf_mixtures": report.adf_mixtures,
            "adf_faces": report.adf_faces,
            "issues": report.issues,
            "warnings": report.warnings,
        },
        "readback": readback,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
