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
    mixtures: int = 0
    stateful_mixtures: int = 0
    state_points: int = 1
    calculations: int = 0
    burnup_axis_path: str | None = None
    burnup_axis_values: int | None = None
    fissionable_mixtures: int = 0
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
    print(
        "        mixtures="
        f"{report.mixtures} fissionable={report.fissionable_mixtures} "
        f"calculations={calculation_count} state_points={report.state_points}"
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
        "mixtures": report.mixtures,
        "stateful_mixtures": report.stateful_mixtures,
        "state_points": report.state_points,
        "calculations": report.calculations,
        "burnup_axis_path": report.burnup_axis_path,
        "burnup_axis_values": report.burnup_axis_values,
        "fissionable_mixtures": report.fissionable_mixtures,
        "scatter_axes": report.scatter_axes,
        "scatter_row_balance": {
            "checked": report.scatter_row_balance_checked,
            "warn_threshold": report.scatter_row_balance_warn_threshold,
            "fail_threshold": report.scatter_row_balance_fail_threshold,
            "max_abs": report.scatter_row_balance_max_abs,
            "max_rel": report.scatter_row_balance_max_rel,
            "worst": report.scatter_row_balance_worst,
        },
        "transport_total_datasets": report.transport_total_datasets,
        "transport_total_derivable": report.transport_total_derivable,
        "adf_mixtures": report.adf_mixtures,
        "adf_faces": report.adf_faces,
        "sph_calculations": report.sph_calculations,
        "issues": report.issues,
        "warnings": report.warnings,
    }
