"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import shlex
import sys
import tempfile
from typing import Any

from . import __version__
from ._logging import (
    CLI_LOGGING_VALUE_FLAGS,
    add_cli_logging_arguments,
    configure_cli_logging_from_args,
    is_cli_logging_flag,
)
from .commands import adf, diagnostics, fill, sph, web
from .commands.base import CommandSpec
from .energy_groups import MESH_RELATIVE_TOLERANCE
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .pygan_writer import convert_mgxs_hdf5_with_pygan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description=(
            "Convert an OpenMC MGXS HDF5 dump to DONJON ASCII LCM objects. "
            "Use 'openmc2donjon inspect <input_h5>' to inspect an HDF5 handoff, "
            "'openmc2donjon diff <reference_h5> <candidate_h5>' to compare two "
            "handoffs, 'openmc2donjon export-surface-flux <statepoint> ...' to "
            "export OpenMC face fluxes, 'openmc2donjon make-low-order-driver "
            "<input_h5> ...' to canonicalize a low-order driver handoff, "
            "'openmc2donjon check-low-order-driver <input_h5> <driver_h5>' to "
            "validate the low-order handoff, "
            "'openmc2donjon check-face-flux <input_h5> ...' to validate "
            "flux-ratio ADF face-flux inputs, "
            "'openmc2donjon make-homogeneous-face-flux <input_h5> ...' to "
            "reconstruct homogeneous face fluxes, 'openmc2donjon "
            "make-adf-sidecar <input_h5> ...' to create an ADF "
            "sidecar, 'openmc2donjon augment-adf <input_h5> ...' to inject "
            "computed discontinuity factors, 'openmc2donjon fill-zero-flux "
            "<input_h5> --macrolib PATH ...' to substitute macrolib XS into "
            "zero-flux fast-spectrum groups, 'openmc2donjon make-sph-sidecar "
            "<input_h5> ...', 'openmc2donjon make-sph-update-table "
            "<input_h5> ...', and 'openmc2donjon augment-sph <input_h5> ...' "
            "to carry OpenMC CE/MG SPH equivalence factors, "
            "'openmc2donjon bundle --output-dir DIR ...' to collect "
            "production artifacts, 'openmc2donjon validate-bundle manifest.json' "
            "to validate a bundle, 'openmc2donjon doctor' for environment checks, or "
            "'openmc2donjon check <input_h5>' for input-contract preflight."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    add_cli_logging_arguments(parser)
    parser.add_argument("input_h5", help="OpenMC MGXS library HDF5 file")
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib"),
        default="multicompo",
        help="output object format (default: multicompo)",
    )
    parser.add_argument(
        "--writer-backend",
        choices=("ascii", "pygan"),
        default="ascii",
        help=(
            "LCM ASCII writer backend (default: ascii). Use 'pygan' to build "
            "the same LCM tree with PyGan and let PyGan export the ASCII file."
        ),
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
        "--dry-run",
        action="store_true",
        help="run requested checks and resolve the output path without writing ASCII",
    )
    parser.add_argument(
        "--overwrite",
        "--force",
        action="store_true",
        help="allow replacing an existing ASCII output file",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help=(
            "run preflight with production defaults: volume, transport_total, "
            "fissionable H-FACTOR, declared mixture order, domain provenance, "
            "physics consistency gates, and production uncertainty gate"
        ),
    )
    parser.add_argument(
        "--require-mixture-order",
        action="store_true",
        help=(
            "with --check, require /mixture_names and matching 1-based "
            "source_domain_index attributes"
        ),
    )
    parser.add_argument(
        "--require-domain-mode",
        action="store_true",
        help="with --check, require a non-empty domain_mode root attribute",
    )
    parser.add_argument(
        "--require-source-domain-metadata",
        action="store_true",
        help="with --check, require source_domain_id and source_domain_type attributes",
    )
    parser.add_argument(
        "--require-openmc-volume-flux",
        action="store_true",
        help="with --check, require /openmc_volume_flux reference flux metadata",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="with --check, require ADF data for every mixture",
    )
    parser.add_argument(
        "--require-sph",
        action="store_true",
        help="with --check, require SPH data for every calculation",
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
        "--require-h-factor",
        action="store_true",
        help="with --check, require group-wise H-FACTOR/kappa-fission data for fissionable mixtures",
    )
    parser.add_argument(
        "--expected-energy-group-structure",
        default=None,
        help="with --check, require this energy_group_structure root attribute",
    )
    parser.add_argument(
        "--expected-energy-bounds",
        type=Path,
        default=None,
        help="with --check, text file containing expected energy bounds in eV",
    )
    parser.add_argument(
        "--expected-energy-bounds-sha256",
        default=None,
        help="with --check, require this /energy_bounds SHA-256 digest",
    )
    parser.add_argument(
        "--require-known-energy-mesh",
        action="store_true",
        help="with --check, fail if /energy_bounds is not a bundled known mesh",
    )
    parser.add_argument(
        "--warn-unknown-energy-mesh",
        action="store_true",
        help="with --check, warn if /energy_bounds is not a bundled known mesh",
    )
    parser.add_argument(
        "--energy-mesh-tolerance",
        type=float,
        default=MESH_RELATIVE_TOLERANCE,
        metavar="RTOL",
        help="with --check, relative tolerance for known energy-mesh matching",
    )
    parser.add_argument(
        "--scatter-row-balance-warn",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, warn if max |total - absorption - sum(P0 scatter out)| "
            "/ |total| exceeds REL"
        ),
    )
    parser.add_argument(
        "--scatter-row-balance-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, fail if max |total - absorption - sum(P0 scatter out)| "
            "/ |total| exceeds REL"
        ),
    )
    parser.add_argument(
        "--require-energy-bounds-consistency",
        action="store_true",
        help=(
            "with --check, require local mixture/state energy_bounds datasets "
            "to match global /energy_bounds"
        ),
    )
    parser.add_argument(
        "--chi-sum-tolerance",
        type=float,
        default=None,
        metavar="ABS",
        help="with --check, fail if fissionable chi sum error exceeds ABS",
    )
    parser.add_argument(
        "--require-adf-face-consistency",
        action="store_true",
        help="with --check, require all ADF-bearing calculations to share faces",
    )
    parser.add_argument(
        "--transport-p1-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, fail if explicit transport_total differs from "
            "total minus P1 scatter out by more than REL"
        ),
    )
    parser.add_argument(
        "--uncertainty-warn",
        type=float,
        default=0.05,
        metavar="REL",
        help="with --check, warn if any available *_std_dev / |mean| exceeds REL",
    )
    parser.add_argument(
        "--uncertainty-fail",
        type=float,
        default=None,
        metavar="REL",
        help="with --check, fail if any available *_std_dev / |mean| exceeds REL",
    )
    parser.add_argument(
        "--uncertainty-production-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, fail if production-critical uncertainty exceeds REL; "
            "this gates 1D XS and P0 scatter but leaves higher scatter moments "
            "warning-only"
        ),
    )
    parser.add_argument(
        "--uncertainty-mean-abs-floor",
        type=float,
        default=1.0e-12,
        metavar="ABS",
        help="with --check, skip relative uncertainty bins with |mean| <= ABS",
    )
    parser.add_argument(
        "--no-uncertainty-check",
        action="store_true",
        help="with --check, disable *_std_dev relative uncertainty checks",
    )
    parser.add_argument(
        "--require-std-dev-coverage",
        action="store_true",
        help=(
            "with --check, fail if any expected MGXS mean dataset is missing "
            "a matching *_std_dev uncertainty dataset"
        ),
    )
    parser.add_argument(
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable direct conversion summary JSON",
    )
    return parser


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description="Run an openmc2donjon utility command.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    add_cli_logging_arguments(parser)
    specs = _command_specs()
    visible_command_names: list[str] = []
    for spec in specs:
        if not spec.hidden:
            visible_command_names.append(spec.name)
            visible_command_names.extend(spec.aliases)
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="{" + ",".join(visible_command_names) + "}",
    )
    for spec in specs:
        parent = spec.parser_builder()
        command_parser = subparsers.add_parser(
            spec.name,
            aliases=list(spec.aliases),
            parents=[parent],
            add_help=False,
            help=argparse.SUPPRESS if spec.hidden else spec.help,
            description=parent.description,
        )
        if spec.hidden:
            # argparse keeps hidden subcommands callable but still lists them
            # unless their choice actions are removed from help rendering.
            subparsers._choices_actions = [
                action for action in subparsers._choices_actions if action.dest != spec.name
            ]
        add_cli_logging_arguments(command_parser, defaults=False)
        command_parser.set_defaults(func=spec.handler, _parser=command_parser)
    return parser


def _command_specs() -> tuple[CommandSpec, ...]:
    return (
        *adf.command_specs(),
        *fill.command_specs(),
        *sph.command_specs(),
        *diagnostics.command_specs(),
        *web.command_specs(),
    )


def _command_names() -> set[str]:
    names: set[str] = set()
    for spec in _command_specs():
        names.add(spec.name)
        names.update(spec.aliases)
    return names


def _is_command_invocation(raw_argv: list[str]) -> bool:
    skip_next = False
    for token in raw_argv:
        if skip_next:
            skip_next = False
            continue
        if token in _command_names():
            return True
        if token == "--":
            return False
        if is_cli_logging_flag(token):
            if token in CLI_LOGGING_VALUE_FLAGS:
                skip_next = True
            continue
        return False
    return False


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if _is_command_invocation(raw_argv):
        args = build_command_parser().parse_args(raw_argv)
        configure_cli_logging_from_args(args)
        return args.func(args)
    args = build_parser().parse_args(raw_argv)
    args._raw_argv = raw_argv
    configure_cli_logging_from_args(args)
    return _convert_handler(args)


def _convert_handler(args: argparse.Namespace) -> int:
    if args.production:
        args.check = True
    input_path = Path(args.input_h5).expanduser()
    if args.output:
        output_path = Path(args.output).expanduser()
    elif args.format == "macrolib":
        output_path = Path("out.macrolib.txt")
    else:
        output_path = Path("out.mcompo.txt")
    if args.summary_json is not None:
        args.summary_json = args.summary_json.expanduser()

    output_error = _validate_direct_output_path(
        input_path,
        output_path,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    if output_error is not None:
        sys.stderr.write(f"openmc2donjon: error: {output_error}\n")
        return 1
    summary_error = _validate_direct_summary_path(args.summary_json, output_path)
    if summary_error is not None:
        sys.stderr.write(f"openmc2donjon: error: {summary_error}\n")
        return 1

    preflight: dict[str, Any] | None = None
    preflight_ok = True
    output_size = (
        output_path.stat().st_size if output_path.exists() and output_path.is_file() else None
    )

    with contextlib.ExitStack() as stack:
        preflight_summary_json = args.check_summary_json
        if args.summary_json is not None and args.check and preflight_summary_json is None:
            tmpdir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            preflight_summary_json = tmpdir / "preflight_summary.json"

        if args.check:
            preflight_ok = _run_direct_preflight(
                args,
                input_path=input_path,
                output_path=output_path,
                summary_json=preflight_summary_json,
            )
            preflight = _read_json_payload(preflight_summary_json)
            if not preflight_ok:
                _write_direct_convert_summary_for_state(
                    args,
                    input_path=input_path,
                    output_path=output_path,
                    preflight=preflight,
                    preflight_ok=False,
                    converted=False,
                    output_size=output_size,
                )
                return 1

        if args.dry_run:
            _write_direct_convert_summary_for_state(
                args,
                input_path=input_path,
                output_path=output_path,
                preflight=preflight,
                preflight_ok=preflight_ok,
                converted=False,
                output_size=output_size,
            )
            return 0

        if args.writer_backend == "pygan":
            convert_mgxs_hdf5_with_pygan(
                input_path,
                output_path,
                output_format=args.format,
                root_name=args.root_name,
                comment=args.comment,
                burnup=args.burnup,
                h_factor_default=args.h_factor_default,
                mixture_names=args.mixture,
            )
        elif args.format == "macrolib":
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
        output_size = output_path.stat().st_size
        _write_direct_convert_summary_for_state(
            args,
            input_path=input_path,
            output_path=output_path,
            preflight=preflight,
            preflight_ok=preflight_ok,
            converted=True,
            output_size=output_size,
        )
    return 0


def _run_direct_preflight(
    args: argparse.Namespace,
    *,
    input_path: Path,
    output_path: Path,
    summary_json: Path | None,
) -> bool:
    return run_preflight(
        [input_path],
        output_format=args.format,
        output_path=output_path,
        production=args.production,
        require_adf=args.require_adf,
        require_sph=args.require_sph,
        expected_adf_faces=args.expected_adf_faces,
        require_mixture_order=args.require_mixture_order,
        require_domain_mode=args.require_domain_mode,
        require_source_domain_metadata=args.require_source_domain_metadata,
        require_openmc_volume_flux=args.require_openmc_volume_flux,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        require_h_factor=args.require_h_factor,
        expected_energy_group_structure=args.expected_energy_group_structure,
        expected_energy_bounds=args.expected_energy_bounds,
        expected_energy_bounds_sha256=args.expected_energy_bounds_sha256,
        require_known_energy_mesh=args.require_known_energy_mesh,
        warn_unknown_energy_mesh=args.warn_unknown_energy_mesh,
        energy_mesh_tolerance=args.energy_mesh_tolerance,
        scatter_row_balance_warn=args.scatter_row_balance_warn,
        scatter_row_balance_fail=args.scatter_row_balance_fail,
        require_energy_bounds_consistency=args.require_energy_bounds_consistency,
        chi_sum_tolerance=args.chi_sum_tolerance,
        require_adf_face_consistency=args.require_adf_face_consistency,
        transport_p1_fail=args.transport_p1_fail,
        uncertainty_warn=None if args.no_uncertainty_check else args.uncertainty_warn,
        uncertainty_fail=None if args.no_uncertainty_check else args.uncertainty_fail,
        uncertainty_production_fail=(
            None if args.no_uncertainty_check else args.uncertainty_production_fail
        ),
        uncertainty_mean_abs_floor=args.uncertainty_mean_abs_floor,
        require_std_dev_coverage=(
            False if args.no_uncertainty_check else args.require_std_dev_coverage
        ),
        summary_json=summary_json,
    )


def _validate_direct_output_path(
    input_path: Path,
    output_path: Path,
    *,
    overwrite: bool,
    dry_run: bool,
) -> str | None:
    if not input_path.exists():
        return f"input HDF5 not found: {input_path}"
    if not input_path.is_file():
        return f"input path is not a file: {input_path}"
    if output_path.resolve() == input_path.resolve():
        return "output path must differ from input"
    parent = output_path.parent
    if not parent.exists():
        return f"output directory not found: {parent}"
    if not parent.is_dir():
        return f"output parent is not a directory: {parent}"
    if output_path.exists() and not output_path.is_file():
        return f"output path exists but is not a file: {output_path}"
    if output_path.exists() and not overwrite and not dry_run:
        return f"output already exists; use --overwrite to replace it: {output_path}"
    return None


def _validate_direct_summary_path(summary_path: Path | None, output_path: Path) -> str | None:
    if summary_path is None:
        return None
    if summary_path.expanduser().resolve() == output_path.expanduser().resolve():
        return "summary JSON path must differ from output"
    if not summary_path.parent.exists():
        return f"summary JSON directory not found: {summary_path.parent}"
    if not summary_path.parent.is_dir():
        return f"summary JSON parent is not a directory: {summary_path.parent}"
    if summary_path.exists() and not summary_path.is_file():
        return f"summary JSON path exists but is not a file: {summary_path}"
    return None


def _read_json_payload(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _direct_convert_summary_payload(
    args: argparse.Namespace,
    *,
    input_path: Path,
    output_path: Path,
    preflight: dict[str, Any] | None,
    preflight_ok: bool,
    converted: bool,
    output_size: int | None,
    summary_written: bool,
) -> dict[str, Any]:
    dry_run = bool(args.dry_run)
    command = ["openmc2donjon", *list(getattr(args, "_raw_argv", []))]
    return {
        "schema": "openmc2donjon.convert.v1",
        "ok": bool(preflight_ok and (dry_run or converted)),
        "dry_run": dry_run,
        "converted": converted,
        "format": args.format,
        "writer_backend": args.writer_backend,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "summary_path": None if args.summary_json is None else str(args.summary_json),
        "summary_written": summary_written,
        "output_exists": output_path.exists(),
        "output_size": output_size,
        "preflight_ok": preflight_ok,
        "preflight": preflight,
        "cli_command": command,
        "cli_command_text": " ".join(shlex.quote(part) for part in command),
    }


def _write_direct_convert_summary_for_state(
    args: argparse.Namespace,
    *,
    input_path: Path,
    output_path: Path,
    preflight: dict[str, Any] | None,
    preflight_ok: bool,
    converted: bool,
    output_size: int | None,
) -> None:
    if args.summary_json is None:
        return
    _write_direct_convert_summary(
        args.summary_json,
        _direct_convert_summary_payload(
            args,
            input_path=input_path,
            output_path=output_path,
            preflight=preflight,
            preflight_ok=preflight_ok,
            converted=converted,
            output_size=output_size,
            summary_written=True,
        ),
    )


def _write_direct_convert_summary(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
