"""SPH sidecar CLI commands for OpenMC-side equivalence factors."""

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
from ..openmc_sph_sidecar import create_openmc_sph_sidecar
from ..native_sph_validation import validate_native_sph
from ..sph_apply import (
    apply_sph_to_openmc_mgxs_hdf5,
    apply_sph_to_hdf5,
    print_report as print_sph_apply_report,
    write_summary as write_sph_apply_summary,
)
from ..sph_augment import (
    augment_hdf5_with_sph,
    create_macrolib_sph_sidecar,
    create_table_sph_sidecar,
    create_unity_sph_sidecar,
)
from ..sph_iteration import (
    FLUX_NORMALIZATIONS,
    SPH_TARGETS,
    ZERO_FLUX_POLICIES,
    create_sph_update_table,
)


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "validate-native-sph",
            build_validate_native_sph_parser,
            validate_native_sph_handler,
            "validate Converter -> DRAGON native SPH -> DONJON evidence",
        ),
        CommandSpec(
            "make-openmc-sph-sidecar",
            build_make_openmc_sph_sidecar_parser,
            make_openmc_sph_sidecar_handler,
            "compute OpenMC CE/MG SPH factors and write a sidecar",
        ),
        CommandSpec(
            "make-sph-sidecar",
            build_make_sph_sidecar_parser,
            make_sph_sidecar_handler,
            "create an SPH sidecar",
        ),
        CommandSpec(
            "make-sph-update-table",
            build_make_sph_update_table_parser,
            make_sph_update_table_handler,
            "compute an OpenMC CE/MG SPH factor table",
        ),
        CommandSpec(
            "apply-sph",
            build_apply_sph_parser,
            apply_sph_handler,
            "write an SPH-corrected MGXS HDF5 copy",
        ),
        CommandSpec(
            "augment-sph",
            build_augment_sph_parser,
            augment_sph_handler,
            "inject SPH factors into an MGXS HDF5 handoff",
        ),
    )


def build_validate_native_sph_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon validate-native-sph",
        description=(
            "Validate a physical OpenMC CE -> Converter -> DRAGON SPH -> "
            "DONJON SN/SPN handoff using reaction-rate balance, native SPH "
            "convergence, and OpenMC keff uncertainty."
        ),
    )
    parser.add_argument("reference_h5", type=Path, help="component MGXS HDF5 reference")
    parser.add_argument("--reference-macrolib", type=Path, required=True)
    parser.add_argument("--sph-macrolib", type=Path, required=True)
    parser.add_argument("--verify-macrolib", type=Path, required=True)
    parser.add_argument("--result-listing", type=Path, required=True)
    parser.add_argument(
        "--execution-deck",
        type=Path,
        default=None,
        help=(
            "exact CLE-2000 deck echoed by the result listing; required to "
            "prove that ADF and empirical eigenvalue multipliers were absent"
        ),
    )
    parser.add_argument("--energy-coverage", type=Path, default=None)
    parser.add_argument(
        "--converter-receipt",
        type=Path,
        default=None,
        help=(
            "hash-linked openmc2donjon.convert.v1 receipt for the reference "
            "HDF5 -> reference MACROLIB conversion; required for acceptance"
        ),
    )
    parser.add_argument(
        "--max-keff-sigma",
        type=float,
        default=2.0,
        help="maximum absolute OpenMC standard deviations for eigenvalue gates",
    )
    parser.add_argument("--summary-json", type=Path, required=True)
    return parser


def build_make_openmc_sph_sidecar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-openmc-sph-sidecar",
        description=(
            "Compute SPH factors from OpenMC continuous-energy reference flux "
            "and OpenMC multi-group macro flux, then write both an auditable "
            "CSV table and an SPH sidecar HDF5. The CE and MG calculations "
            "must use the same geometry and output regions."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument("-o", "--output", type=Path, required=True, help="SPH sidecar HDF5 output path")
    parser.add_argument(
        "--reference-flux",
        required=True,
        help="OpenMC CE reference flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--mg-flux",
        "--macro-flux",
        dest="mg_flux",
        required=True,
        help="OpenMC MG macro flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--table-output",
        type=Path,
        default=None,
        help="SPH CSV table output path (default: sidecar path with .sph.csv suffix)",
    )
    parser.add_argument(
        "--previous-sph",
        default=None,
        help="previous SPH CSV or HDF5 sidecar/source; defaults to unity",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=1.0,
        help="multiplicative update damping in 0..1 (default: 1.0)",
    )
    parser.add_argument("--clip-min", type=float, default=None, help="minimum SPH value after update")
    parser.add_argument("--clip-max", type=float, default=None, help="maximum SPH value after update")
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="none",
        help=(
            "scale MG flux before forming the SPH ratio: none, total, power, "
            "or auto using group-wise H-FACTOR/kappa_fission (default: none)"
        ),
    )
    parser.add_argument(
        "--sph-target",
        choices=SPH_TARGETS,
        default="flux",
        help=(
            "SPH fixed-point target: flux matches the corrected MG flux to "
            "the CE reference; rate preserves reaction rates "
            "(phi_mg = sph * reference flux) for spatially coupled regions "
            "(default: flux)"
        ),
    )
    parser.add_argument(
        "--zero-flux-policy",
        choices=ZERO_FLUX_POLICIES,
        default="reject",
        help=(
            "handling of bins where both CE and MG flux are exactly zero, "
            "e.g. thermal groups of a fast-spectrum case: reject fails, "
            "identity keeps the previous SPH value there (default: reject)"
        ),
    )
    parser.add_argument(
        "--flux-floor-rel",
        type=float,
        default=None,
        metavar="FLOAT",
        help=(
            "freeze bins whose CE reference flux is below FLOAT times the "
            "mixture's peak reference flux: their SPH keeps the previous "
            "value and they bypass zero-flux and std-dev gates, so noisy "
            "near-zero groups do not get fitted (default: none)"
        ),
    )
    parser.add_argument(
        "--freeze-groups",
        default=None,
        metavar="G1,G2",
        help=(
            "comma-separated 1-based group indices (same numbering as the "
            "update table and diagnostics) whose SPH is frozen at the "
            "previous value for all mixtures, e.g. 31 or 30,31 "
            "(default: none)"
        ),
    )
    parser.add_argument(
        "--tie-mixtures",
        action="append",
        default=None,
        metavar="MIX1,MIX2,...",
        help=(
            "declare a physical symmetry/equivalence class whose mixtures share "
            "one pooled SPH update; repeat for disjoint classes"
        ),
    )
    parser.add_argument(
        "--require-reference-flux-std-dev",
        action="store_true",
        help="fail unless the CE reference flux HDF5 source has a sibling std_dev dataset",
    )
    parser.add_argument(
        "--max-reference-flux-std-dev-rel",
        type=float,
        default=None,
        metavar="REL",
        help="fail if max(CE flux std_dev / mean) exceeds REL",
    )
    parser.add_argument(
        "--require-mg-flux-std-dev",
        action="store_true",
        help="fail unless the OpenMC MG flux HDF5 source has a sibling std_dev dataset",
    )
    parser.add_argument(
        "--max-mg-flux-std-dev-rel",
        type=float,
        default=None,
        metavar="REL",
        help="fail if max(MG flux std_dev / mean) exceeds REL",
    )
    parser.add_argument(
        "--sph-kind",
        default="openmc-ce-mg",
        help="root sph_kind provenance attribute (default: openmc-ce-mg)",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default="true",
        help="root sph_real provenance attribute (default: true)",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default="false",
        help="root sph_applied provenance attribute (default: false)",
    )
    parser.add_argument(
        "--source-label",
        default="openmc-ce-mg-sph",
        help="provenance label recorded in the summary JSON",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable OpenMC SPH sidecar summary JSON",
    )
    parser.add_argument("--force", action="store_true", help="overwrite generated outputs")
    return parser


def build_apply_sph_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon apply-sph",
        description=(
            "Apply OpenMC CE/MG SPH factors to an MGXS HDF5 file and write a "
            "corrected copy. Use --input-format converter for the "
            "openmc2donjon /mixtures layout, or --input-format openmc-mgxs "
            "for OpenMC native setN mgxs.h5 files used by the next OpenMC MG "
            "iteration. The command divides macroscopic XS datasets by NSPH."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file to correct")
    parser.add_argument(
        "--input-format",
        choices=("converter", "openmc-mgxs"),
        default="converter",
        help=(
            "input HDF5 layout: converter for openmc2donjon /mixtures, "
            "or openmc-mgxs for OpenMC native setN mgxs.h5 (default: converter)"
        ),
    )
    parser.add_argument(
        "--sph-source",
        type=Path,
        required=True,
        help="HDF5 sidecar containing SPH/NSPH vectors",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="SPH-corrected MGXS HDF5 output path",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH application summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the corrected output HDF5 if it already exists",
    )
    return parser


def build_augment_sph_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon augment-sph",
        description="Inject SPH equivalence factors into an MGXS HDF5 handoff.",
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file to augment")
    parser.add_argument(
        "--sph-source",
        type=Path,
        required=True,
        help="HDF5 sidecar containing SPH vectors",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="augmented MGXS HDF5 output path",
    )
    parser.add_argument(
        "--sph-kind",
        default=None,
        help="override root sph_kind provenance attribute",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default=None,
        help="override root sph_real provenance attribute",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default=None,
        help=(
            "mark whether the XS payload has already been SPH-corrected; "
            "the converter records factors but does not apply them"
        ),
    )
    parser.add_argument(
        "--sph-source-label",
        default=None,
        help="override root sph_source provenance attribute",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH augmentation summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the augmented output HDF5 if it already exists",
    )
    return parser


def build_make_sph_sidecar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-sph-sidecar",
        description=(
            "Create an SPH sidecar HDF5 from an MGXS handoff. Production SPH "
            "factors should come from OpenMC CE reference versus OpenMC MG "
            "macro calculations using the same geometry. Unity SPH is useful "
            "for plumbing; table mode canonicalizes external SPH factors from "
            "CSV; macrolib mode remains available for legacy NSPH extraction."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="SPH sidecar HDF5 output path",
    )
    parser.add_argument(
        "--mode",
        choices=("unity", "macrolib", "table"),
        default="unity",
        help="sidecar source mode (default: unity)",
    )
    parser.add_argument(
        "--macrolib",
        type=Path,
        default=None,
        help="for --mode macrolib, L_MACROLIB ASCII file containing GROUP/*/NSPH",
    )
    parser.add_argument(
        "--table",
        type=Path,
        default=None,
        help=(
            "for --mode table, CSV with either long columns mixture,group,sph "
            "or wide columns mixture,g1,g2,..."
        ),
    )
    parser.add_argument(
        "--value",
        type=float,
        default=1.0,
        help="constant SPH value for --mode unity (default: 1.0)",
    )
    parser.add_argument(
        "--sph-kind",
        default=None,
        help="root sph_kind provenance attribute (default: unity or macrolib-nsph)",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default=None,
        help="root sph_real provenance attribute (default: false for unity, true for macrolib)",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default=None,
        help="root sph_applied provenance attribute (default: false)",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH sidecar summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the sidecar HDF5 if it already exists",
    )
    return parser


def build_make_sph_update_table_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-sph-update-table",
        description=(
            "Create an external SPH CSV table from OpenMC CE reference flux "
            "and OpenMC MG macro flux using a damped flux-ratio update. The "
            "two flux sources should use the same geometry and output regions."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument("-o", "--output", type=Path, required=True, help="SPH CSV table output path")
    parser.add_argument(
        "--reference-flux",
        required=True,
        help="OpenMC CE reference flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--low-order-flux",
        required=True,
        help="OpenMC MG macro flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--previous-sph",
        default=None,
        help="previous SPH CSV or HDF5 sidecar/source; defaults to unity",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=1.0,
        help="multiplicative update damping in 0..1 (default: 1.0)",
    )
    parser.add_argument(
        "--clip-min",
        type=float,
        default=None,
        help="minimum SPH value after update",
    )
    parser.add_argument(
        "--clip-max",
        type=float,
        default=None,
        help="maximum SPH value after update",
    )
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="none",
        help=(
            "scale low-order flux before forming the SPH ratio: none, total, "
            "power, or auto using group-wise H-FACTOR/kappa_fission "
            "(default: none)"
        ),
    )
    parser.add_argument(
        "--source-label",
        default="openmc-ce-mg-sph",
        help="provenance label recorded in the summary JSON",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH iteration summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the SPH CSV output if it already exists",
    )
    return parser


def apply_sph_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.input_format == "openmc-mgxs":
            report = apply_sph_to_openmc_mgxs_hdf5(
                args.input_h5,
                sph_source=args.sph_source,
                output_h5=args.output,
                force=args.force,
            )
        else:
            report = apply_sph_to_hdf5(
                args.input_h5,
                sph_source=args.sph_source,
                output_h5=args.output,
                force=args.force,
            )
        print_sph_apply_report(report)
        if args.summary_json is not None:
            write_sph_apply_summary(args.summary_json, report)
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "apply-sph", exc)
    return 0


def augment_sph_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        augment_hdf5_with_sph(
            args.input_h5,
            sph_source=args.sph_source,
            output_h5=args.output,
            force=args.force,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real,
            sph_applied=args.sph_applied,
            sph_source_label=args.sph_source_label,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "augment-sph", exc)
    return 0


def make_sph_sidecar_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.mode == "unity":
            create_unity_sph_sidecar(
                args.input_h5,
                args.output,
                value=args.value,
                force=args.force,
                sph_kind=args.sph_kind or "unity",
                sph_real=False if args.sph_real is None else args.sph_real == "true",
                sph_applied=False if args.sph_applied is None else args.sph_applied == "true",
                summary_json=args.summary_json,
            )
        elif args.mode == "macrolib":
            if args.macrolib is None:
                parser.error("--mode macrolib requires --macrolib")
            create_macrolib_sph_sidecar(
                args.input_h5,
                args.output,
                macrolib_ascii=args.macrolib,
                force=args.force,
                sph_kind=args.sph_kind or "macrolib-nsph",
                sph_real=True if args.sph_real is None else args.sph_real == "true",
                sph_applied=False if args.sph_applied is None else args.sph_applied == "true",
                summary_json=args.summary_json,
            )
        elif args.mode == "table":
            if args.table is None:
                parser.error("--mode table requires --table")
            create_table_sph_sidecar(
                args.input_h5,
                args.output,
                table=args.table,
                force=args.force,
                sph_kind=args.sph_kind or "external-table",
                sph_real=True if args.sph_real is None else args.sph_real == "true",
                sph_applied=False if args.sph_applied is None else args.sph_applied == "true",
                summary_json=args.summary_json,
            )
        else:
            parser.error(f"unsupported --mode: {args.mode}")
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-sph-sidecar", exc)
    return 0


def make_sph_update_table_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        create_sph_update_table(
            args.input_h5,
            args.output,
            reference_flux=args.reference_flux,
            low_order_flux=args.low_order_flux,
            previous_sph=args.previous_sph,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-sph-update-table", exc)
    return 0


def _parse_freeze_groups(raw: str | None) -> tuple[int, ...] | None:
    if raw is None:
        return None
    items = [item.strip() for item in str(raw).split(",") if item.strip()]
    if not items:
        raise ValueError("--freeze-groups must list at least one group index")
    try:
        return tuple(int(item) for item in items)
    except ValueError as exc:
        raise ValueError("--freeze-groups must be comma-separated integers") from exc


def _parse_tie_mixture_groups(
    raw_groups: list[str] | None,
) -> tuple[tuple[str, ...], ...] | None:
    if raw_groups is None:
        return None
    groups: list[tuple[str, ...]] = []
    for raw in raw_groups:
        group = tuple(item.strip() for item in str(raw).split(",") if item.strip())
        if len(group) < 2:
            raise ValueError("--tie-mixtures must list at least two mixture names")
        groups.append(group)
    return tuple(groups)


def make_openmc_sph_sidecar_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        create_openmc_sph_sidecar(
            args.input_h5,
            args.output,
            reference_flux=args.reference_flux,
            mg_flux=args.mg_flux,
            table_output=args.table_output,
            previous_sph=args.previous_sph,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            sph_target=args.sph_target,
            zero_flux_policy=args.zero_flux_policy,
            flux_floor_rel=args.flux_floor_rel,
            freeze_groups=_parse_freeze_groups(args.freeze_groups),
            tie_mixture_groups=_parse_tie_mixture_groups(args.tie_mixtures),
            require_reference_flux_std_dev=args.require_reference_flux_std_dev,
            max_reference_flux_std_dev_rel=args.max_reference_flux_std_dev_rel,
            require_mg_flux_std_dev=args.require_mg_flux_std_dev,
            max_mg_flux_std_dev_rel=args.max_mg_flux_std_dev_rel,
            source_label=args.source_label,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real == "true",
            sph_applied=args.sph_applied == "true",
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-openmc-sph-sidecar", exc)
    return 0


def print_native_sph_validation(payload: dict[str, object]) -> None:
    """Render the native-SPH validation result as the CLI JSON result."""

    print(json.dumps(payload, indent=2, sort_keys=True))


def validate_native_sph_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        payload = validate_native_sph(
            args.reference_h5,
            args.reference_macrolib,
            args.sph_macrolib,
            args.verify_macrolib,
            args.result_listing,
            output_json=args.summary_json,
            energy_coverage_json=args.energy_coverage,
            converter_receipt_json=args.converter_receipt,
            execution_deck=args.execution_deck,
            max_keff_sigma=args.max_keff_sigma,
        )
        print_native_sph_validation(payload)
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "validate-native-sph", exc)
    return 0 if payload["quality"]["production_ready"] else 2
