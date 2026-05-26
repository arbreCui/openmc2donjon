"""Diagnostics, comparison, and bundle CLI commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .base import (
    USER_FACING_EXCEPTIONS,
    CommandSpec,
    exit_with_command_error,
    parser_from_args,
)
from ..bundle import ArtifactSpec, bundle_artifacts, parse_extra_artifact, validate_bundle
from ..doctor import run_doctor
from ..energy_groups import MESH_RELATIVE_TOLERANCE
from ..mgxs_diff import diff_hdf5_files
from ..mgxs_input_contract import run_preflight
from ..mgxs_inspect import inspect_files
from ..pygan_backend import PyGanStatus, probe_pygan


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "bundle",
            build_bundle_parser,
            bundle_handler,
            "collect production artifacts into a manifest-backed directory",
        ),
        CommandSpec(
            "validate-bundle",
            build_validate_bundle_parser,
            validate_bundle_handler,
            "validate a manifest-backed production bundle",
            aliases=("check-bundle",),
        ),
        CommandSpec(
            "doctor",
            build_doctor_parser,
            doctor_handler,
            "check the local runtime environment",
        ),
        CommandSpec(
            "pygan-doctor",
            build_pygan_doctor_parser,
            pygan_doctor_handler,
            "check optional PyGan backend availability",
        ),
        CommandSpec(
            "diff",
            build_diff_parser,
            diff_handler,
            "compare two MGXS HDF5 handoff files",
        ),
        CommandSpec(
            "inspect",
            build_inspect_parser,
            inspect_handler,
            "inspect MGXS HDF5 handoff files",
        ),
        CommandSpec(
            "check",
            build_check_parser,
            check_handler,
            "validate MGXS HDF5 files against the input contract",
        ),
    )


def build_pygan_doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon pygan-doctor",
        description=(
            "Check whether the optional PyGan backend is importable. "
            "PyGan is used for DRAGON/DONJON validation and future alternate "
            "writers; the default converter writer remains pure Python ASCII."
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable PyGan availability summary",
    )
    return parser


def pygan_doctor_handler(args: argparse.Namespace) -> int:
    status = probe_pygan()
    payload = status.as_dict()
    if args.summary_json is not None:
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        args.summary_json.write_text(text, encoding="utf-8")

    print_pygan_status(status)
    return 0 if status.available else 1


def print_pygan_status(status: PyGanStatus) -> None:
    state = "available" if status.available else "unavailable"
    print(f"pygan_backend={state}")
    print(f"role={status.role}")
    for module in status.modules:
        if module.available:
            print(f"{module.name}=available ({module.module_file})")
        else:
            print(f"{module.name}=missing ({module.error})")
    if not status.available:
        print(f"install_hint={status.install_hint}")


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
        "--production",
        action="store_true",
        help=(
            "enable production preflight defaults: volume, transport_total, "
            "fissionable H-FACTOR, declared mixture order, domain provenance, "
            "physics consistency gates, and production uncertainty gate"
        ),
    )
    parser.add_argument(
        "--require-mixture-order",
        action="store_true",
        help=(
            "require /mixture_names and matching 1-based source_domain_index "
            "attributes"
        ),
    )
    parser.add_argument(
        "--require-domain-mode",
        action="store_true",
        help="require a non-empty /attrs domain_mode such as assembly, cell, or mesh",
    )
    parser.add_argument(
        "--require-source-domain-metadata",
        action="store_true",
        help="require source_domain_id and source_domain_type on every mixture",
    )
    parser.add_argument(
        "--require-openmc-volume-flux",
        action="store_true",
        help=(
            "require /openmc_volume_flux with MGXS/DONJON group order and "
            "matching mixture_names"
        ),
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="require ADF data for every mixture",
    )
    parser.add_argument(
        "--require-sph",
        action="store_true",
        help="require SPH data for every calculation",
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
        "--require-h-factor",
        action="store_true",
        help="require group-wise H-FACTOR/kappa-fission data for fissionable calculations",
    )
    parser.add_argument(
        "--expected-energy-group-structure",
        default=None,
        help="require this energy_group_structure root attribute",
    )
    parser.add_argument(
        "--expected-energy-bounds",
        type=Path,
        default=None,
        help="text file containing expected energy bounds in eV",
    )
    parser.add_argument(
        "--expected-energy-bounds-sha256",
        default=None,
        help="require this /energy_bounds SHA-256 digest",
    )
    parser.add_argument(
        "--require-known-energy-mesh",
        action="store_true",
        help="fail if /energy_bounds is not a bundled known energy mesh",
    )
    parser.add_argument(
        "--warn-unknown-energy-mesh",
        action="store_true",
        help="warn if /energy_bounds is not a bundled known energy mesh",
    )
    parser.add_argument(
        "--energy-mesh-tolerance",
        type=float,
        default=MESH_RELATIVE_TOLERANCE,
        metavar="RTOL",
        help="relative tolerance for bundled energy-mesh matching",
    )
    parser.add_argument(
        "--scatter-row-balance-warn",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "warn if max |total - absorption - sum(P0 scatter out)| / |total| "
            "exceeds REL"
        ),
    )
    parser.add_argument(
        "--scatter-row-balance-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "fail if max |total - absorption - sum(P0 scatter out)| / |total| "
            "exceeds REL"
        ),
    )
    parser.add_argument(
        "--require-energy-bounds-consistency",
        action="store_true",
        help="require local mixture/state energy_bounds to match global /energy_bounds",
    )
    parser.add_argument(
        "--chi-sum-tolerance",
        type=float,
        default=None,
        metavar="ABS",
        help="fail if fissionable chi normalization error exceeds ABS",
    )
    parser.add_argument(
        "--require-adf-face-consistency",
        action="store_true",
        help="require all ADF-bearing calculations to share face names",
    )
    parser.add_argument(
        "--transport-p1-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "fail if explicit transport_total differs from total minus P1 "
            "scatter out by more than REL"
        ),
    )
    parser.add_argument(
        "--uncertainty-warn",
        type=float,
        default=0.05,
        metavar="REL",
        help="warn if any available *_std_dev / |mean| exceeds REL (default: 0.05)",
    )
    parser.add_argument(
        "--uncertainty-fail",
        type=float,
        default=None,
        metavar="REL",
        help="fail if any available *_std_dev / |mean| exceeds REL",
    )
    parser.add_argument(
        "--uncertainty-production-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "fail if production-critical uncertainty exceeds REL; this gates "
            "1D XS and P0 scatter but leaves higher scatter moments warning-only"
        ),
    )
    parser.add_argument(
        "--uncertainty-mean-abs-floor",
        type=float,
        default=1.0e-12,
        metavar="ABS",
        help="skip relative uncertainty bins with |mean| <= ABS (default: 1e-12)",
    )
    parser.add_argument(
        "--no-uncertainty-check",
        action="store_true",
        help="disable *_std_dev relative uncertainty checks",
    )
    parser.add_argument(
        "--require-std-dev-coverage",
        action="store_true",
        help=(
            "fail if any expected MGXS mean dataset is missing a matching "
            "*_std_dev uncertainty dataset"
        ),
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


def build_doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon doctor",
        description="Check the local openmc2donjon runtime environment.",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        default=None,
        help="optional OpenMC export recipe to dry-run as part of the check",
    )
    parser.add_argument(
        "--statepoint",
        type=Path,
        default=None,
        help="optional statepoint path passed to the recipe dry-run",
    )
    parser.add_argument(
        "--load-statepoint",
        action="store_true",
        help="with --recipe and --statepoint, load the statepoint during recipe dry-run",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable doctor JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the doctor report",
    )
    return parser


def build_bundle_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon bundle",
        description="Collect production handoff artifacts into a manifest-backed directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory that will receive copied artifacts and manifest.json",
    )
    parser.add_argument(
        "--mgxs",
        type=Path,
        default=None,
        help="MGXS HDF5 handoff to include",
    )
    parser.add_argument(
        "--mcompo",
        type=Path,
        default=None,
        help="L_MULTICOMPO ASCII output to include",
    )
    parser.add_argument(
        "--macrolib",
        type=Path,
        default=None,
        help="L_MACROLIB ASCII output to include",
    )
    parser.add_argument(
        "--run-summary",
        type=Path,
        default=None,
        help="one-step conversion summary JSON to include",
    )
    parser.add_argument(
        "--check-summary",
        type=Path,
        default=None,
        help="input-contract preflight summary JSON to include",
    )
    parser.add_argument(
        "--inspect-summary",
        type=Path,
        default=None,
        help="MGXS inspect summary JSON to include",
    )
    parser.add_argument(
        "--doctor-summary",
        type=Path,
        default=None,
        help="doctor summary JSON to include",
    )
    parser.add_argument(
        "--diff-summary",
        type=Path,
        default=None,
        help="HDF5 diff summary JSON to include",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="additional artifact to include; repeat as needed",
    )
    parser.add_argument(
        "--manifest-name",
        default="manifest.json",
        help="manifest filename inside --output-dir (default: manifest.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing bundled files and manifest",
    )
    return parser


def build_validate_bundle_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon validate-bundle",
        description="Validate a manifest-backed production handoff bundle.",
    )
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=Path("manifest.json"),
        help="bundle manifest JSON to validate (default: manifest.json)",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable bundle validation summary JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the validation report",
    )
    return parser


def check_handler(args: argparse.Namespace) -> int:
    ok = run_preflight(
        args.input_h5,
        output_format=args.format,
        output_path=args.output,
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
        summary_json=args.summary_json,
    )
    return 0 if ok or args.no_fail else 1


def inspect_handler(args: argparse.Namespace) -> int:
    reports = inspect_files(
        args.input_h5,
        limit=args.limit,
        all_mixtures=args.all_mixtures,
        summary_json=args.summary_json,
    )
    return 0 if all(report.ok for report in reports) else 1


def diff_handler(args: argparse.Namespace) -> int:
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


def doctor_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    if args.statepoint is not None and args.recipe is None:
        parser.error("--statepoint can only be used with --recipe")
    if args.load_statepoint and args.recipe is None:
        parser.error("--load-statepoint can only be used with --recipe")
    if args.load_statepoint and args.statepoint is None:
        parser.error("--load-statepoint requires --statepoint")
    report = run_doctor(
        recipe=args.recipe,
        statepoint=args.statepoint,
        load_statepoint=args.load_statepoint,
        summary_json=args.summary_json,
    )
    return 0 if report.ok or args.no_fail else 1


def bundle_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    artifacts = _bundle_artifacts_from_args(args, parser)
    try:
        bundle_artifacts(
            output_dir=args.output_dir,
            artifacts=artifacts,
            manifest_name=args.manifest_name,
            force=args.force,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "bundle", exc)
    return 0


def validate_bundle_handler(args: argparse.Namespace) -> int:
    report = validate_bundle(args.manifest, summary_json=args.summary_json)
    return 0 if report.ok or args.no_fail else 1


def _bundle_artifacts_from_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> list[ArtifactSpec]:
    artifacts: list[ArtifactSpec] = []
    for label, path in (
        ("mgxs", args.mgxs),
        ("mcompo", args.mcompo),
        ("macrolib", args.macrolib),
        ("run-summary", args.run_summary),
        ("check-summary", args.check_summary),
        ("inspect-summary", args.inspect_summary),
        ("doctor-summary", args.doctor_summary),
        ("diff-summary", args.diff_summary),
    ):
        if path is not None:
            artifacts.append(ArtifactSpec(label=label, source=path))
    for raw in args.extra:
        try:
            artifacts.append(parse_extra_artifact(raw))
        except ValueError as exc:
            parser.error(f"--extra {raw!r}: {exc}")
    if not artifacts:
        parser.error("at least one artifact option is required")
    return artifacts
