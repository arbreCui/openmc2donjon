"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .commands import adf, diagnostics, openmc, sph
from .commands.base import CommandSpec
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5


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
            "computed discontinuity factors, 'openmc2donjon make-sph-sidecar "
            "<input_h5> ...', 'openmc2donjon make-sph-update-table "
            "<input_h5> ...', and 'openmc2donjon augment-sph <input_h5> ...' "
            "to iterate and carry SPH equivalence factors, "
            "'openmc2donjon extract-donjon-volume-flux <input_h5> ...' to "
            "adapt DONJON L_FLUX dumps into canonical low-order volume flux, "
            "'openmc2donjon run-sph-iteration <input_h5> ...' to run one "
            "fixed-OpenMC SPH iteration handoff, "
            "'openmc2donjon run-sph-loop --config loop.json' to iterate "
            "DONJON solves and SPH handoffs, "
            "'openmc2donjon make-donjon-sph-loop-config ...' to write a "
            "generic DONJON-backed loop config, "
            "'openmc2donjon make-sph-loop-scaffold <input_h5> ...' to write "
            "reference flux, scalar-flux map, and loop config from an OpenMC "
            "handoff, "
            "'openmc2donjon prepare-openmc-sph-loop ...' to export an OpenMC "
            "recipe and prepare the SPH loop handoff in one run, "
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
        "--production",
        action="store_true",
        help=(
            "run preflight with production defaults: volume, transport_total, "
            "fissionable H-FACTOR, declared mixture order, row-balance "
            "warnings, and production uncertainty gate"
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
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    for spec in _command_specs():
        parent = spec.parser_builder()
        command_parser = subparsers.add_parser(
            spec.name,
            aliases=list(spec.aliases),
            parents=[parent],
            add_help=False,
            help=spec.help,
            description=parent.description,
        )
        command_parser.set_defaults(func=spec.handler, _parser=command_parser)
    return parser


def _command_specs() -> tuple[CommandSpec, ...]:
    return (
        *openmc.command_specs(),
        *adf.command_specs(),
        *sph.command_specs(),
        *diagnostics.command_specs(),
    )


def _command_names() -> set[str]:
    names: set[str] = set()
    for spec in _command_specs():
        names.add(spec.name)
        names.update(spec.aliases)
    return names


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and raw_argv[0] in _command_names():
        args = build_command_parser().parse_args(raw_argv)
        return args.func(args)
    return _convert_handler(build_parser().parse_args(raw_argv))


def _convert_handler(args: argparse.Namespace) -> int:
    if args.production:
        args.check = True
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
            production=args.production,
            require_adf=args.require_adf,
            require_sph=args.require_sph,
            expected_adf_faces=args.expected_adf_faces,
            require_mixture_order=args.require_mixture_order,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            require_h_factor=args.require_h_factor,
            expected_energy_group_structure=args.expected_energy_group_structure,
            expected_energy_bounds=args.expected_energy_bounds,
            expected_energy_bounds_sha256=args.expected_energy_bounds_sha256,
            scatter_row_balance_warn=args.scatter_row_balance_warn,
            scatter_row_balance_fail=args.scatter_row_balance_fail,
            uncertainty_warn=None if args.no_uncertainty_check else args.uncertainty_warn,
            uncertainty_fail=None if args.no_uncertainty_check else args.uncertainty_fail,
            uncertainty_production_fail=(
                None if args.no_uncertainty_check else args.uncertainty_production_fail
            ),
            uncertainty_mean_abs_floor=args.uncertainty_mean_abs_floor,
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


if __name__ == "__main__":
    raise SystemExit(main())
