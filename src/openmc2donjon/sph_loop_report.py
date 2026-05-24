"""Reporting and audit helpers for the SPH loop driver."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .bundle import ArtifactSpec, bundle_artifacts
from .hdf5_metadata import Hdf5DatasetMetadata
from .sph_loop_production_audit import build_production_audit_payload
from .sph_loop_audit import (
    first_diagnostic_bin,
    format_optional_float,
    optional_float,
)
from .sph_loop_preflight import (
    payload as flux_map_preflight_payload,
)
from .sph_loop_records import (
    SphLoopAuditRow,
    SphLoopArtifactMetadata,
    SphLoopWorkflowMetadata,
    SphLoopPostprocessReport,
    SphLoopReport,
    SphLoopSolveReport,
)


SCHEMA = "openmc2donjon.sph-loop.v1"
PASS_DECISION = "openmc2donjon_sph_loop_passed"

__all__ = [
    "PASS_DECISION",
    "SCHEMA",
    "SphLoopAuditRow",
    "SphLoopPostprocessReport",
    "SphLoopReport",
    "SphLoopSolveReport",
    "print_report",
    "write_bundle",
    "write_summary",
]


def print_report(report: SphLoopReport) -> None:
    print("OpenMC-to-DONJON SPH loop")
    print(f"  schema: {SCHEMA}")
    print(f"  config: {report.config_path}")
    print(f"  input: {report.input_h5}")
    print(f"  output_dir: {report.output_dir}")
    print(f"  iterations: {report.completed_iterations}/{report.iterations}")
    print(f"  reference_flux: {report.reference_flux}")
    print(f"  initial_ascii: {report.initial_ascii}")
    print(f"  final_ascii: {report.final_ascii}")
    print(f"  audit_csv: {report.audit_csv}")
    print(f"  audit_text: {report.audit_text}")
    print(
        "  flux_map_preflight: "
        f"{'PASS' if report.flux_map_preflight.passed else 'FAIL'} "
        f"map={report.flux_map_preflight.map_kind} "
        f"mixtures={len(report.flux_map_preflight.mixture_names)} "
        f"groups={report.flux_map_preflight.energy_groups} "
        f"mesh={report.flux_map_preflight.mgxs_energy_mesh_id or 'unknown'} "
        f"volume_defaulted={report.flux_map_preflight.mgxs_volume_defaulted} "
        f"h_factor_missing={report.flux_map_preflight.mgxs_h_factor_missing} "
        "scatter_row_balance="
        f"{format_optional_float(report.flux_map_preflight.mgxs_scatter_row_balance_max_rel)} "
        "chi_error="
        f"{format_optional_float(report.flux_map_preflight.mgxs_chi_sum_max_abs_error)}"
    )
    if report.bundle_manifest is not None:
        print(f"  bundle_manifest: {report.bundle_manifest}")
    if report.final_sph_sidecar is not None:
        print(f"  final_sph_sidecar: {report.final_sph_sidecar}")
    print(
        "  artifact_metadata: "
        f"reference_order={report.artifact_metadata.reference_flux.group_order} "
        f"workflow_count={len(report.artifact_metadata.workflows)}"
    )
    production_audit = _production_audit_payload(report)
    print(
        "  production_audit: "
        f"{'PASS' if production_audit['passed'] else 'FAIL'} "
        f"checks={len(production_audit['checks'])} "
        f"errors={len(production_audit['errors'])}"
    )
    for solve in report.solves:
        print(
            f"  solve[{solve.iteration}]: rc={solve.returncode} "
            f"result={solve.result} "
            f"vectors={solve.flux_vector_count} unknowns={solve.flux_unknown_count} "
            f"keff={format_optional_float(solve.keff)}"
        )
    for postprocess in report.postprocesses:
        print(
            f"  postprocess[{postprocess.iteration}]: rc={postprocess.returncode} "
            f"output={postprocess.output} blocks={postprocess.block_count}"
        )
    if report.convergence_enabled:
        print("  convergence:")
        print(
            "    "
            f"fail_on_nonconvergence={report.fail_on_nonconvergence} "
            f"min_iterations={report.min_iterations}"
        )
        for item in report.convergence:
            print(
                f"    iter{item.iteration}: "
                f"sph_rel={item.sph_max_rel_change:.6e} "
                f"flux_res={item.flux_ratio_max_residual:.6e} "
                f"clipped={item.clipped_count}:{item.clipped_fraction:.3f} "
                f"converged={item.converged}"
            )
        print(f"  stop_reason: {report.stop_reason}")
    quality = _quality_payload(report)
    if quality["final_flux_ratio_max_residual"] is not None:
        print("  quality:")
        print(
            "    flux_residual="
            f"{format_optional_float(quality['initial_flux_ratio_max_residual'])}"
            " -> "
            f"{format_optional_float(quality['final_flux_ratio_max_residual'])} "
            "ratio="
            f"{format_optional_float(quality['final_to_initial_flux_residual_ratio'])}"
        )
        print(
            "    final_clipped="
            f"{quality['final_clipped_count']}:"
            f"{format_optional_float(quality['final_clipped_fraction'])} "
            "max_clipped="
            f"{quality['maximum_clipped_count']}:"
            f"{format_optional_float(quality['maximum_clipped_fraction'])}"
        )
        final_worst = quality["final_worst_residual_bin"]
        if isinstance(final_worst, dict):
            print(
                "    final_worst_bin="
                f"{final_worst.get('mixture')} g{final_worst.get('group')} "
                f"raw={format_optional_float(optional_float(final_worst.get('raw_update')))} "
                f"residual={format_optional_float(optional_float(final_worst.get('residual')))}"
            )
    if report.acceptance.enabled:
        print("  acceptance:")
        print(f"    decision={report.acceptance.decision}")
        for item in report.acceptance.checks:
            status = "PASS" if item.passed else "FAIL"
            print(f"    {status} {item.name}: {item.message}")
    print()
    print("SPH loop decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SphLoopReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "config_path": str(report.config_path),
        "input_h5": str(report.input_h5),
        "output_dir": str(report.output_dir),
        "reference_flux": report.reference_flux,
        "iterations": report.iterations,
        "completed_iterations": report.completed_iterations,
        "output_format": report.output_format,
        "initial_ascii": str(report.initial_ascii),
        "final_ascii": str(report.final_ascii),
        "audit_csv": str(report.audit_csv),
        "audit_text": str(report.audit_text),
        "bundle_manifest": (
            None if report.bundle_manifest is None else str(report.bundle_manifest)
        ),
        "run_script": None if report.run_script is None else str(report.run_script),
        "acceptance_enabled": report.acceptance.enabled,
        "acceptance_passed": report.acceptance.passed,
        "acceptance_decision": report.acceptance.decision,
        "final_sph_sidecar": (
            None if report.final_sph_sidecar is None else str(report.final_sph_sidecar)
        ),
        "convergence_enabled": report.convergence_enabled,
        "converged": report.converged,
        "stop_reason": report.stop_reason,
        "sph_change_tolerance": report.sph_change_tolerance,
        "flux_ratio_tolerance": report.flux_ratio_tolerance,
        "min_iterations": report.min_iterations,
        "fail_on_nonconvergence": report.fail_on_nonconvergence,
        "flux_map_preflight": flux_map_preflight_payload(
            report.flux_map_preflight
        ),
        "artifact_metadata": _artifact_metadata_payload(report.artifact_metadata),
        "production_audit": _production_audit_payload(report),
        "quality": _quality_payload(report),
        "solves": [
            {
                "iteration": solve.iteration,
                "command": list(solve.command),
                "cwd": str(solve.cwd),
                "ascii_input": str(solve.ascii_input),
                "result": str(solve.result),
                "stdout": str(solve.stdout),
                "stderr": str(solve.stderr),
                "returncode": solve.returncode,
                "result_bytes": solve.result_bytes,
                "flux_vector_count": solve.flux_vector_count,
                "flux_unknown_count": solve.flux_unknown_count,
                "keff": solve.keff,
            }
            for solve in report.solves
        ],
        "convergence": [
            {
                "iteration": item.iteration,
                "sph_max_abs_change": item.sph_max_abs_change,
                "sph_max_rel_change": item.sph_max_rel_change,
                "flux_ratio_max_residual": item.flux_ratio_max_residual,
                "clipped_count": item.clipped_count,
                "clipped_fraction": item.clipped_fraction,
                "worst_residual_bins": [dict(bin_item) for bin_item in item.worst_residual_bins],
                "clipped_bins": [dict(bin_item) for bin_item in item.clipped_bins],
                "converged": item.converged,
            }
            for item in report.convergence
        ],
        "final_solve": (
            None
            if report.final_solve is None
            else {
                "iteration": report.final_solve.iteration,
                "result": str(report.final_solve.result),
                "returncode": report.final_solve.returncode,
                "keff": report.final_solve.keff,
                "flux_vector_count": report.final_solve.flux_vector_count,
                "flux_unknown_count": report.final_solve.flux_unknown_count,
            }
        ),
        "workflows": [
            {
                "iteration": index + 1,
                "summary_json": str(workflow.summary_json),
                "donjon_volume_flux_h5": str(workflow.donjon_volume_flux_h5),
                "sph_sidecar": str(workflow.sph_sidecar),
                "augmented_h5": str(workflow.augmented_h5),
                "ascii_output": str(workflow.ascii_output),
                "sph_minimum": workflow.sph_minimum,
                "sph_maximum": workflow.sph_maximum,
                "flux_normalization": workflow.flux_normalization,
                "normalization_factor": workflow.normalization_factor,
            }
            for index, workflow in enumerate(report.workflows)
        ],
        "postprocesses": [
            {
                "iteration": postprocess.iteration,
                "command": list(postprocess.command),
                "cwd": str(postprocess.cwd),
                "workflow_ascii": str(postprocess.workflow_ascii),
                "output": str(postprocess.output),
                "sph_sidecar": str(postprocess.sph_sidecar),
                "stdout": str(postprocess.stdout),
                "stderr": str(postprocess.stderr),
                "returncode": postprocess.returncode,
                "output_bytes": postprocess.output_bytes,
                "block_count": postprocess.block_count,
            }
            for postprocess in report.postprocesses
        ],
        "audit_rows": [
            {
                "stage": row.stage,
                "iteration": row.iteration,
                "keff": row.keff,
                "sph_minimum": row.sph_minimum,
                "sph_maximum": row.sph_maximum,
                "sph_max_abs_change": row.sph_max_abs_change,
                "sph_max_rel_change": row.sph_max_rel_change,
                "flux_ratio_max_residual": row.flux_ratio_max_residual,
                "worst_residual_mixture": row.worst_residual_mixture,
                "worst_residual_group": row.worst_residual_group,
                "worst_residual_raw_update": row.worst_residual_raw_update,
                "worst_residual": row.worst_residual,
                "converged": row.converged,
                "solve_result": None if row.solve_result is None else str(row.solve_result),
                "ascii_output": None if row.ascii_output is None else str(row.ascii_output),
                "postprocess_output": (
                    None
                    if row.postprocess_output is None
                    else str(row.postprocess_output)
                ),
            }
            for row in report.audit_rows
        ],
        "acceptance": {
            "enabled": report.acceptance.enabled,
            "passed": report.acceptance.passed,
            "fail_on_violation": report.acceptance.fail_on_violation,
            "decision": report.acceptance.decision,
            "checks": [
                {
                    "name": item.name,
                    "actual": item.actual,
                    "limit": item.limit,
                    "units": item.units,
                    "passed": item.passed,
                    "message": item.message,
                }
                for item in report.acceptance.checks
            ],
        },
        "openmc_xs_policy": "fixed base MGXS; DONJON solves consume updated ASCII SPH handoffs",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _artifact_metadata_payload(
    metadata: SphLoopArtifactMetadata,
) -> dict[str, Any]:
    return {
        "reference_flux": _dataset_metadata_payload(metadata.reference_flux),
        "workflows": [
            _workflow_metadata_payload(item) for item in metadata.workflows
        ],
        "final_sph_sidecar": (
            None
            if metadata.final_sph_sidecar is None
            else _dataset_metadata_payload(metadata.final_sph_sidecar)
        ),
    }


def _workflow_metadata_payload(
    metadata: SphLoopWorkflowMetadata,
) -> dict[str, Any]:
    return {
        "iteration": metadata.iteration,
        "donjon_volume_flux": _dataset_metadata_payload(
            metadata.donjon_volume_flux
        ),
        "sph_sidecar": _dataset_metadata_payload(metadata.sph_sidecar),
    }


def _dataset_metadata_payload(metadata: Hdf5DatasetMetadata) -> dict[str, Any]:
    return {
        "requested_source": metadata.requested_source,
        "source": metadata.source,
        "path": str(metadata.path),
        "dataset": metadata.dataset,
        "shape": list(metadata.shape),
        "group_order": metadata.group_order,
        "energy_groups": metadata.energy_groups,
        "mixture_count": len(metadata.mixture_names),
        "mixture_names": list(metadata.mixture_names),
        "std_dev_source": metadata.std_dev_source,
        "std_dev_dataset": metadata.std_dev_dataset,
        "std_dev_shape": (
            None if metadata.std_dev_shape is None else list(metadata.std_dev_shape)
        ),
        "std_dev_max_rel": metadata.std_dev_max_rel,
        "std_dev_worst": metadata.std_dev_worst,
    }


def _production_audit_payload(report: SphLoopReport) -> dict[str, Any]:
    return build_production_audit_payload(
        flux_map_preflight=report.flux_map_preflight,
        artifact_metadata=report.artifact_metadata,
        solve_count=len(report.solves),
        postprocess_count=len(report.postprocesses),
    )


def write_bundle(
    report: SphLoopReport,
    *,
    output_dir: Path,
    manifest_name: str,
    force: bool,
) -> None:
    artifacts = [
        ArtifactSpec(label="sph-loop-config", source=report.config_path),
        ArtifactSpec(label="sph-input-h5", source=report.input_h5),
        ArtifactSpec(label="sph-loop-final-ascii", source=report.final_ascii),
        ArtifactSpec(label="sph-loop-summary", source=report.summary_json),
        ArtifactSpec(label="sph-loop-audit-csv", source=report.audit_csv),
        ArtifactSpec(label="sph-loop-audit-text", source=report.audit_text),
    ]
    if report.run_script is not None:
        artifacts.insert(
            1,
            ArtifactSpec(label="sph-loop-run-script", source=report.run_script),
        )
    if report.final_sph_sidecar is not None:
        artifacts.insert(
            3,
            ArtifactSpec(
                label="sph-loop-final-sph-sidecar",
                source=report.final_sph_sidecar,
            ),
        )
    bundle_artifacts(
        output_dir=output_dir,
        artifacts=artifacts,
        manifest_name=manifest_name,
        force=force,
    )


def _quality_payload(report: SphLoopReport) -> dict[str, Any]:
    if not report.convergence:
        return {
            "initial_flux_ratio_max_residual": None,
            "final_flux_ratio_max_residual": None,
            "final_to_initial_flux_residual_ratio": None,
            "flux_residual_improved": None,
            "final_clipped_count": None,
            "final_clipped_fraction": None,
            "maximum_clipped_count": None,
            "maximum_clipped_fraction": None,
            "clipping_observed": None,
            "final_sph_minimum": None,
            "final_sph_maximum": None,
            "initial_worst_residual_bin": None,
            "final_worst_residual_bin": None,
            "final_worst_residual_bins": [],
            "final_clipped_bins": [],
        }

    initial = float(report.convergence[0].flux_ratio_max_residual)
    final = float(report.convergence[-1].flux_ratio_max_residual)
    final_item = report.convergence[-1]
    final_workflow = report.workflows[-1] if report.workflows else None
    maximum_clipped_count = max(item.clipped_count for item in report.convergence)
    maximum_clipped_fraction = max(
        item.clipped_fraction for item in report.convergence
    )
    ratio = 0.0 if final == 0.0 else final / max(abs(initial), 1.0e-30)
    return {
        "initial_flux_ratio_max_residual": initial,
        "final_flux_ratio_max_residual": final,
        "final_to_initial_flux_residual_ratio": ratio,
        "flux_residual_improved": final <= initial,
        "final_clipped_count": int(final_item.clipped_count),
        "final_clipped_fraction": float(final_item.clipped_fraction),
        "maximum_clipped_count": int(maximum_clipped_count),
        "maximum_clipped_fraction": float(maximum_clipped_fraction),
        "clipping_observed": maximum_clipped_count > 0,
        "final_sph_minimum": (
            None if final_workflow is None else final_workflow.sph_minimum
        ),
        "final_sph_maximum": (
            None if final_workflow is None else final_workflow.sph_maximum
        ),
        "initial_worst_residual_bin": first_diagnostic_bin(
            report.convergence[0].worst_residual_bins
        ),
        "final_worst_residual_bin": first_diagnostic_bin(
            final_item.worst_residual_bins
        ),
        "final_worst_residual_bins": [
            dict(item) for item in final_item.worst_residual_bins
        ],
        "final_clipped_bins": [dict(item) for item in final_item.clipped_bins],
    }
