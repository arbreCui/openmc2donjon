"""OpenMC recipe-driven CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .acceptance import add_sph_loop_acceptance_args, sph_loop_acceptance_from_args
from .base import (
    USER_FACING_EXCEPTIONS,
    CommandSpec,
    exit_with_command_error,
    parser_from_args,
)
from ..multicompo import DEFAULT_ROOT_NAME
from ..openmc_sph_loop_handoff import prepare_openmc_sph_loop_handoff
from ..sph_iteration import FLUX_NORMALIZATIONS
from ..sph_loop_scaffold import parse_scalar_flux_map


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "prepare-openmc-sph-loop",
            build_prepare_openmc_sph_loop_parser,
            prepare_openmc_sph_loop_handler,
            "export an OpenMC recipe and prepare SPH loop inputs",
        ),
    )


def build_prepare_openmc_sph_loop_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon prepare-openmc-sph-loop",
        description=(
            "Export an OpenMC MGXS recipe/statepoint, write the initial DONJON "
            "ASCII handoff, and build the reference-flux/map/config scaffold "
            "needed by run-sph-loop."
        ),
    )
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--statepoint", type=Path, default=None)
    parser.add_argument("--no-load-statepoint", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--solve-template",
        type=Path,
        required=True,
        help="case-specific DONJON solve deck template; must dump L_FLUX",
    )
    parser.add_argument(
        "--scatter-mgxs-type",
        default=None,
        help="explicit OpenMC MGXS scattering type for the MGXS exporter",
    )
    parser.add_argument(
        "--format",
        choices=("macrolib", "multicompo"),
        default="macrolib",
        help="initial and loop ASCII handoff format",
    )
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--root-name", default=DEFAULT_ROOT_NAME)
    parser.add_argument("--h-factor-default", type=float, default=None)
    parser.add_argument("--no-check", action="store_true")
    parser.add_argument("--check-summary-json", type=Path, default=None)
    parser.add_argument(
        "--production",
        action="store_true",
        help=(
            "enable production preflight defaults for the exported MGXS handoff"
        ),
    )
    parser.add_argument("--no-require-volume", action="store_true")
    parser.add_argument("--require-h-factor", action="store_true")
    parser.add_argument("--no-require-transport-dataset", action="store_true")
    parser.add_argument("--expected-energy-group-structure", default=None)
    parser.add_argument("--expected-energy-bounds", type=Path, default=None)
    parser.add_argument("--expected-energy-bounds-sha256", default=None)
    parser.add_argument("--scatter-row-balance-warn", type=float, default=None)
    parser.add_argument("--scatter-row-balance-fail", type=float, default=None)
    parser.add_argument("--uncertainty-warn", type=float, default=0.05)
    parser.add_argument("--uncertainty-fail", type=float, default=None)
    parser.add_argument("--uncertainty-production-fail", type=float, default=None)
    parser.add_argument("--uncertainty-mean-abs-floor", type=float, default=1.0e-12)
    parser.add_argument("--no-uncertainty-check", action="store_true")
    parser.add_argument(
        "--reference-flux",
        default=None,
        help=(
            "OpenMC reference flux source as CSV, HDF5, or file.h5::dataset; "
            "default is <run-dir>/mgxs_library.h5::openmc_volume_flux"
        ),
    )
    parser.add_argument("--reference-flux-dataset", default="openmc_volume_flux")
    parser.add_argument("--scaffold-dir", type=Path, default=None)
    parser.add_argument(
        "--run-script-output",
        type=Path,
        default=None,
        help="optional path for the generated run_sph_loop.sh helper",
    )
    parser.add_argument(
        "--scalar-flux-map",
        default=None,
        help="comma-separated DONJON scalar unknown ids, e.g. FUEL=1,MOD=2",
    )
    parser.add_argument(
        "--sequential-scalar-flux-map",
        action="store_true",
        help="write scalar_flux_ids=1..N in MGXS mixture order",
    )
    parser.add_argument(
        "--donjon-root",
        type=Path,
        default=Path("/Users/wen/dragon-5.1/Donjon"),
    )
    parser.add_argument("--apply-template", type=Path, default=None)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--clip-min", type=float, default=0.5)
    parser.add_argument("--clip-max", type=float, default=3.0)
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="none",
        help=(
            "scale DONJON flux before forming SPH ratios: none, total, or power "
            "using group-wise H-FACTOR/kappa_fission (default: none)"
        ),
    )
    parser.add_argument("--sph-change-tolerance", type=float, default=None)
    parser.add_argument("--flux-ratio-tolerance", type=float, default=None)
    parser.add_argument("--min-iterations", type=int, default=1)
    parser.add_argument("--fail-on-nonconvergence", action="store_true")
    add_sph_loop_acceptance_args(parser)
    parser.add_argument("--case-id-prefix", default="openmc_sph_loop")
    parser.add_argument("--stage-prefix", default="odj_openmc_sph_loop")
    parser.add_argument(
        "--case-dir",
        default="openmc2donjon/case_runs/openmc_sph_loop",
        help="DONJON data-relative directory where rendered decks are written",
    )
    parser.add_argument("--sph-kind", default="openmc-sph-loop")
    parser.add_argument("--sph-real", choices=("true", "false"), default="false")
    parser.add_argument("--sph-applied", choices=("true", "false"), default="false")
    parser.add_argument("--source-label", default="OpenMC SPH loop handoff")
    parser.add_argument("--postprocess-output", default="corrected.macrolib.txt")
    parser.add_argument("--no-final-solve", action="store_true")
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--scaffold-summary-json", type=Path, default=None)
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=None,
        help="write a manifest-backed OpenMC SPH loop handoff bundle in this directory",
    )
    parser.add_argument(
        "--bundle-manifest-name",
        default="manifest.json",
        help="handoff bundle manifest filename (default: manifest.json)",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def prepare_openmc_sph_loop_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.production and args.no_check:
            parser.error("--production cannot be used with --no-check")
        scalar_flux_ids = (
            None if args.scalar_flux_map is None else parse_scalar_flux_map(args.scalar_flux_map)
        )
        prepare_openmc_sph_loop_handoff(
            recipe=args.recipe,
            statepoint=args.statepoint,
            no_load_statepoint=args.no_load_statepoint,
            run_dir=args.run_dir,
            solve_template=args.solve_template,
            scatter_mgxs_type=args.scatter_mgxs_type,
            output_format=args.format,
            output=args.output,
            root_name=args.root_name,
            h_factor_default=args.h_factor_default,
            check=not args.no_check,
            check_summary_json=args.check_summary_json,
            production=args.production,
            require_volume=not args.no_require_volume,
            require_h_factor=args.require_h_factor,
            require_transport_dataset=not args.no_require_transport_dataset,
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
            reference_flux=args.reference_flux,
            reference_flux_dataset=args.reference_flux_dataset,
            scaffold_dir=args.scaffold_dir,
            run_script_output=args.run_script_output,
            scalar_flux_ids=scalar_flux_ids,
            sequential_scalar_flux_map=args.sequential_scalar_flux_map,
            donjon_root=args.donjon_root,
            apply_template=args.apply_template,
            python_bin=args.python_bin,
            iterations=args.iterations,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            sph_change_tolerance=args.sph_change_tolerance,
            flux_ratio_tolerance=args.flux_ratio_tolerance,
            min_iterations=args.min_iterations,
            fail_on_nonconvergence=args.fail_on_nonconvergence,
            acceptance=sph_loop_acceptance_from_args(args),
            case_id_prefix=args.case_id_prefix,
            stage_prefix=args.stage_prefix,
            case_dir=args.case_dir,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real == "true",
            sph_applied=args.sph_applied == "true",
            source_label=args.source_label,
            postprocess_output=args.postprocess_output,
            final_solve=not args.no_final_solve,
            force=args.force,
            summary_json=args.summary_json,
            scaffold_summary_json=args.scaffold_summary_json,
            bundle_dir=args.bundle_dir,
            bundle_manifest_name=args.bundle_manifest_name,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "prepare-openmc-sph-loop", exc)
    return 0
