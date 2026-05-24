"""Shared CLI helpers for SPH loop production acceptance gates."""

from __future__ import annotations

import argparse


def add_sph_loop_acceptance_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--acceptance-preset",
        choices=("mechanical", "production", "physics"),
        default=None,
        help=(
            "acceptance preset: 'mechanical' checks loop completion, final solve, "
            "metadata alignment, and no final clipping; 'production'/'physics' "
            "also require non-worsening flux residual and configured convergence "
            "tolerances"
        ),
    )
    parser.add_argument(
        "--acceptance-min-completed-iterations",
        type=int,
        default=None,
        help="production acceptance: require at least this many SPH update cycles",
    )
    parser.add_argument(
        "--acceptance-require-final-solve",
        action="store_true",
        help="production acceptance: require a final DONJON solve row",
    )
    parser.add_argument(
        "--acceptance-require-converged",
        action="store_true",
        help="production acceptance: require the convergence criteria to pass",
    )
    parser.add_argument(
        "--acceptance-require-mgxs-explicit-volumes",
        action="store_true",
        help=(
            "production acceptance: require every MGXS calculation to have an "
            "explicit positive volume"
        ),
    )
    parser.add_argument(
        "--acceptance-max-mgxs-default-volume-count",
        type=int,
        default=None,
        help="production acceptance: max MGXS calculation count using default volume 1.0",
    )
    parser.add_argument(
        "--acceptance-require-mgxs-h-factor",
        action="store_true",
        help=(
            "production acceptance: require every fissionable MGXS calculation "
            "to have group-wise H-FACTOR/kappa_fission data"
        ),
    )
    parser.add_argument(
        "--acceptance-max-mgxs-missing-h-factor-count",
        type=int,
        default=None,
        help=(
            "production acceptance: max fissionable MGXS calculation count "
            "missing H-FACTOR/kappa_fission data"
        ),
    )
    parser.add_argument(
        "--acceptance-require-mgxs-energy-bounds",
        action="store_true",
        help="production acceptance: require a valid global /energy_bounds dataset",
    )
    parser.add_argument(
        "--acceptance-require-known-mesh",
        action="store_true",
        help=(
            "production acceptance: require /energy_bounds to match a bundled "
            "known energy mesh"
        ),
    )
    parser.add_argument(
        "--acceptance-mesh-tolerance",
        type=float,
        default=None,
        help="production acceptance: relative tolerance for known energy mesh matching",
    )
    parser.add_argument(
        "--acceptance-require-mgxs-energy-bounds-consistency",
        action="store_true",
        help=(
            "production acceptance: require local mixture/state energy_bounds "
            "to match the global /energy_bounds dataset"
        ),
    )
    parser.add_argument(
        "--acceptance-max-mgxs-scatter-row-balance-rel",
        type=float,
        default=None,
        help="production acceptance: max relative MGXS scatter row-balance residual",
    )
    parser.add_argument(
        "--acceptance-max-mgxs-chi-sum-error",
        type=float,
        default=None,
        help="production acceptance: max absolute fissionable chi normalization error",
    )
    parser.add_argument(
        "--acceptance-require-mgxs-adf-face-consistency",
        action="store_true",
        help="production acceptance: require all ADF-bearing calculations to share faces",
    )
    parser.add_argument(
        "--acceptance-max-mgxs-transport-p1-rel",
        type=float,
        default=None,
        help="production acceptance: max relative transport_total/P1 residual",
    )
    parser.add_argument(
        "--acceptance-max-sph-rel-change",
        type=float,
        default=None,
        help="production acceptance: max relative SPH change in the last update",
    )
    parser.add_argument(
        "--acceptance-max-flux-ratio-residual",
        type=float,
        default=None,
        help="production acceptance: max |low_order/reference - 1| in the last update",
    )
    parser.add_argument(
        "--acceptance-max-final-to-initial-flux-residual-ratio",
        type=float,
        default=None,
        help="production acceptance: max final/initial flux residual ratio",
    )
    parser.add_argument(
        "--acceptance-max-final-clipped-fraction",
        type=float,
        default=None,
        help="production acceptance: max final clipped SPH bin fraction",
    )
    parser.add_argument(
        "--acceptance-max-final-clipped-count",
        type=int,
        default=None,
        help="production acceptance: max final clipped SPH bin count",
    )
    parser.add_argument(
        "--acceptance-sph-minimum-floor",
        type=float,
        default=None,
        help="production acceptance: minimum allowed final SPH factor",
    )
    parser.add_argument(
        "--acceptance-sph-maximum-ceiling",
        type=float,
        default=None,
        help="production acceptance: maximum allowed final SPH factor",
    )
    parser.add_argument(
        "--acceptance-max-keff-step-pcm",
        type=float,
        default=None,
        help="production acceptance: max absolute keff step across audit rows",
    )
    parser.add_argument(
        "--acceptance-max-final-keff-delta-pcm",
        type=float,
        default=None,
        help="production acceptance: max final-vs-previous keff delta",
    )
    parser.add_argument(
        "--fail-on-acceptance-violation",
        action="store_true",
        help="return an error after writing outputs if production acceptance fails",
    )


def sph_loop_acceptance_from_args(
    args: argparse.Namespace,
) -> dict[str, object] | None:
    acceptance: dict[str, object] = {}
    if args.acceptance_preset is not None:
        acceptance["preset"] = args.acceptance_preset
    optional_values = {
        "min_completed_iterations": args.acceptance_min_completed_iterations,
        "max_mgxs_default_volume_count": (
            args.acceptance_max_mgxs_default_volume_count
        ),
        "max_mgxs_missing_h_factor_count": (
            args.acceptance_max_mgxs_missing_h_factor_count
        ),
        "mesh_tolerance": args.acceptance_mesh_tolerance,
        "max_mgxs_scatter_row_balance_rel": (
            args.acceptance_max_mgxs_scatter_row_balance_rel
        ),
        "max_mgxs_chi_sum_error": args.acceptance_max_mgxs_chi_sum_error,
        "max_mgxs_transport_p1_rel": args.acceptance_max_mgxs_transport_p1_rel,
        "max_sph_rel_change": args.acceptance_max_sph_rel_change,
        "max_flux_ratio_residual": args.acceptance_max_flux_ratio_residual,
        "max_final_to_initial_flux_residual_ratio": (
            args.acceptance_max_final_to_initial_flux_residual_ratio
        ),
        "max_final_clipped_fraction": args.acceptance_max_final_clipped_fraction,
        "max_final_clipped_count": args.acceptance_max_final_clipped_count,
        "sph_minimum_floor": args.acceptance_sph_minimum_floor,
        "sph_maximum_ceiling": args.acceptance_sph_maximum_ceiling,
        "max_keff_step_pcm": args.acceptance_max_keff_step_pcm,
        "max_final_keff_delta_pcm": args.acceptance_max_final_keff_delta_pcm,
    }
    for key, value in optional_values.items():
        if value is not None:
            acceptance[key] = value
    if args.acceptance_require_final_solve:
        acceptance["require_final_solve"] = True
    if args.acceptance_require_converged:
        acceptance["require_converged"] = True
    if args.acceptance_require_mgxs_explicit_volumes:
        acceptance["require_mgxs_explicit_volumes"] = True
    if args.acceptance_require_mgxs_h_factor:
        acceptance["require_mgxs_h_factor"] = True
    if args.acceptance_require_mgxs_energy_bounds:
        acceptance["require_mgxs_energy_bounds"] = True
    if args.acceptance_require_known_mesh:
        acceptance["require_known_mesh"] = True
    if args.acceptance_require_mgxs_energy_bounds_consistency:
        acceptance["require_mgxs_energy_bounds_consistency"] = True
    if args.acceptance_require_mgxs_adf_face_consistency:
        acceptance["require_mgxs_adf_face_consistency"] = True
    if args.fail_on_acceptance_violation:
        acceptance["fail_on_violation"] = True
    return acceptance or None
