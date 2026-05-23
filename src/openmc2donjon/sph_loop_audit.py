"""Audit row generation and audit file writers for the SPH loop driver."""

from __future__ import annotations

import csv
from pathlib import Path

from .hdf5_metadata import Hdf5DatasetMetadata
from .sph_loop_convergence import SphLoopConvergenceReport
from .sph_loop_preflight import SphLoopFluxMapPreflightReport
from .sph_loop_records import (
    SphLoopAuditRow,
    SphLoopArtifactMetadata,
    SphLoopPostprocessReport,
    SphLoopSolveReport,
)
from .sph_workflow import SphIterationWorkflowReport


def build_audit_rows(
    *,
    solves: tuple[SphLoopSolveReport, ...],
    workflows: tuple[SphIterationWorkflowReport, ...],
    convergence: tuple[SphLoopConvergenceReport, ...],
    postprocesses: tuple[SphLoopPostprocessReport, ...],
    final_solve: SphLoopSolveReport | None,
    final_ascii: Path,
) -> tuple[SphLoopAuditRow, ...]:
    solve_by_iteration = {solve.iteration: solve for solve in solves}
    postprocess_by_iteration = {item.iteration: item for item in postprocesses}
    rows: list[SphLoopAuditRow] = []
    for index, workflow in enumerate(workflows, start=1):
        solve = solve_by_iteration.get(index - 1)
        convergence_report = convergence[index - 1] if index - 1 < len(convergence) else None
        worst_bin = (
            None
            if convergence_report is None
            else first_diagnostic_bin(convergence_report.worst_residual_bins)
        )
        postprocess = postprocess_by_iteration.get(index)
        rows.append(
            SphLoopAuditRow(
                stage="iteration",
                iteration=index,
                keff=None if solve is None else solve.keff,
                sph_minimum=workflow.sph_minimum,
                sph_maximum=workflow.sph_maximum,
                sph_max_abs_change=(
                    None if convergence_report is None else convergence_report.sph_max_abs_change
                ),
                sph_max_rel_change=(
                    None if convergence_report is None else convergence_report.sph_max_rel_change
                ),
                flux_ratio_max_residual=(
                    None
                    if convergence_report is None
                    else convergence_report.flux_ratio_max_residual
                ),
                worst_residual_mixture=_optional_str(
                    None if worst_bin is None else worst_bin.get("mixture")
                ),
                worst_residual_group=_optional_int(
                    None if worst_bin is None else worst_bin.get("group")
                ),
                worst_residual_raw_update=optional_float(
                    None if worst_bin is None else worst_bin.get("raw_update")
                ),
                worst_residual=optional_float(
                    None if worst_bin is None else worst_bin.get("residual")
                ),
                worst_residual_bins=(
                    ()
                    if convergence_report is None
                    else tuple(dict(item) for item in convergence_report.worst_residual_bins)
                ),
                converged=None if convergence_report is None else convergence_report.converged,
                solve_result=None if solve is None else solve.result,
                ascii_output=workflow.ascii_output,
                postprocess_output=None if postprocess is None else postprocess.output,
            )
        )
    if final_solve is not None:
        rows.append(
            SphLoopAuditRow(
                stage="final",
                iteration=final_solve.iteration,
                keff=final_solve.keff,
                sph_minimum=None,
                sph_maximum=None,
                sph_max_abs_change=None,
                sph_max_rel_change=None,
                flux_ratio_max_residual=None,
                worst_residual_mixture=None,
                worst_residual_group=None,
                worst_residual_raw_update=None,
                worst_residual=None,
                worst_residual_bins=(),
                converged=None,
                solve_result=final_solve.result,
                ascii_output=final_ascii,
                postprocess_output=None,
            )
        )
    return tuple(rows)


def write_audit_csv(path: Path, rows: tuple[SphLoopAuditRow, ...]) -> None:
    fieldnames = [
        "stage",
        "iteration",
        "keff",
        "sph_minimum",
        "sph_maximum",
        "sph_max_abs_change",
        "sph_max_rel_change",
        "flux_ratio_max_residual",
        "worst_residual_mixture",
        "worst_residual_group",
        "worst_residual_raw_update",
        "worst_residual",
        "converged",
        "solve_result",
        "ascii_output",
        "postprocess_output",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "stage": row.stage,
                    "iteration": row.iteration,
                    "keff": format_optional_float(row.keff),
                    "sph_minimum": format_optional_float(row.sph_minimum),
                    "sph_maximum": format_optional_float(row.sph_maximum),
                    "sph_max_abs_change": format_optional_float(
                        row.sph_max_abs_change
                    ),
                    "sph_max_rel_change": format_optional_float(
                        row.sph_max_rel_change
                    ),
                    "flux_ratio_max_residual": format_optional_float(
                        row.flux_ratio_max_residual
                    ),
                    "worst_residual_mixture": row.worst_residual_mixture or "",
                    "worst_residual_group": (
                        "" if row.worst_residual_group is None else row.worst_residual_group
                    ),
                    "worst_residual_raw_update": format_optional_float(
                        row.worst_residual_raw_update
                    ),
                    "worst_residual": format_optional_float(row.worst_residual),
                    "converged": "" if row.converged is None else str(row.converged),
                    "solve_result": "" if row.solve_result is None else str(row.solve_result),
                    "ascii_output": "" if row.ascii_output is None else str(row.ascii_output),
                    "postprocess_output": (
                        "" if row.postprocess_output is None else str(row.postprocess_output)
                    ),
                }
            )


def write_audit_text(
    path: Path,
    rows: tuple[SphLoopAuditRow, ...],
    *,
    flux_map_preflight: SphLoopFluxMapPreflightReport | None = None,
    artifact_metadata: SphLoopArtifactMetadata | None = None,
) -> None:
    lines = [
        "OpenMC-to-DONJON SPH loop audit",
    ]
    if flux_map_preflight is not None:
        lines.extend(_format_preflight_audit_lines(flux_map_preflight))
    if artifact_metadata is not None:
        lines.extend(_format_artifact_metadata_lines(artifact_metadata))
    lines.append(
        (
            "stage      iter  keff          sph_min       sph_max       "
            "sph_rel       flux_res      worst_bin            raw_update    "
            "residual     converged"
        )
    )
    for row in rows:
        converged = "" if row.converged is None else str(row.converged)
        lines.append(
            f"{row.stage:<10} {row.iteration:>4d}  "
            f"{format_optional_float(row.keff):<12} "
            f"{format_optional_float(row.sph_minimum):<12} "
            f"{format_optional_float(row.sph_maximum):<12} "
            f"{format_optional_float(row.sph_max_rel_change):<12} "
            f"{format_optional_float(row.flux_ratio_max_residual):<12} "
            f"{_format_audit_bin(row):<20} "
            f"{format_optional_float(row.worst_residual_raw_update):<12} "
            f"{format_optional_float(row.worst_residual):<12} "
            f"{converged:<9}"
        )
    final_bins = _last_worst_residual_bins(rows)
    if final_bins:
        lines.extend(
            [
                "",
                "Final worst residual bins",
                "rank  mixture          group  raw_update    residual",
            ]
        )
        for rank, item in enumerate(final_bins[:10], start=1):
            lines.append(
                f"{rank:<5d} "
                f"{str(item.get('mixture', '')):<16} "
                f"{str(item.get('group', '')):<6} "
                f"{format_optional_float(optional_float(item.get('raw_update'))):<12} "
                f"{format_optional_float(optional_float(item.get('residual'))):<12}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def first_diagnostic_bin(
    bins: tuple[dict[str, object], ...],
) -> dict[str, object] | None:
    if not bins:
        return None
    return dict(bins[0])


def format_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12g}"


def optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _format_preflight_audit_lines(
    report: SphLoopFluxMapPreflightReport,
) -> list[str]:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        (
            f"Flux-map preflight: {status} map={report.map_kind} "
            f"mixtures={len(report.mixture_names)} groups={report.energy_groups}"
        )
    ]
    if report.minimum_required_flux_unknown_count is not None:
        lines.append(
            "  minimum_required_flux_unknown_count="
            f"{report.minimum_required_flux_unknown_count}"
        )
    lines.append(
        "  mgxs_volume="
        f"{report.mgxs_volume_attributes}/{report.mgxs_calculations} "
        f"defaulted={report.mgxs_volume_defaulted}/{report.mgxs_calculations} "
        f"nonpositive={report.mgxs_volume_nonpositive}"
    )
    if report.mesh_shape is not None:
        shape = "x".join(str(value) for value in report.mesh_shape)
        lines.append(
            f"  mesh_shape={shape} cells={report.mesh_cell_count} "
            f"nonpositive_ids={report.mesh_zero_or_negative_id_count}"
        )
    if report.errors:
        lines.extend(f"  ERROR: {error}" for error in report.errors)
    if report.warnings:
        lines.extend(f"  WARN: {warning}" for warning in report.warnings)
    lines.append("")
    return lines


def _format_artifact_metadata_lines(
    metadata: SphLoopArtifactMetadata,
) -> list[str]:
    lines = [
        "Artifact metadata:",
        f"  reference_flux: {_format_dataset_metadata(metadata.reference_flux)}",
    ]
    for item in metadata.workflows:
        lines.append(
            f"  iter{item.iteration} donjon_volume_flux: "
            f"{_format_dataset_metadata(item.donjon_volume_flux)}"
        )
        lines.append(
            f"  iter{item.iteration} sph_sidecar: "
            f"{_format_dataset_metadata(item.sph_sidecar)}"
        )
    if metadata.final_sph_sidecar is not None:
        lines.append(
            "  final_sph_sidecar: "
            f"{_format_dataset_metadata(metadata.final_sph_sidecar)}"
        )
    lines.append("")
    return lines


def _format_dataset_metadata(metadata: Hdf5DatasetMetadata) -> str:
    shape = "x".join(str(value) for value in metadata.shape)
    order = metadata.group_order or ""
    mixtures = _format_mixture_names(metadata.mixture_names)
    return (
        f"dataset=/{metadata.dataset} shape={shape} "
        f"group_order={order} mixtures={mixtures}"
    )


def _format_mixture_names(names: tuple[str, ...]) -> str:
    if not names:
        return ""
    if len(names) <= 4:
        return ",".join(names)
    return ",".join(names[:4]) + f",...({len(names)} total)"


def _format_audit_bin(row: SphLoopAuditRow) -> str:
    if row.worst_residual_mixture is None or row.worst_residual_group is None:
        return ""
    return f"{row.worst_residual_mixture}:g{row.worst_residual_group}"


def _last_worst_residual_bins(
    rows: tuple[SphLoopAuditRow, ...],
) -> tuple[dict[str, object], ...]:
    for row in reversed(rows):
        if row.worst_residual_bins:
            return row.worst_residual_bins
    return ()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    return None
