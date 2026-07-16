#!/usr/bin/env python3
"""Validate converter-facing OpenMC MGXS/ADF HDF5 input files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import h5py
import numpy as np

from .constants import MGXS_DONJON_GROUP_ORDER
from .energy_groups import (
    MESH_ABSOLUTE_TOLERANCE,
    MESH_RELATIVE_TOLERANCE,
    energy_bounds_sha256,
    identify_mesh,
    load_energy_bounds_text,
)
from .hdf5_names import read_mixture_names
from .mgxs_input_equivalence import (
    SPH_DATASETS,  # noqa: F401  (re-exported for mgxs_inspect)
    adf_names_for_group,
    attr_text,
    sph_present_for_group,
    validate_adf_layout,
    validate_sph_layout,
    validate_vector,
)
from .mgxs_input_report import (
    FAIL_DECISION,
    PASS_DECISION,
    InputReport,
    print_preflight_report,
    write_summary,
)
from .mgxs_physics_checks import (
    MgxsPhysicsCheckReport,
    evaluate_mgxs_physics,
)
from .production_policy import effective_production_thresholds
from .openmc_provenance import read_openmc_provenance_h5
from .mgxs_input_scatter import (
    configure_scatter_row_balance,
    validate_scatter,
)
from .mgxs_input_uncertainty import (
    UncertaintyConfig,
    configure_uncertainty,
    finalize_uncertainty,
    validate_uncertainty_for_calculation,
)

VALID_MULTICOMPO_EXTENSIONS = (".mco", ".mcompo.txt")
VALID_MACROLIB_EXTENSIONS = (".macrolib.txt",)
REQUIRED_DATASETS = ("total", "absorption", "fission", "nu_fission", "chi", "scatter_matrix")
OPTIONAL_VECTOR_DATASETS = (
    "transport_total",
    "inverse_velocity",
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)
H_FACTOR_DATASETS = (
    "h_factor",
    "H-FACTOR",
    "H_FACTOR",
    "kappa_fission",
    "kappa_fission_xs",
    "kappa_fission_cross_section",
)
def production_preflight_defaults(
    *,
    production: bool,
    require_mixture_order: bool = False,
    require_domain_mode: bool = False,
    require_source_domain_metadata: bool = False,
    require_openmc_provenance: bool = False,
    require_openmc_provenance_if_openmc: bool = False,
    require_openmc_volume_flux: bool = False,
    require_transport_dataset: bool,
    require_volume: bool,
    require_h_factor: bool,
    require_known_energy_mesh: bool = False,
    warn_unknown_energy_mesh: bool = False,
    energy_mesh_tolerance: float = MESH_RELATIVE_TOLERANCE,
    scatter_row_balance_warn: float | None,
    scatter_row_balance_fail: float | None,
    require_energy_bounds_consistency: bool = False,
    chi_sum_tolerance: float | None = None,
    require_adf_face_consistency: bool = False,
    transport_p1_fail: float | None = None,
    uncertainty_warn: float | None,
    uncertainty_fail: float | None,
    uncertainty_production_fail: float | None,
    uncertainty_mean_abs_floor: float,
    require_std_dev_coverage: bool = False,
) -> dict[str, Any]:
    """Return effective preflight options after applying the production preset."""
    if not production:
        return {
            "require_mixture_order": require_mixture_order,
            "require_domain_mode": require_domain_mode,
            "require_source_domain_metadata": require_source_domain_metadata,
            "require_openmc_provenance": require_openmc_provenance,
            "require_openmc_provenance_if_openmc": (
                require_openmc_provenance_if_openmc
            ),
            "require_openmc_volume_flux": require_openmc_volume_flux,
            "require_transport_dataset": require_transport_dataset,
            "require_volume": require_volume,
            "require_h_factor": require_h_factor,
            "require_known_energy_mesh": require_known_energy_mesh,
            "warn_unknown_energy_mesh": warn_unknown_energy_mesh,
            "energy_mesh_tolerance": energy_mesh_tolerance,
            "scatter_row_balance_warn": scatter_row_balance_warn,
            "scatter_row_balance_fail": scatter_row_balance_fail,
            "require_energy_bounds_consistency": require_energy_bounds_consistency,
            "chi_sum_tolerance": chi_sum_tolerance,
            "require_adf_face_consistency": require_adf_face_consistency,
            "transport_p1_fail": transport_p1_fail,
            "uncertainty_warn": uncertainty_warn,
            "uncertainty_fail": uncertainty_fail,
            "uncertainty_production_fail": uncertainty_production_fail,
            "uncertainty_mean_abs_floor": uncertainty_mean_abs_floor,
            "require_std_dev_coverage": require_std_dev_coverage,
        }

    thresholds = effective_production_thresholds(
        scatter_row_balance_fail=scatter_row_balance_fail,
        transport_p1_fail=transport_p1_fail,
        chi_sum_tolerance=chi_sum_tolerance,
        uncertainty_warn=uncertainty_warn,
        uncertainty_fail=uncertainty_fail,
        uncertainty_production_fail=uncertainty_production_fail,
        uncertainty_mean_abs_floor=uncertainty_mean_abs_floor,
    )

    return {
        "require_mixture_order": True,
        "require_domain_mode": True,
        "require_source_domain_metadata": True,
        # Production is source-aware: a generic handoff is not forced to
        # pretend it came from OpenMC, while every marked/embedded OpenMC input
        # must carry an intact frozen-reference binding. The explicit CLI flag
        # remains stricter and requires provenance on every input.
        "require_openmc_provenance": require_openmc_provenance,
        "require_openmc_provenance_if_openmc": True,
        "require_openmc_volume_flux": require_openmc_volume_flux,
        "require_transport_dataset": True,
        "require_volume": True,
        "require_h_factor": True,
        "require_known_energy_mesh": require_known_energy_mesh,
        "warn_unknown_energy_mesh": True,
        "energy_mesh_tolerance": energy_mesh_tolerance,
        "scatter_row_balance_warn": scatter_row_balance_warn,
        "scatter_row_balance_fail": thresholds["scatter_row_balance_fail"],
        "require_energy_bounds_consistency": True,
        "chi_sum_tolerance": thresholds["chi_sum_tolerance"],
        "require_adf_face_consistency": True,
        "transport_p1_fail": thresholds["transport_p1_fail"],
        "uncertainty_warn": thresholds["uncertainty_warn"],
        "uncertainty_fail": thresholds["uncertainty_fail"],
        "uncertainty_production_fail": thresholds[
            "uncertainty_production_fail"
        ],
        "uncertainty_mean_abs_floor": thresholds[
            "uncertainty_mean_abs_floor"
        ],
        "require_std_dev_coverage": True,
    }


def main() -> int:
    args = parse_args()
    if args.production and args.no_uncertainty_check:
        sys.stderr.write(
            "mgxs_input_contract: error: --production cannot be combined with "
            "--no-uncertainty-check; the canonical production policy requires "
            "uncertainty checks and complete std-dev coverage\n"
        )
        return 1
    expected_faces = split_csv(args.expected_adf_faces)
    settings = production_preflight_defaults(
        production=args.production,
        require_mixture_order=args.require_mixture_order,
        require_domain_mode=args.require_domain_mode,
        require_source_domain_metadata=args.require_source_domain_metadata,
        require_openmc_provenance=args.require_openmc_provenance,
        require_openmc_volume_flux=args.require_openmc_volume_flux,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        require_h_factor=args.require_h_factor,
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
    )
    reports = [
        validate_input(
            path,
            require_adf=args.require_adf,
            require_sph=args.require_sph,
            require_mixture_order=settings["require_mixture_order"],
            require_domain_mode=settings["require_domain_mode"],
            require_source_domain_metadata=settings["require_source_domain_metadata"],
            require_openmc_provenance=settings["require_openmc_provenance"],
            require_openmc_provenance_if_openmc=settings[
                "require_openmc_provenance_if_openmc"
            ],
            require_openmc_volume_flux=settings["require_openmc_volume_flux"],
            require_transport_dataset=settings["require_transport_dataset"],
            require_volume=settings["require_volume"],
            require_h_factor=settings["require_h_factor"],
            expected_energy_group_structure=args.expected_energy_group_structure,
            expected_energy_bounds=(
                None
                if args.expected_energy_bounds is None
                else load_energy_bounds_text(args.expected_energy_bounds)
            ),
            expected_energy_bounds_label=(
                None
                if args.expected_energy_bounds is None
                else str(args.expected_energy_bounds)
            ),
            expected_energy_bounds_sha256=args.expected_energy_bounds_sha256,
            require_known_energy_mesh=settings["require_known_energy_mesh"],
            warn_unknown_energy_mesh=settings["warn_unknown_energy_mesh"],
            energy_mesh_tolerance=settings["energy_mesh_tolerance"],
            expected_adf_faces=expected_faces,
            scatter_row_balance_warn=settings["scatter_row_balance_warn"],
            scatter_row_balance_fail=settings["scatter_row_balance_fail"],
            require_energy_bounds_consistency=settings[
                "require_energy_bounds_consistency"
            ],
            chi_sum_tolerance=settings["chi_sum_tolerance"],
            require_adf_face_consistency=settings["require_adf_face_consistency"],
            transport_p1_fail=settings["transport_p1_fail"],
            uncertainty=UncertaintyConfig(
                warn_threshold=settings["uncertainty_warn"],
                fail_threshold=settings["uncertainty_fail"],
                production_fail_threshold=settings["uncertainty_production_fail"],
                mean_abs_floor=settings["uncertainty_mean_abs_floor"],
                require_coverage=settings["require_std_dev_coverage"],
            ),
        )
        for path in args.input_h5
    ]

    output_issue = output_name_issue(args.output, args.format)
    ok = all(report.ok for report in reports) and output_issue is None
    decision = PASS_DECISION if ok else FAIL_DECISION

    print_preflight_report(
        reports,
        decision=decision,
        output_path=args.output,
        output_issue=output_issue,
    )

    if args.summary_json:
        write_summary(args.summary_json, reports, decision, output_issue)

    return 0 if ok or not (args.check or args.production) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
            "enable production preflight defaults: require volume, transport_total, "
            "fissionable H-FACTOR, declared mixture order, domain provenance, "
            "OpenMC fine-reference binding, physics consistency gates, and "
            "production uncertainty failure threshold"
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
        "--require-openmc-provenance",
        action="store_true",
        help=(
            "for OpenMC-source handoffs, require a verified recipe/statepoint "
            "reference binding; implied by --production"
        ),
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
        help="require /attrs energy_group_structure to match this label",
    )
    parser.add_argument(
        "--expected-energy-bounds",
        type=Path,
        default=None,
        help="text file containing expected ascending energy bounds in eV",
    )
    parser.add_argument(
        "--expected-energy-bounds-sha256",
        default=None,
        help="require the actual /energy_bounds SHA-256 digest to match this value",
    )
    parser.add_argument(
        "--require-known-energy-mesh",
        action="store_true",
        help=(
            "fail if /energy_bounds does not match a bundled known group "
            "structure"
        ),
    )
    parser.add_argument(
        "--warn-unknown-energy-mesh",
        action="store_true",
        help=(
            "warn if /energy_bounds does not match a bundled known group "
            "structure"
        ),
    )
    parser.add_argument(
        "--energy-mesh-tolerance",
        type=float,
        default=MESH_RELATIVE_TOLERANCE,
        metavar="RTOL",
        help=(
            "relative tolerance for bundled energy-mesh identification "
            f"(default: {MESH_RELATIVE_TOLERANCE:g})"
        ),
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
        help=(
            "require any local mixture/state energy_bounds dataset to match "
            "global /energy_bounds"
        ),
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
        help="require all ADF-bearing calculations to declare the same face names",
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
        "--check",
        action="store_true",
        help="return non-zero if any input violates the production contract",
    )
    return parser.parse_args()


def validate_input(
    path: Path,
    *,
    require_adf: bool = False,
    require_sph: bool = False,
    require_mixture_order: bool = False,
    require_domain_mode: bool = False,
    require_source_domain_metadata: bool = False,
    require_openmc_provenance: bool = False,
    require_openmc_provenance_if_openmc: bool = False,
    require_openmc_volume_flux: bool = False,
    require_transport_dataset: bool = False,
    require_volume: bool = False,
    require_h_factor: bool = False,
    expected_energy_group_structure: str | None = None,
    expected_energy_bounds: np.ndarray | list[float] | None = None,
    expected_energy_bounds_label: str | None = None,
    expected_energy_bounds_sha256: str | None = None,
    require_known_energy_mesh: bool = False,
    warn_unknown_energy_mesh: bool = False,
    energy_mesh_tolerance: float = MESH_RELATIVE_TOLERANCE,
    expected_adf_faces: list[str] | None = None,
    scatter_row_balance_warn: float | None = None,
    scatter_row_balance_fail: float | None = None,
    require_energy_bounds_consistency: bool = False,
    chi_sum_tolerance: float | None = None,
    require_adf_face_consistency: bool = False,
    transport_p1_fail: float | None = None,
    uncertainty: UncertaintyConfig | None = None,
) -> InputReport:
    report = InputReport(path=str(path))
    report.chi_sum_tolerance = chi_sum_tolerance
    report.transport_p1_fail_threshold = transport_p1_fail
    configure_scatter_row_balance(
        report,
        warn_threshold=scatter_row_balance_warn,
        fail_threshold=scatter_row_balance_fail,
    )
    configure_uncertainty(report, uncertainty or UncertaintyConfig())
    if not path.is_file():
        report.fail(f"input file does not exist: {path}")
        return report

    try:
        with h5py.File(path, "r") as h5:
            validate_open_h5(
                h5,
                report,
                require_adf=require_adf,
                require_sph=require_sph,
                require_mixture_order=require_mixture_order,
                require_domain_mode=require_domain_mode,
                require_source_domain_metadata=require_source_domain_metadata,
                require_openmc_provenance=require_openmc_provenance,
                require_openmc_provenance_if_openmc=(
                    require_openmc_provenance_if_openmc
                ),
                require_openmc_volume_flux=require_openmc_volume_flux,
                require_transport_dataset=require_transport_dataset,
                require_volume=require_volume,
                require_h_factor=require_h_factor,
                expected_energy_group_structure=expected_energy_group_structure,
                expected_energy_bounds=expected_energy_bounds,
                expected_energy_bounds_label=expected_energy_bounds_label,
                expected_energy_bounds_sha256=expected_energy_bounds_sha256,
                require_known_energy_mesh=require_known_energy_mesh,
                warn_unknown_energy_mesh=warn_unknown_energy_mesh,
                energy_mesh_tolerance=energy_mesh_tolerance,
                expected_adf_faces=expected_adf_faces,
                scatter_row_balance_warn=scatter_row_balance_warn,
                scatter_row_balance_fail=scatter_row_balance_fail,
                require_energy_bounds_consistency=require_energy_bounds_consistency,
                chi_sum_tolerance=chi_sum_tolerance,
                require_adf_face_consistency=require_adf_face_consistency,
                transport_p1_fail=transport_p1_fail,
                uncertainty=uncertainty or UncertaintyConfig(),
            )
    except OSError as exc:
        report.fail(f"cannot open HDF5 file: {exc}")
    except (ValueError, TypeError) as exc:
        report.fail(f"cannot interpret HDF5 dataset values: {exc}")
    return report


def validate_open_h5(
    h5: h5py.File,
    report: InputReport,
    *,
    require_adf: bool,
    require_sph: bool,
    require_mixture_order: bool,
    require_domain_mode: bool,
    require_source_domain_metadata: bool,
    require_openmc_provenance: bool,
    require_openmc_provenance_if_openmc: bool,
    require_openmc_volume_flux: bool,
    require_transport_dataset: bool,
    require_volume: bool,
    require_h_factor: bool,
    expected_energy_group_structure: str | None,
    expected_energy_bounds: np.ndarray | list[float] | None,
    expected_energy_bounds_label: str | None,
    expected_energy_bounds_sha256: str | None,
    require_known_energy_mesh: bool,
    warn_unknown_energy_mesh: bool,
    energy_mesh_tolerance: float,
    expected_adf_faces: list[str] | None,
    scatter_row_balance_warn: float | None,
    scatter_row_balance_fail: float | None,
    require_energy_bounds_consistency: bool,
    chi_sum_tolerance: float | None,
    require_adf_face_consistency: bool,
    transport_p1_fail: float | None,
    uncertainty: UncertaintyConfig,
) -> None:
    ngroups = integer_attr(h5.attrs, "energy_groups")
    legendre_order = integer_attr(h5.attrs, "legendre_order")
    report.energy_groups = ngroups
    report.legendre_order = legendre_order
    report.sph_applied = bool(h5.attrs.get("sph_applied", False))
    report.sph_applied_source = (
        attr_text(h5.attrs["sph_applied_source"])
        if "sph_applied_source" in h5.attrs
        else None
    )
    report.sph_apply_operator = (
        attr_text(h5.attrs["sph_apply_operator"])
        if "sph_apply_operator" in h5.attrs
        else None
    )
    report.sph_kind = (
        attr_text(h5.attrs["sph_kind"])
        if "sph_kind" in h5.attrs
        else None
    )
    validate_openmc_provenance(
        h5,
        report,
        require_complete=require_openmc_provenance,
        require_if_openmc=require_openmc_provenance_if_openmc,
    )

    if ngroups is None or ngroups <= 0:
        report.fail("/attrs energy_groups must be a positive integer")
        return
    if legendre_order is None or legendre_order < 0:
        report.fail("/attrs legendre_order must be a non-negative integer")
        return

    if "energy_bounds" not in h5:
        report.fail("/energy_bounds dataset is missing")
        return
    energy = np.asarray(h5["energy_bounds"][:], dtype=float).reshape(-1)
    if energy.shape != (ngroups + 1,):
        report.fail(f"/energy_bounds must have shape ({ngroups + 1},), got {energy.shape}")
    elif not np.all(np.isfinite(energy)):
        report.fail("/energy_bounds contains non-finite values")
    elif np.any(energy <= 0.0):
        report.fail("/energy_bounds must be positive eV values")
    elif not np.all(np.diff(energy) > 0.0):
        report.fail("/energy_bounds must be strictly ascending")
    validate_energy_identity(
        h5,
        report,
        energy,
        expected_structure=expected_energy_group_structure,
        expected_bounds=expected_energy_bounds,
        expected_bounds_label=expected_energy_bounds_label,
        expected_bounds_sha256=expected_energy_bounds_sha256,
        require_known_mesh=require_known_energy_mesh,
        warn_unknown_mesh=warn_unknown_energy_mesh,
        mesh_tolerance=energy_mesh_tolerance,
    )
    validate_domain_mode(h5, report, require_domain_mode=require_domain_mode)

    if "mixtures" not in h5 or not isinstance(h5["mixtures"], h5py.Group):
        report.fail("/mixtures group is missing")
        return
    mixtures = h5["mixtures"]
    try:
        mixture_names = read_mixture_names(h5)
    except ValueError as exc:
        report.fail(str(exc))
        return
    report.mixtures = len(mixture_names)
    if report.mixtures == 0:
        report.fail("/mixtures group contains no mixtures")
        return
    validate_mixture_order_contract(
        h5,
        mixtures,
        mixture_names,
        report,
        require_mixture_order=require_mixture_order,
        require_source_domain_metadata=require_source_domain_metadata,
    )
    validate_openmc_volume_flux(
        h5,
        mixture_names,
        ngroups,
        report,
        require_openmc_volume_flux=require_openmc_volume_flux,
        uncertainty=uncertainty,
    )

    burnup_axis = burnup_axis_from_hdf5(h5, report)
    adf_names_by_mix: list[tuple[str, ...]] = []
    sph_present_by_calc: list[bool] = []
    state_counts: list[int] = []
    for name in mixture_names:
        group = mixtures[name]
        if not isinstance(group, h5py.Group):
            report.fail(f"/mixtures/{name} must be an HDF5 group")
            continue
        state_counts.append(
            validate_mixture(
                h5,
                group,
                str(name),
                ngroups,
                legendre_order,
                report,
                adf_names_by_mix,
                sph_present_by_calc,
                require_transport_dataset=require_transport_dataset,
                require_volume=require_volume,
                require_h_factor=require_h_factor,
                uncertainty=uncertainty,
            )
        )

    physics = evaluate_mgxs_physics(
        h5,
        mixture_names=mixture_names,
        energy_groups=ngroups,
        legendre_order=legendre_order,
        root_energy_bounds=_valid_root_energy_bounds(energy, ngroups),
        energy_bounds_consistency=require_energy_bounds_consistency,
        scatter_row_balance_rel=scatter_row_balance_fail,
        scatter_row_balance_warn_rel=scatter_row_balance_warn,
        chi_sum_tolerance=chi_sum_tolerance,
        require_adf_face_consistency=require_adf_face_consistency,
        transport_p1_rel=transport_p1_fail,
    )
    apply_shared_physics_checks(report, physics)

    validate_state_layout(report, state_counts, burnup_axis)

    validate_adf_layout(report, adf_names_by_mix, require_adf, expected_adf_faces)
    validate_sph_layout(report, sph_present_by_calc, require_sph)
    finalize_volume_contract(report, require_volume=bool(require_volume))
    finalize_uncertainty(report)


def _valid_root_energy_bounds(energy: np.ndarray, ngroups: int) -> np.ndarray | None:
    if energy.shape != (ngroups + 1,):
        return None
    if not np.all(np.isfinite(energy)):
        return None
    if np.any(energy <= 0.0):
        return None
    if not np.all(np.diff(energy) > 0.0):
        return None
    return energy


def apply_shared_physics_checks(
    report: InputReport,
    physics: MgxsPhysicsCheckReport,
) -> None:
    report.energy_bounds_local_count = physics.energy_bounds_local_count
    for issue in physics.energy_bounds_consistency_errors:
        report.fail(issue)
    report.scatter_row_balance_max_rel = physics.scatter_row_balance_max_rel
    report.scatter_row_balance_max_abs = physics.scatter_row_balance_max_abs
    report.scatter_row_balance_worst = physics.scatter_row_balance_worst
    for warning in physics.scatter_row_balance_warnings:
        report.warn(warning)
    for issue in physics.scatter_row_balance_errors:
        report.fail(issue)
    report.chi_checked = physics.chi_checked
    report.chi_sum_max_abs_error = physics.chi_sum_max_abs_error
    report.chi_sum_worst = physics.chi_sum_worst
    for issue in physics.chi_errors:
        report.fail(issue)
    report.nu_ratio_checked_bins = physics.nu_ratio_checked_bins
    report.nu_ratio_min = physics.nu_ratio_min
    report.nu_ratio_max = physics.nu_ratio_max
    report.nu_ratio_worst = physics.nu_ratio_worst
    report.nu_ratio_warning_count = physics.nu_ratio_warning_count
    for warning in physics.nu_ratio_warnings:
        report.warn(warning)
    report.adf_face_consistency_checked = bool(
        physics.adf_calculations or physics.adf_face_errors
    )
    report.adf_face_consistency_errors = len(physics.adf_face_errors)
    for issue in physics.adf_face_errors:
        report.fail(issue)
    report.transport_p1_checked = physics.transport_p1_checked
    report.transport_p1_max_rel = physics.transport_p1_max_rel
    report.transport_p1_max_abs = physics.transport_p1_max_abs
    report.transport_p1_worst = physics.transport_p1_worst
    for issue in physics.transport_p1_errors:
        report.fail(issue)


def finalize_volume_contract(report: InputReport, *, require_volume: bool) -> None:
    if report.volume_defaulted == 0 or require_volume:
        return
    calculation_count = report.calculations or report.mixtures
    report.warn(
        f"{report.volume_defaulted}/{calculation_count} calculation(s) are missing "
        "volume; converter readers will use default volume 1.0 for those "
        "calculations"
    )


def validate_mixture_order_contract(
    h5: h5py.File,
    mixtures: h5py.Group,
    mixture_names: tuple[str, ...],
    report: InputReport,
    *,
    require_mixture_order: bool,
    require_source_domain_metadata: bool,
) -> None:
    report.declared_mixture_order = "mixture_names" in h5
    if require_mixture_order and not report.declared_mixture_order:
        report.fail(
            "/mixture_names dataset is required to declare DONJON mixture order"
        )

    for expected_index, name in enumerate(mixture_names, start=1):
        group = mixtures[name]
        if not isinstance(group, h5py.Group):
            continue
        validate_source_domain_metadata(
            group,
            str(name),
            report,
            require_source_domain_metadata=require_source_domain_metadata,
        )
        if "source_domain_index" not in group.attrs:
            if require_mixture_order:
                report.fail(
                    f"mixture {name}: source_domain_index attribute is required"
                )
            continue
        try:
            source_domain_index = int(group.attrs["source_domain_index"])
        except (TypeError, ValueError):
            report.fail(
                f"mixture {name}: source_domain_index attribute must be an integer"
            )
            continue
        report.source_domain_indices += 1
        if source_domain_index <= 0:
            report.fail(
                f"mixture {name}: source_domain_index attribute must be positive"
            )
        elif (
            require_mixture_order or report.declared_mixture_order
        ) and source_domain_index != expected_index:
            report.fail(
                f"mixture {name}: source_domain_index {source_domain_index} "
                f"does not match declared mixture order position {expected_index}"
            )


def validate_domain_mode(
    h5: h5py.File,
    report: InputReport,
    *,
    require_domain_mode: bool,
) -> None:
    if "domain_mode" not in h5.attrs:
        if require_domain_mode:
            report.fail("/attrs domain_mode is required for production handoff provenance")
        return
    domain_mode = attr_text(h5.attrs["domain_mode"]).strip()
    report.domain_mode = domain_mode or None
    if require_domain_mode and not domain_mode:
        report.fail("/attrs domain_mode must be a non-empty string")


def validate_openmc_provenance(
    h5: h5py.File,
    report: InputReport,
    *,
    require_complete: bool,
    require_if_openmc: bool,
) -> None:
    """Validate the embedded fine-reference identity without reopening OpenMC.

    Production conversion requires an immutable reference binding (recipe and
    loaded statepoint hashes plus a valid embedded record). Full transport
    replayability remains visible as a stricter academic capability and is not
    made a native-SPH runtime dependency.
    """

    provenance = read_openmc_provenance_h5(h5)
    if provenance is None:
        if require_complete:
            report.fail(
                "OpenMC provenance was explicitly required, but the input has no "
                "embedded OpenMC provenance record"
            )
        return
    report.openmc_provenance = provenance
    report.openmc_provenance_status = str(provenance.get("status") or "legacy")
    is_legacy = report.openmc_provenance_status == "legacy"
    capabilities = provenance.get("capabilities")
    integrity = provenance.get("integrity")
    integrity_ok = bool(
        integrity.get("ok", False) if isinstance(integrity, dict) else False
    )
    reference_bound = bool(
        capabilities.get("reference_bound", False)
        if isinstance(capabilities, dict)
        else False
    )
    transport_reproducible = bool(
        capabilities.get("transport_reproducible", False)
        if isinstance(capabilities, dict)
        else False
    )
    if not integrity_ok and not is_legacy:
        report.fail("embedded OpenMC provenance integrity check failed")
    if (require_complete or require_if_openmc) and (
        not reference_bound or not integrity_ok
    ):
        report.fail(
            "OpenMC source provenance is not reference-bound; production needs "
            "verified recipe and loaded-statepoint content hashes plus an intact "
            "embedded provenance digest"
        )
    if not transport_reproducible:
        missing = provenance.get("missing")
        count = len(missing) if isinstance(missing, list) else 0
        report.warn(
            "OpenMC transport replay provenance is incomplete"
            + (f" ({count} missing field(s))" if count else "")
        )


def validate_source_domain_metadata(
    group: h5py.Group,
    name: str,
    report: InputReport,
    *,
    require_source_domain_metadata: bool,
) -> None:
    has_id = "source_domain_id" in group.attrs
    has_type = "source_domain_type" in group.attrs
    if has_id and has_type:
        report.source_domain_metadata += 1

    if require_source_domain_metadata and not has_id:
        report.fail(f"mixture {name}: source_domain_id attribute is required")
    if require_source_domain_metadata and not has_type:
        report.fail(f"mixture {name}: source_domain_type attribute is required")

    if has_id:
        try:
            int(group.attrs["source_domain_id"])
        except (TypeError, ValueError):
            report.fail(f"mixture {name}: source_domain_id attribute must be an integer")
    if has_type and not attr_text(group.attrs["source_domain_type"]).strip():
        report.fail(f"mixture {name}: source_domain_type attribute must be non-empty")


def validate_openmc_volume_flux(
    h5: h5py.File,
    mixture_names: tuple[str, ...],
    ngroups: int,
    report: InputReport,
    *,
    require_openmc_volume_flux: bool,
    uncertainty: UncertaintyConfig,
) -> None:
    if "openmc_volume_flux" not in h5:
        if require_openmc_volume_flux:
            report.fail("/openmc_volume_flux dataset is required")
        return

    obj = h5["openmc_volume_flux"]
    report.openmc_volume_flux_present = True
    if not isinstance(obj, h5py.Dataset):
        report.fail("/openmc_volume_flux must be an HDF5 dataset")
        return

    report.openmc_volume_flux_shape = tuple(int(value) for value in obj.shape)
    expected_shape = (len(mixture_names), ngroups)
    if report.openmc_volume_flux_shape != expected_shape:
        report.fail(
            "/openmc_volume_flux shape must match (mixture, group): "
            f"{report.openmc_volume_flux_shape} != {expected_shape}"
        )
    else:
        values = np.asarray(obj[:], dtype=float)
        if not np.all(np.isfinite(values)):
            report.fail("/openmc_volume_flux contains non-finite values")
        if np.any(values <= 0.0):
            report.fail("/openmc_volume_flux values must be positive")

    group_order = (
        attr_text(obj.attrs["group_order"]) if "group_order" in obj.attrs else None
    )
    report.openmc_volume_flux_group_order = group_order
    if group_order != MGXS_DONJON_GROUP_ORDER:
        report.fail(
            "/openmc_volume_flux attrs group_order must be "
            f"{MGXS_DONJON_GROUP_ORDER!r}, got {group_order!r}"
        )

    if "source_group_order" in obj.attrs:
        report.openmc_volume_flux_source_group_order = attr_text(
            obj.attrs["source_group_order"]
        )

    if "mixture_names" not in obj.attrs:
        report.fail("/openmc_volume_flux attrs mixture_names is required")
        return
    declared = names_from_hdf5_value(obj.attrs["mixture_names"])
    report.openmc_volume_flux_mixture_names = len(declared)
    if declared != mixture_names:
        report.fail(
            "/openmc_volume_flux attrs mixture_names must match /mixture_names: "
            f"{declared!r} != {mixture_names!r}"
        )

    validate_openmc_volume_flux_std_dev(
        h5,
        obj,
        mixture_names,
        expected_shape,
        report,
        uncertainty=uncertainty,
    )


def validate_openmc_volume_flux_std_dev(
    h5: h5py.File,
    mean: h5py.Dataset,
    mixture_names: tuple[str, ...],
    expected_shape: tuple[int, int],
    report: InputReport,
    *,
    uncertainty: UncertaintyConfig,
) -> None:
    name = "openmc_volume_flux_std_dev"
    if name not in h5:
        return

    obj = h5[name]
    report.openmc_volume_flux_std_dev_present = True
    if not isinstance(obj, h5py.Dataset):
        report.fail("/openmc_volume_flux_std_dev must be an HDF5 dataset")
        return

    report.openmc_volume_flux_std_dev_shape = tuple(int(value) for value in obj.shape)
    if report.openmc_volume_flux_std_dev_shape != expected_shape:
        report.fail(
            "/openmc_volume_flux_std_dev shape must match (mixture, group): "
            f"{report.openmc_volume_flux_std_dev_shape} != {expected_shape}"
        )
        return

    values = np.asarray(obj[:], dtype=float)
    if not np.all(np.isfinite(values)):
        report.fail("/openmc_volume_flux_std_dev contains non-finite values")
        return
    if np.any(values < 0.0):
        report.fail("/openmc_volume_flux_std_dev values must be non-negative")
        return

    group_order = (
        attr_text(obj.attrs["group_order"]) if "group_order" in obj.attrs else None
    )
    if group_order != MGXS_DONJON_GROUP_ORDER:
        report.fail(
            "/openmc_volume_flux_std_dev attrs group_order must be "
            f"{MGXS_DONJON_GROUP_ORDER!r}, got {group_order!r}"
        )
    if "mixture_names" not in obj.attrs:
        report.fail("/openmc_volume_flux_std_dev attrs mixture_names is required")
    else:
        declared = names_from_hdf5_value(obj.attrs["mixture_names"])
        if declared != mixture_names:
            report.fail(
                "/openmc_volume_flux_std_dev attrs mixture_names must match "
                f"/mixture_names: {declared!r} != {mixture_names!r}"
            )

    if mean.shape != expected_shape:
        return
    mean_values = np.asarray(mean[:], dtype=float)
    if not np.all(np.isfinite(mean_values)):
        return
    mask = np.abs(mean_values) > uncertainty.mean_abs_floor
    if not np.any(mask):
        return
    rel = np.zeros_like(mean_values, dtype=float)
    rel[mask] = values[mask] / np.abs(mean_values[mask])
    index = tuple(
        int(value) for value in np.unravel_index(int(np.argmax(rel)), rel.shape)
    )
    max_rel = float(rel[index])
    report.openmc_volume_flux_std_dev_max_rel = max_rel
    report.openmc_volume_flux_std_dev_worst = (
        f"{mixture_names[index[0]]}: openmc_volume_flux g={index[1] + 1} "
        f"mean={mean_values[index]:.6e} std_dev={values[index]:.6e} "
        f"rel={max_rel:.6e}"
    )
    _apply_openmc_volume_flux_uncertainty_threshold(
        report,
        max_rel,
        uncertainty=uncertainty,
    )


def _apply_openmc_volume_flux_uncertainty_threshold(
    report: InputReport,
    max_rel: float,
    *,
    uncertainty: UncertaintyConfig,
) -> None:
    detail = (
        "OpenMC volume-flux statistical uncertainty max relative sigma "
        f"{max_rel:.6e} at {report.openmc_volume_flux_std_dev_worst}"
    )
    if (
        uncertainty.production_fail_threshold is not None
        and max_rel > uncertainty.production_fail_threshold
    ):
        report.fail(
            f"{detail} exceeds production fail threshold "
            f"{uncertainty.production_fail_threshold:.6e}"
        )
    elif uncertainty.fail_threshold is not None and max_rel > uncertainty.fail_threshold:
        report.fail(
            f"{detail} exceeds fail threshold {uncertainty.fail_threshold:.6e}"
        )
    elif uncertainty.warn_threshold is not None and max_rel > uncertainty.warn_threshold:
        report.warn(
            f"{detail} exceeds warn threshold {uncertainty.warn_threshold:.6e}"
        )


def validate_energy_identity(
    h5: h5py.File,
    report: InputReport,
    energy: np.ndarray,
    *,
    expected_structure: str | None,
    expected_bounds: np.ndarray | list[float] | None,
    expected_bounds_label: str | None,
    expected_bounds_sha256: str | None,
    require_known_mesh: bool,
    warn_unknown_mesh: bool,
    mesh_tolerance: float,
) -> None:
    structure = (
        attr_text(h5.attrs["energy_group_structure"])
        if "energy_group_structure" in h5.attrs
        else None
    )
    report.energy_group_structure = structure
    digest = energy_bounds_sha256(energy)
    report.energy_bounds_sha256 = digest

    declared_digest = (
        attr_text(h5.attrs["energy_bounds_sha256"])
        if "energy_bounds_sha256" in h5.attrs
        else None
    )
    if declared_digest is not None and declared_digest != digest:
        report.fail(
            "/attrs energy_bounds_sha256 does not match /energy_bounds: "
            f"{declared_digest} != {digest}"
        )

    if expected_structure is not None:
        if structure is None:
            report.fail(
                "/attrs energy_group_structure is missing; expected "
                f"{expected_structure!r}"
            )
        elif structure != expected_structure:
            report.fail(
                "/attrs energy_group_structure mismatch: "
                f"{structure!r} != {expected_structure!r}"
            )

    if expected_bounds_sha256 is not None and digest != expected_bounds_sha256:
        report.fail(
            "/energy_bounds SHA-256 mismatch: "
            f"{digest} != {expected_bounds_sha256}"
        )

    if expected_bounds is not None:
        expected = np.asarray(expected_bounds, dtype=float).reshape(-1)
        label = expected_bounds_label or "expected energy bounds"
        if expected.shape != energy.shape:
            report.fail(
                f"/energy_bounds shape does not match {label}: "
                f"{energy.shape} != {expected.shape}"
            )
        elif not np.allclose(energy, expected, rtol=1.0e-10, atol=0.0):
            index = int(np.argmax(np.abs(energy - expected)))
            report.fail(
                f"/energy_bounds differ from {label}: index {index} "
                f"actual={energy[index]:.12e} expected={expected[index]:.12e}"
            )

    report.energy_mesh_tolerance = float(mesh_tolerance)
    if not _mesh_identification_candidate(energy):
        return
    mesh = identify_mesh(
        energy,
        rtol=float(mesh_tolerance),
        atol=MESH_ABSOLUTE_TOLERANCE,
    )
    if mesh is not None:
        report.energy_mesh_id = mesh.mesh_id
        report.energy_mesh_name = mesh.name
        return

    message = (
        "/energy_bounds did not match a bundled known energy mesh "
        f"within rtol={float(mesh_tolerance):g}"
    )
    if require_known_mesh:
        report.fail(message.replace("did not match", "does not match"))
    elif warn_unknown_mesh:
        report.warn(message)


def _mesh_identification_candidate(energy: np.ndarray) -> bool:
    return (
        energy.ndim == 1
        and energy.size >= 2
        and np.all(np.isfinite(energy))
        and np.all(energy > 0.0)
        and np.all(np.diff(energy) > 0.0)
    )


def burnup_axis_from_hdf5(h5: h5py.File, report: InputReport) -> np.ndarray | None:
    paths: list[str] = []
    if "state_points" in h5:
        state_points = h5["state_points"]
        if not isinstance(state_points, h5py.Group):
            report.fail("/state_points must be an HDF5 group")
            return None
        unsupported = [
            str(name)
            for name in state_points
            if str(name).lower() not in {"burn", "burnup"}
        ]
        if unsupported:
            report.fail(
                "unsupported /state_points axis/axes: "
                f"{', '.join(unsupported)}; only BURN is supported"
            )
        paths.extend(
            f"state_points/{name}"
            for name in state_points
            if str(name).lower() in {"burn", "burnup"}
        )
    paths.extend(path for path in ("burnup_values", "burnup") if path in h5)
    attrs = [attr for attr in ("burnup_values", "burnup") if attr in h5.attrs]

    if len(paths) + len(attrs) > 1:
        labels = [f"/{path}" for path in paths] + [f"/attrs/{attr}" for attr in attrs]
        report.fail(f"multiple BURN axis definitions found: {', '.join(labels)}")
        return None

    if paths:
        obj = h5[paths[0]]
        if not isinstance(obj, h5py.Dataset):
            report.fail(f"/{paths[0]} must be a dataset")
            return None
        values = np.asarray(obj[:], dtype=float).reshape(-1)
        validate_burnup_axis(values, report, f"/{paths[0]}")
        return values

    if attrs:
        values = np.asarray(h5.attrs[attrs[0]], dtype=float).reshape(-1)
        validate_burnup_axis(values, report, f"/attrs/{attrs[0]}")
        return values
    return None


def validate_burnup_axis(
    values: np.ndarray,
    report: InputReport,
    label: str,
) -> None:
    report.burnup_axis_path = label
    report.burnup_axis_values = int(values.size)
    if values.size == 0:
        report.fail(f"{label} BURN axis must contain at least one value")
        return
    if not np.all(np.isfinite(values)):
        report.fail(f"{label} BURN axis contains non-finite values")
    if values.size > 1 and not np.all(np.diff(values) > 0.0):
        report.fail(f"{label} BURN axis must be strictly increasing")


def validate_state_layout(
    report: InputReport,
    state_counts: list[int],
    burnup_axis: np.ndarray | None,
) -> None:
    positive_counts = [count for count in state_counts if count > 0]
    if not positive_counts:
        return

    first = positive_counts[0]
    report.state_points = first
    if any(count != first for count in positive_counts):
        report.fail(
            "all mixtures must contain the same number of state points; got "
            f"{state_counts}"
        )
        return

    if first > 1:
        if burnup_axis is None:
            report.fail("multi-state HDF5 requires a BURN axis")
        elif burnup_axis.size != first:
            report.fail(
                f"BURN axis length must match number of states: "
                f"{burnup_axis.size} != {first}"
            )
    elif burnup_axis is not None:
        report.warn(
            "BURN axis is present on a one-state input; pass --burnup during "
            "conversion if single-point BURN metadata is desired"
        )
    if report.stateful_mixtures and first == 1:
        report.warn("states/ layout contains a single point and will convert as one-state")


def validate_mixture(
    h5: h5py.File,
    group: h5py.Group,
    name: str,
    ngroups: int,
    legendre_order: int,
    report: InputReport,
    adf_names_by_mix: list[tuple[str, ...]],
    sph_present_by_calc: list[bool],
    *,
    require_transport_dataset: bool,
    require_volume: bool,
    require_h_factor: bool,
    uncertainty: UncertaintyConfig,
) -> int:
    if "states" in group:
        return validate_mixture_states(
            h5,
            group,
            name,
            ngroups,
            legendre_order,
            report,
            adf_names_by_mix,
            sph_present_by_calc,
            require_transport_dataset=require_transport_dataset,
            require_volume=require_volume,
            require_h_factor=require_h_factor,
            uncertainty=uncertainty,
        )

    validate_calculation(
        h5,
        group,
        name,
        ngroups,
        legendre_order,
        report,
        adf_names_by_mix,
        sph_present_by_calc,
        parent_group=None,
        count_fissionable=True,
        require_transport_dataset=require_transport_dataset,
        require_volume=require_volume,
        require_h_factor=require_h_factor,
        uncertainty=uncertainty,
    )
    report.calculations += 1
    return 1


def validate_mixture_states(
    h5: h5py.File,
    mixture_group: h5py.Group,
    name: str,
    ngroups: int,
    legendre_order: int,
    report: InputReport,
    adf_names_by_mix: list[tuple[str, ...]],
    sph_present_by_calc: list[bool],
    *,
    require_transport_dataset: bool,
    require_volume: bool,
    require_h_factor: bool,
    uncertainty: UncertaintyConfig,
) -> int:
    states = mixture_group["states"]
    if not isinstance(states, h5py.Group):
        report.fail(f"mixture {name}: states must be an HDF5 group")
        return 0
    state_names = sorted_state_names(states)
    if not state_names:
        report.fail(f"mixture {name}: states group contains no state points")
        return 0

    report.stateful_mixtures += 1
    report.calculations += len(state_names)
    if any(field in mixture_group for field in REQUIRED_DATASETS):
        report.warn(
            f"mixture {name}: direct XS datasets are ignored because states/ is present"
        )

    for index, state_name in enumerate(state_names):
        state_group = states[state_name]
        label = f"{name}/states/{state_name}"
        if not isinstance(state_group, h5py.Group):
            report.fail(f"mixture {label}: state point must be an HDF5 group")
            continue
        validate_calculation(
            h5,
            state_group,
            label,
            ngroups,
            legendre_order,
            report,
            adf_names_by_mix,
            sph_present_by_calc,
            parent_group=mixture_group,
            count_fissionable=index == 0,
            require_transport_dataset=require_transport_dataset,
            require_volume=require_volume,
            require_h_factor=require_h_factor,
            uncertainty=uncertainty,
        )
    return len(state_names)


def validate_calculation(
    h5: h5py.File,
    group: h5py.Group,
    name: str,
    ngroups: int,
    legendre_order: int,
    report: InputReport,
    adf_names_by_mix: list[tuple[str, ...]],
    sph_present_by_calc: list[bool],
    *,
    parent_group: h5py.Group | None,
    count_fissionable: bool,
    require_transport_dataset: bool,
    require_volume: bool,
    require_h_factor: bool,
    uncertainty: UncertaintyConfig,
) -> None:
    missing = [field for field in REQUIRED_DATASETS if field not in group]
    if missing:
        report.fail(f"mixture {name}: missing dataset(s): {', '.join(missing)}")
        return

    fissionable_attr = attr_with_parent(group, parent_group, "fissionable")
    fissionable = False if fissionable_attr is None else bool(fissionable_attr)
    if fissionable_attr is None:
        report.fail(f"mixture {name}: fissionable attribute is missing")
    elif count_fissionable and fissionable:
        report.fissionable_mixtures += 1

    volume = attr_with_parent(group, parent_group, "volume")
    if require_volume and volume is None:
        report.fail(f"mixture {name}: volume attribute is missing")
    if volume is None:
        report.volume_defaulted += 1
    else:
        report.volume_attributes += 1
    if volume is not None and float(volume) <= 0.0:
        report.fail(f"mixture {name}: volume attribute must be positive")

    for field in REQUIRED_DATASETS[:-1]:
        validate_vector(group[field], ngroups, report, f"mixture {name}: {field}")

    scatter = np.asarray(group["scatter_matrix"][:], dtype=float)
    axes = scatter_axes(group, h5, parent_group)
    moments = validate_scatter(
        scatter,
        ngroups,
        legendre_order,
        axes,
        report,
        name,
    )
    if not np.all(np.isfinite(scatter)):
        report.fail(f"mixture {name}: scatter_matrix contains non-finite values")
    for field in OPTIONAL_VECTOR_DATASETS:
        if field in group:
            validate_vector(group[field], ngroups, report, f"mixture {name}: {field}")

    if has_h_factor(group):
        report.h_factor_datasets += 1
    elif require_h_factor and fissionable:
        report.fail(
            f"mixture {name}: fissionable calculation requires group-wise "
            "H-FACTOR/kappa_fission data"
        )

    validate_uncertainty_for_calculation(
        group,
        name,
        REQUIRED_DATASETS
        + tuple(field for field in OPTIONAL_VECTOR_DATASETS if field in group),
        fissionable=fissionable,
        scatter_axes=axes,
        ngroups=ngroups,
        legendre_order=legendre_order,
        report=report,
    )

    if "transport_total" in group:
        report.transport_total_datasets += 1
        values = np.asarray(group["transport_total"][:], dtype=float).reshape(-1)
        if values.shape == (ngroups,) and np.any(values <= 0.0):
            report.fail(f"mixture {name}: transport_total must be positive")
        if values.shape == (ngroups,) and np.all(values > 0.0):
            report.transport_total_derivable += 1
    elif moments and moments > 1:
        report.transport_total_derivable += 1
    elif require_transport_dataset:
        report.fail(f"mixture {name}: transport_total dataset is required")
    else:
        report.warn(
            f"mixture {name}: STRD will fall back to total because no transport_total "
            "dataset or P1 scatter is available"
        )

    adf_names = adf_names_for_group(group, ngroups, report, name)
    adf_names_by_mix.append(tuple(adf_names))
    if adf_names:
        report.adf_mixtures += 1

    sph_present = sph_present_for_group(group, ngroups, report, name)
    sph_present_by_calc.append(sph_present)
    if sph_present:
        report.sph_calculations += 1


def has_h_factor(group: h5py.Group) -> bool:
    return any(name in group for name in H_FACTOR_DATASETS)


def scatter_axes(
    group: h5py.Group,
    h5: h5py.File,
    parent_group: h5py.Group | None = None,
) -> str | None:
    sources = [group.attrs]
    if parent_group is not None:
        sources.append(parent_group.attrs)
    sources.append(h5.attrs)
    for source in sources:
        for key in ("scatter_axes", "axes"):
            if key in source:
                return attr_text(source[key])
    return None


def attr_with_parent(
    group: h5py.Group,
    parent_group: h5py.Group | None,
    name: str,
) -> Any | None:
    if name in group.attrs:
        return group.attrs[name]
    if parent_group is not None and name in parent_group.attrs:
        return parent_group.attrs[name]
    return None


def names_from_hdf5_value(value: Any) -> tuple[str, ...]:
    names: list[str] = []
    for item in np.asarray(value).reshape(-1):
        if isinstance(item, bytes):
            names.append(item.decode("utf-8"))
        else:
            names.append(str(item))
    return tuple(names)


def sorted_state_names(states: h5py.Group) -> list[str]:
    def key(name: str) -> tuple[int, int | str]:
        try:
            return (0, int(name))
        except ValueError:
            return (1, name)

    return sorted(states.keys(), key=key)


def integer_attr(attrs: h5py.AttributeManager, name: str) -> int | None:
    if name not in attrs:
        return None
    try:
        return int(attrs[name])
    except (TypeError, ValueError):
        return None


def split_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def output_name_issue(path: Path | None, output_format: str) -> str | None:
    if path is None:
        return None
    name = str(path)
    if output_format == "multicompo":
        allowed = VALID_MULTICOMPO_EXTENSIONS
    elif output_format == "macrolib":
        allowed = VALID_MACROLIB_EXTENSIONS
    else:
        allowed = VALID_MULTICOMPO_EXTENSIONS + VALID_MACROLIB_EXTENSIONS
    if any(name.endswith(extension) for extension in allowed):
        return None
    return f"output should end with one of: {', '.join(allowed)}"


def run_preflight(
    input_paths: list[Path],
    *,
    output_format: str = "any",
    output_path: Path | None = None,
    production: bool = False,
    require_adf: bool = False,
    require_sph: bool = False,
    expected_adf_faces: str | list[str] | None = None,
    require_mixture_order: bool = False,
    require_domain_mode: bool = False,
    require_source_domain_metadata: bool = False,
    require_openmc_provenance: bool = False,
    require_openmc_provenance_if_openmc: bool = False,
    require_openmc_volume_flux: bool = False,
    require_transport_dataset: bool = False,
    require_volume: bool = False,
    require_h_factor: bool = False,
    expected_energy_group_structure: str | None = None,
    expected_energy_bounds: str | Path | np.ndarray | list[float] | None = None,
    expected_energy_bounds_sha256: str | None = None,
    require_known_energy_mesh: bool = False,
    warn_unknown_energy_mesh: bool = False,
    energy_mesh_tolerance: float = MESH_RELATIVE_TOLERANCE,
    scatter_row_balance_warn: float | None = None,
    scatter_row_balance_fail: float | None = None,
    require_energy_bounds_consistency: bool = False,
    chi_sum_tolerance: float | None = None,
    require_adf_face_consistency: bool = False,
    transport_p1_fail: float | None = None,
    uncertainty_warn: float | None = 0.05,
    uncertainty_fail: float | None = None,
    uncertainty_production_fail: float | None = None,
    uncertainty_mean_abs_floor: float = 1.0e-12,
    require_std_dev_coverage: bool = False,
    summary_json: Path | None = None,
) -> bool:
    expected_faces = (
        split_csv(expected_adf_faces)
        if isinstance(expected_adf_faces, str) or expected_adf_faces is None
        else expected_adf_faces
    )
    expected_bounds, expected_bounds_label = _expected_energy_bounds_input(
        expected_energy_bounds
    )
    settings = production_preflight_defaults(
        production=production,
        require_mixture_order=require_mixture_order,
        require_domain_mode=require_domain_mode,
        require_source_domain_metadata=require_source_domain_metadata,
        require_openmc_provenance=require_openmc_provenance,
        require_openmc_provenance_if_openmc=require_openmc_provenance_if_openmc,
        require_openmc_volume_flux=require_openmc_volume_flux,
        require_transport_dataset=require_transport_dataset,
        require_volume=require_volume,
        require_h_factor=require_h_factor,
        require_known_energy_mesh=require_known_energy_mesh,
        warn_unknown_energy_mesh=warn_unknown_energy_mesh,
        energy_mesh_tolerance=energy_mesh_tolerance,
        scatter_row_balance_warn=scatter_row_balance_warn,
        scatter_row_balance_fail=scatter_row_balance_fail,
        require_energy_bounds_consistency=require_energy_bounds_consistency,
        chi_sum_tolerance=chi_sum_tolerance,
        require_adf_face_consistency=require_adf_face_consistency,
        transport_p1_fail=transport_p1_fail,
        uncertainty_warn=uncertainty_warn,
        uncertainty_fail=uncertainty_fail,
        uncertainty_production_fail=uncertainty_production_fail,
        uncertainty_mean_abs_floor=uncertainty_mean_abs_floor,
        require_std_dev_coverage=require_std_dev_coverage,
    )
    reports = [
        validate_input(
            path,
            require_adf=require_adf,
            require_sph=require_sph,
            require_mixture_order=settings["require_mixture_order"],
            require_domain_mode=settings["require_domain_mode"],
            require_source_domain_metadata=settings["require_source_domain_metadata"],
            require_openmc_provenance=settings["require_openmc_provenance"],
            require_openmc_provenance_if_openmc=settings[
                "require_openmc_provenance_if_openmc"
            ],
            require_openmc_volume_flux=settings["require_openmc_volume_flux"],
            require_transport_dataset=settings["require_transport_dataset"],
            require_volume=settings["require_volume"],
            require_h_factor=settings["require_h_factor"],
            expected_energy_group_structure=expected_energy_group_structure,
            expected_energy_bounds=expected_bounds,
            expected_energy_bounds_label=expected_bounds_label,
            expected_energy_bounds_sha256=expected_energy_bounds_sha256,
            require_known_energy_mesh=settings["require_known_energy_mesh"],
            warn_unknown_energy_mesh=settings["warn_unknown_energy_mesh"],
            energy_mesh_tolerance=settings["energy_mesh_tolerance"],
            expected_adf_faces=expected_faces,
            scatter_row_balance_warn=settings["scatter_row_balance_warn"],
            scatter_row_balance_fail=settings["scatter_row_balance_fail"],
            require_energy_bounds_consistency=settings[
                "require_energy_bounds_consistency"
            ],
            chi_sum_tolerance=settings["chi_sum_tolerance"],
            require_adf_face_consistency=settings["require_adf_face_consistency"],
            transport_p1_fail=settings["transport_p1_fail"],
            uncertainty=UncertaintyConfig(
                warn_threshold=settings["uncertainty_warn"],
                fail_threshold=settings["uncertainty_fail"],
                production_fail_threshold=settings["uncertainty_production_fail"],
                mean_abs_floor=settings["uncertainty_mean_abs_floor"],
                require_coverage=settings["require_std_dev_coverage"],
            ),
        )
        for path in input_paths
    ]
    output_issue = output_name_issue(output_path, output_format)
    ok = all(report.ok for report in reports) and output_issue is None
    decision = PASS_DECISION if ok else FAIL_DECISION

    print_preflight_report(
        reports,
        decision=decision,
        output_path=output_path,
        output_issue=output_issue,
    )

    if summary_json:
        write_summary(summary_json, reports, decision, output_issue)

    return ok


def _expected_energy_bounds_input(
    value: str | Path | np.ndarray | list[float] | None,
) -> tuple[np.ndarray | None, str | None]:
    if value is None:
        return None, None
    if isinstance(value, (str, Path)):
        path = Path(value)
        return load_energy_bounds_text(path), str(path)
    return np.asarray(value, dtype=float).reshape(-1), "expected energy bounds"


if __name__ == "__main__":
    raise SystemExit(main())
