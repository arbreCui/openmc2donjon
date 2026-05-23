"""Reporting helpers for the MGXS HDF5 input contract."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


SCHEMA = "openmc2donjon.mgxs-input-contract.v1"
PASS_DECISION = "mgxs_input_contract_passed"
FAIL_DECISION = "mgxs_input_contract_failed"


@dataclass
class InputReport:
    path: str
    ok: bool = True
    energy_groups: int | None = None
    legendre_order: int | None = None
    energy_group_structure: str | None = None
    energy_bounds_sha256: str | None = None
    energy_bounds_local_count: int = 0
    domain_mode: str | None = None
    mixtures: int = 0
    declared_mixture_order: bool = False
    source_domain_indices: int = 0
    source_domain_metadata: int = 0
    stateful_mixtures: int = 0
    state_points: int = 1
    calculations: int = 0
    burnup_axis_path: str | None = None
    burnup_axis_values: int | None = None
    fissionable_mixtures: int = 0
    volume_attributes: int = 0
    volume_defaulted: int = 0
    openmc_volume_flux_present: bool = False
    openmc_volume_flux_shape: tuple[int, ...] | None = None
    openmc_volume_flux_group_order: str | None = None
    openmc_volume_flux_source_group_order: str | None = None
    openmc_volume_flux_mixture_names: int = 0
    openmc_volume_flux_std_dev_present: bool = False
    openmc_volume_flux_std_dev_shape: tuple[int, ...] | None = None
    openmc_volume_flux_std_dev_max_rel: float | None = None
    openmc_volume_flux_std_dev_worst: str | None = None
    h_factor_datasets: int = 0
    scatter_axes: list[str] = field(default_factory=list)
    transport_total_datasets: int = 0
    transport_total_derivable: int = 0
    adf_mixtures: int = 0
    adf_faces: list[str] = field(default_factory=list)
    sph_calculations: int = 0
    scatter_row_balance_checked: bool = False
    scatter_row_balance_warn_threshold: float | None = None
    scatter_row_balance_fail_threshold: float | None = None
    scatter_row_balance_max_abs: float | None = None
    scatter_row_balance_max_rel: float | None = None
    scatter_row_balance_worst: str | None = None
    chi_checked: int = 0
    chi_sum_max_abs_error: float | None = None
    chi_sum_worst: str | None = None
    nu_ratio_checked_bins: int = 0
    nu_ratio_min: float | None = None
    nu_ratio_max: float | None = None
    nu_ratio_worst: str | None = None
    adf_face_consistency_checked: bool = False
    adf_face_consistency_errors: int = 0
    transport_p1_checked: int = 0
    transport_p1_max_abs: float | None = None
    transport_p1_max_rel: float | None = None
    transport_p1_worst: str | None = None
    uncertainty_checked: bool = False
    uncertainty_warn_threshold: float | None = None
    uncertainty_fail_threshold: float | None = None
    uncertainty_production_fail_threshold: float | None = None
    uncertainty_mean_abs_floor: float = 1.0e-12
    uncertainty_expected_datasets: int = 0
    uncertainty_datasets: int = 0
    uncertainty_bins_checked: int = 0
    uncertainty_max_rel: float | None = None
    uncertainty_worst: str | None = None
    uncertainty_top: list[str] = field(default_factory=list)
    uncertainty_production_bins_checked: int = 0
    uncertainty_production_max_rel: float | None = None
    uncertainty_production_worst: str | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.ok = False
        self.issues.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def print_preflight_report(
    reports: list[InputReport],
    *,
    decision: str,
    output_path: Path | None = None,
    output_issue: str | None = None,
) -> None:
    print("OpenMC-to-DONJON MGXS input contract")
    print(f"  schema: {SCHEMA}")
    print()
    for report in reports:
        print_report(report)
    if output_path:
        status = "PASS" if output_issue is None else "FAIL"
        print(f"  {status}  output name: {output_path}")
        if output_issue:
            print(f"        {output_issue}")
        print()

    print("MGXS input contract decision")
    print(f"  {decision}")


def print_report(report: InputReport) -> None:
    status = "PASS" if report.ok else "FAIL"
    calculation_count = report.calculations or report.mixtures
    print(f"== {Path(report.path).name} ==")
    print(f"  {status}  path: {report.path}")
    print(f"        energy_groups={report.energy_groups} legendre_order={report.legendre_order}")
    structure = report.energy_group_structure or "unspecified"
    digest = (
        "none"
        if report.energy_bounds_sha256 is None
        else report.energy_bounds_sha256[:12]
    )
    print(f"        energy_group_structure={structure} bounds_sha256={digest}")
    print(f"        domain_mode={report.domain_mode or 'unspecified'}")
    print(
        "        mixtures="
        f"{report.mixtures} fissionable={report.fissionable_mixtures} "
        f"calculations={calculation_count} state_points={report.state_points}"
    )
    order = "declared" if report.declared_mixture_order else "group-key-fallback"
    print(
        "        "
        f"mixture_order={order} "
        f"source_domain_index={report.source_domain_indices}/{report.mixtures} "
        f"source_domain_metadata={report.source_domain_metadata}/{report.mixtures}"
    )
    if report.burnup_axis_path:
        print(
            "        burnup_axis="
            f"{report.burnup_axis_path} values={report.burnup_axis_values}"
        )
    else:
        print("        burnup_axis=none")
    print(
        "        "
        f"volume={report.volume_attributes}/{calculation_count} "
        f"defaulted={report.volume_defaulted}/{calculation_count} "
        f"h_factor={report.h_factor_datasets}/{calculation_count}"
    )
    print(_openmc_volume_flux_line(report))
    print(
        "        "
        f"transport_total={report.transport_total_datasets}/{calculation_count} "
        f"strd_ready={report.transport_total_derivable}/{calculation_count}"
    )
    axes = ",".join(report.scatter_axes) if report.scatter_axes else "<inferred>"
    print(f"        scatter_axes={axes}")
    if report.scatter_row_balance_checked:
        if report.scatter_row_balance_max_rel is None:
            print("        scatter_row_balance=not evaluated")
        else:
            print(
                "        scatter_row_balance="
                f"max_rel={report.scatter_row_balance_max_rel:.6e} "
                f"max_abs={(report.scatter_row_balance_max_abs or 0.0):.6e} "
                f"worst={report.scatter_row_balance_worst}"
            )
    print(_physics_checks_line(report))
    print(_uncertainty_line(report))
    if report.adf_mixtures:
        print(
            "        adf="
            f"{report.adf_mixtures}/{calculation_count} faces={','.join(report.adf_faces)}"
        )
    else:
        print("        adf=none")
    if report.sph_calculations:
        print(f"        sph={report.sph_calculations}/{calculation_count}")
    else:
        print("        sph=none")
    for issue in report.issues[:12]:
        print(f"        FAIL: {issue}")
    if len(report.issues) > 12:
        print(f"        ... {len(report.issues) - 12} more issue(s)")
    for warning in report.warnings[:6]:
        print(f"        WARN: {warning}")
    if len(report.warnings) > 6:
        print(f"        ... {len(report.warnings) - 6} more warning(s)")
    print()


def write_summary(
    path: Path,
    reports: list[InputReport],
    decision: str,
    output_issue: str | None,
) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": decision,
        "output_issue": output_issue,
        "inputs": [_report_payload(report) for report in reports],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _report_payload(report: InputReport) -> dict[str, object]:
    return {
        "path": report.path,
        "ok": report.ok,
        "energy_groups": report.energy_groups,
        "legendre_order": report.legendre_order,
        "energy_group_structure": report.energy_group_structure,
        "energy_bounds_sha256": report.energy_bounds_sha256,
        "energy_bounds_local_count": report.energy_bounds_local_count,
        "domain_mode": report.domain_mode,
        "mixtures": report.mixtures,
        "declared_mixture_order": report.declared_mixture_order,
        "source_domain_indices": report.source_domain_indices,
        "source_domain_metadata": report.source_domain_metadata,
        "stateful_mixtures": report.stateful_mixtures,
        "state_points": report.state_points,
        "calculations": report.calculations,
        "burnup_axis_path": report.burnup_axis_path,
        "burnup_axis_values": report.burnup_axis_values,
        "fissionable_mixtures": report.fissionable_mixtures,
        "volume_attributes": report.volume_attributes,
        "volume_defaulted": report.volume_defaulted,
        "openmc_volume_flux": {
            "present": report.openmc_volume_flux_present,
            "shape": report.openmc_volume_flux_shape,
            "group_order": report.openmc_volume_flux_group_order,
            "source_group_order": report.openmc_volume_flux_source_group_order,
            "mixture_names": report.openmc_volume_flux_mixture_names,
            "std_dev_present": report.openmc_volume_flux_std_dev_present,
            "std_dev_shape": report.openmc_volume_flux_std_dev_shape,
            "std_dev_max_rel": report.openmc_volume_flux_std_dev_max_rel,
            "std_dev_worst": report.openmc_volume_flux_std_dev_worst,
        },
        "h_factor_datasets": report.h_factor_datasets,
        "scatter_axes": report.scatter_axes,
        "scatter_row_balance": {
            "checked": report.scatter_row_balance_checked,
            "warn_threshold": report.scatter_row_balance_warn_threshold,
            "fail_threshold": report.scatter_row_balance_fail_threshold,
            "max_abs": report.scatter_row_balance_max_abs,
            "max_rel": report.scatter_row_balance_max_rel,
            "worst": report.scatter_row_balance_worst,
        },
        "physics_checks": {
            "chi_checked": report.chi_checked,
            "chi_sum_max_abs_error": report.chi_sum_max_abs_error,
            "chi_sum_worst": report.chi_sum_worst,
            "nu_ratio_checked_bins": report.nu_ratio_checked_bins,
            "nu_ratio_min": report.nu_ratio_min,
            "nu_ratio_max": report.nu_ratio_max,
            "nu_ratio_worst": report.nu_ratio_worst,
            "adf_face_consistency_checked": report.adf_face_consistency_checked,
            "adf_face_consistency_errors": report.adf_face_consistency_errors,
            "transport_p1_checked": report.transport_p1_checked,
            "transport_p1_max_abs": report.transport_p1_max_abs,
            "transport_p1_max_rel": report.transport_p1_max_rel,
            "transport_p1_worst": report.transport_p1_worst,
        },
        "uncertainty": {
            "checked": report.uncertainty_checked,
            "warn_threshold": report.uncertainty_warn_threshold,
            "fail_threshold": report.uncertainty_fail_threshold,
            "production_fail_threshold": (
                report.uncertainty_production_fail_threshold
            ),
            "mean_abs_floor": report.uncertainty_mean_abs_floor,
            "expected_datasets": report.uncertainty_expected_datasets,
            "datasets": report.uncertainty_datasets,
            "missing_datasets": (
                report.uncertainty_expected_datasets - report.uncertainty_datasets
            ),
            "bins_checked": report.uncertainty_bins_checked,
            "max_rel": report.uncertainty_max_rel,
            "worst": report.uncertainty_worst,
            "top": report.uncertainty_top,
            "production_bins_checked": report.uncertainty_production_bins_checked,
            "production_max_rel": report.uncertainty_production_max_rel,
            "production_worst": report.uncertainty_production_worst,
        },
        "transport_total_datasets": report.transport_total_datasets,
        "transport_total_derivable": report.transport_total_derivable,
        "adf_mixtures": report.adf_mixtures,
        "adf_faces": report.adf_faces,
        "sph_calculations": report.sph_calculations,
        "issues": report.issues,
        "warnings": report.warnings,
    }


def _uncertainty_line(report: InputReport) -> str:
    prefix = "        uncertainty="
    if not report.uncertainty_checked:
        return f"{prefix}not checked"
    if report.uncertainty_expected_datasets == 0:
        return f"{prefix}not applicable"
    if report.uncertainty_datasets == 0:
        return f"{prefix}missing"
    coverage = f"{report.uncertainty_datasets}/{report.uncertainty_expected_datasets}"
    if report.uncertainty_max_rel is None:
        return (
            f"{prefix}std_dev={coverage} "
            f"bins={report.uncertainty_bins_checked} max_rel=not evaluated"
        )
    return (
        f"{prefix}std_dev={coverage} "
        f"bins={report.uncertainty_bins_checked} "
        f"max_rel={report.uncertainty_max_rel:.6e} "
        f"worst={report.uncertainty_worst}"
        f"{_uncertainty_production_suffix(report)}"
    )


def _physics_checks_line(report: InputReport) -> str:
    return (
        "        physics_checks="
        f"local_energy_bounds={report.energy_bounds_local_count} "
        f"chi={report.chi_checked} "
        f"chi_sum_error={_format_optional(report.chi_sum_max_abs_error)} "
        f"nu_bins={report.nu_ratio_checked_bins} "
        f"nu_min={_format_optional(report.nu_ratio_min)} "
        f"nu_max={_format_optional(report.nu_ratio_max)} "
        f"transport_p1={report.transport_p1_checked} "
        f"transport_p1_rel={_format_optional(report.transport_p1_max_rel)}"
    )


def _format_optional(value: float | None) -> str:
    return "none" if value is None else f"{value:.6e}"


def _openmc_volume_flux_line(report: InputReport) -> str:
    prefix = "        openmc_volume_flux="
    if not report.openmc_volume_flux_present:
        return f"{prefix}missing"
    shape = (
        "unknown"
        if report.openmc_volume_flux_shape is None
        else "x".join(str(value) for value in report.openmc_volume_flux_shape)
    )
    group_order = report.openmc_volume_flux_group_order or "unspecified"
    return (
        f"{prefix}present shape={shape} group_order={group_order} "
        f"mixture_names={report.openmc_volume_flux_mixture_names}/{report.mixtures}"
        f"{_openmc_volume_flux_std_dev_suffix(report)}"
    )


def _openmc_volume_flux_std_dev_suffix(report: InputReport) -> str:
    if not report.openmc_volume_flux_std_dev_present:
        return " std_dev=missing"
    if report.openmc_volume_flux_std_dev_max_rel is None:
        return " std_dev=present max_rel=not evaluated"
    return f" std_dev=present max_rel={report.openmc_volume_flux_std_dev_max_rel:.6e}"


def _uncertainty_production_suffix(report: InputReport) -> str:
    if report.uncertainty_production_max_rel is None:
        return ""
    return f" production_max_rel={report.uncertainty_production_max_rel:.6e}"
