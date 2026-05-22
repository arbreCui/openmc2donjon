#!/usr/bin/env python3
"""Validate converter-facing OpenMC MGXS/ADF HDF5 input files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from .energy_groups import energy_bounds_sha256, load_energy_bounds_text
from .mgxs_input_equivalence import (
    SPH_DATASETS,
    adf_names_from_attrs,
    adf_names_for_group,
    attr_text,
    sph_present_for_group,
    validate_adf_name,
    validate_adf_layout,
    validate_adf_values,
    validate_sph_layout,
    validate_vector,
)
from .mgxs_input_report import (
    FAIL_DECISION,
    PASS_DECISION,
    SCHEMA,
    InputReport,
    print_preflight_report,
    print_report,
    write_summary,
)
from .mgxs_input_scatter import (
    MOMENT_FIRST_SCATTER_AXES,
    MOMENT_LAST_SCATTER_AXES,
    configure_scatter_row_balance,
    finalize_scatter_row_balance,
    normalize_axes,
    p0_scatter_matrix,
    update_scatter_row_balance,
    validate_scatter,
    vector_values_for_balance,
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


def main() -> int:
    args = parse_args()
    expected_faces = split_csv(args.expected_adf_faces)
    reports = [
        validate_input(
            path,
            require_adf=args.require_adf,
            require_sph=args.require_sph,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            require_h_factor=args.require_h_factor,
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
            expected_adf_faces=expected_faces,
            scatter_row_balance_warn=args.scatter_row_balance_warn,
            scatter_row_balance_fail=args.scatter_row_balance_fail,
            uncertainty=UncertaintyConfig(
                warn_threshold=None if args.no_uncertainty_check else args.uncertainty_warn,
                fail_threshold=None if args.no_uncertainty_check else args.uncertainty_fail,
                production_fail_threshold=(
                    None
                    if args.no_uncertainty_check
                    else args.uncertainty_production_fail
                ),
                mean_abs_floor=args.uncertainty_mean_abs_floor,
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

    return 0 if ok or not args.check else 1


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
        help="require group-wise H-FACTOR/kappa-fission data for every calculation",
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
    require_transport_dataset: bool = False,
    require_volume: bool = False,
    require_h_factor: bool = False,
    expected_energy_group_structure: str | None = None,
    expected_energy_bounds: np.ndarray | list[float] | None = None,
    expected_energy_bounds_label: str | None = None,
    expected_energy_bounds_sha256: str | None = None,
    expected_adf_faces: list[str] | None = None,
    scatter_row_balance_warn: float | None = None,
    scatter_row_balance_fail: float | None = None,
    uncertainty: UncertaintyConfig | None = None,
) -> InputReport:
    report = InputReport(path=str(path))
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
                require_transport_dataset=require_transport_dataset,
                require_volume=require_volume,
                require_h_factor=require_h_factor,
                expected_energy_group_structure=expected_energy_group_structure,
                expected_energy_bounds=expected_energy_bounds,
                expected_energy_bounds_label=expected_energy_bounds_label,
                expected_energy_bounds_sha256=expected_energy_bounds_sha256,
                expected_adf_faces=expected_adf_faces,
                uncertainty=uncertainty or UncertaintyConfig(),
            )
    except OSError as exc:
        report.fail(f"cannot open HDF5 file: {exc}")
    return report


def validate_open_h5(
    h5: h5py.File,
    report: InputReport,
    *,
    require_adf: bool,
    require_sph: bool,
    require_transport_dataset: bool,
    require_volume: bool,
    require_h_factor: bool,
    expected_energy_group_structure: str | None,
    expected_energy_bounds: np.ndarray | list[float] | None,
    expected_energy_bounds_label: str | None,
    expected_energy_bounds_sha256: str | None,
    expected_adf_faces: list[str] | None,
    uncertainty: UncertaintyConfig,
) -> None:
    ngroups = integer_attr(h5.attrs, "energy_groups")
    legendre_order = integer_attr(h5.attrs, "legendre_order")
    report.energy_groups = ngroups
    report.legendre_order = legendre_order

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
    )

    if "mixtures" not in h5 or not isinstance(h5["mixtures"], h5py.Group):
        report.fail("/mixtures group is missing")
        return
    mixtures = h5["mixtures"]
    report.mixtures = len(mixtures)
    if report.mixtures == 0:
        report.fail("/mixtures group contains no mixtures")
        return

    burnup_axis = burnup_axis_from_hdf5(h5, report)
    adf_names_by_mix: list[tuple[str, ...]] = []
    sph_present_by_calc: list[bool] = []
    state_counts: list[int] = []
    for name, group in mixtures.items():
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

    validate_state_layout(report, state_counts, burnup_axis)

    validate_adf_layout(report, adf_names_by_mix, require_adf, expected_adf_faces)
    validate_sph_layout(report, sph_present_by_calc, require_sph)
    finalize_volume_contract(report, require_volume=bool(require_volume))

    finalize_scatter_row_balance(report)
    finalize_uncertainty(report)


def finalize_volume_contract(report: InputReport, *, require_volume: bool) -> None:
    if report.volume_defaulted == 0 or require_volume:
        return
    calculation_count = report.calculations or report.mixtures
    report.warn(
        f"{report.volume_defaulted}/{calculation_count} calculation(s) are missing "
        "volume; converter readers will use default volume 1.0 for those "
        "calculations"
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
            return
        if not np.allclose(energy, expected, rtol=1.0e-10, atol=0.0):
            index = int(np.argmax(np.abs(energy - expected)))
            report.fail(
                f"/energy_bounds differ from {label}: index {index} "
                f"actual={energy[index]:.12e} expected={expected[index]:.12e}"
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

    if attr_with_parent(group, parent_group, "fissionable") is None:
        report.fail(f"mixture {name}: fissionable attribute is missing")
    elif count_fissionable and bool(attr_with_parent(group, parent_group, "fissionable")):
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
    if report.scatter_row_balance_checked:
        update_scatter_row_balance(
            group,
            scatter,
            axes,
            ngroups,
            legendre_order,
            report,
            name,
        )

    for field in OPTIONAL_VECTOR_DATASETS:
        if field in group:
            validate_vector(group[field], ngroups, report, f"mixture {name}: {field}")

    if has_h_factor(group):
        report.h_factor_datasets += 1
    elif require_h_factor:
        report.fail(
            f"mixture {name}: group-wise H-FACTOR/kappa_fission dataset is required"
        )

    validate_uncertainty_for_calculation(
        group,
        name,
        REQUIRED_DATASETS
        + tuple(field for field in OPTIONAL_VECTOR_DATASETS if field in group),
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
    require_adf: bool = False,
    require_sph: bool = False,
    expected_adf_faces: str | list[str] | None = None,
    require_transport_dataset: bool = False,
    require_volume: bool = False,
    require_h_factor: bool = False,
    expected_energy_group_structure: str | None = None,
    expected_energy_bounds: str | Path | np.ndarray | list[float] | None = None,
    expected_energy_bounds_sha256: str | None = None,
    scatter_row_balance_warn: float | None = None,
    scatter_row_balance_fail: float | None = None,
    uncertainty_warn: float | None = 0.05,
    uncertainty_fail: float | None = None,
    uncertainty_production_fail: float | None = None,
    uncertainty_mean_abs_floor: float = 1.0e-12,
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
    reports = [
        validate_input(
            path,
            require_adf=require_adf,
            require_sph=require_sph,
            require_transport_dataset=require_transport_dataset,
            require_volume=require_volume,
            require_h_factor=require_h_factor,
            expected_energy_group_structure=expected_energy_group_structure,
            expected_energy_bounds=expected_bounds,
            expected_energy_bounds_label=expected_bounds_label,
            expected_energy_bounds_sha256=expected_energy_bounds_sha256,
            expected_adf_faces=expected_faces,
            scatter_row_balance_warn=scatter_row_balance_warn,
            scatter_row_balance_fail=scatter_row_balance_fail,
            uncertainty=UncertaintyConfig(
                warn_threshold=uncertainty_warn,
                fail_threshold=uncertainty_fail,
                production_fail_threshold=uncertainty_production_fail,
                mean_abs_floor=uncertainty_mean_abs_floor,
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
