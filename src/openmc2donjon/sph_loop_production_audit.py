"""Production audit checks for fixed-OpenMC SPH loop artifacts."""

from __future__ import annotations

from typing import Any, Protocol

from .constants import MGXS_DONJON_GROUP_ORDER


OPENMC_XS_POLICY = "fixed base MGXS; only SPH/NSPH factors are iterated"


class FluxMapPreflightLike(Protocol):
    passed: bool
    map_kind: str
    mixture_names: tuple[str, ...]
    energy_groups: int
    mgxs_declared_mixture_order: bool
    mgxs_source_domain_indices: tuple[int | None, ...]
    mgxs_source_domain_order_errors: tuple[str, ...]
    scalar_flux_ids: tuple[int, ...]
    minimum_required_flux_unknown_count: int | None
    mixture_flux_map: tuple[tuple[str, int], ...]


class DatasetMetadataLike(Protocol):
    source: str
    group_order: str | None
    mixture_names: tuple[str, ...]
    energy_groups: int | None


class WorkflowMetadataLike(Protocol):
    iteration: int
    donjon_volume_flux: DatasetMetadataLike
    sph_sidecar: DatasetMetadataLike


class ArtifactMetadataLike(Protocol):
    reference_flux: DatasetMetadataLike
    workflows: tuple[WorkflowMetadataLike, ...]
    final_sph_sidecar: DatasetMetadataLike | None


def build_production_audit_payload(
    *,
    flux_map_preflight: FluxMapPreflightLike,
    artifact_metadata: ArtifactMetadataLike,
    solve_count: int = 0,
    postprocess_count: int = 0,
) -> dict[str, Any]:
    checks: list[dict[str, object]] = []
    reference = artifact_metadata.reference_flux
    reference_names = tuple(reference.mixture_names)
    reference_groups = reference.energy_groups
    expected_names = tuple(flux_map_preflight.mixture_names)
    expected_groups = flux_map_preflight.energy_groups
    mgxs_domain_order_errors = tuple(
        getattr(flux_map_preflight, "mgxs_source_domain_order_errors", ())
    )

    _append_audit_check(
        checks,
        "flux_map_preflight_passed",
        flux_map_preflight.passed,
        "flux map preflight passed",
        "flux map preflight failed",
    )
    _append_audit_check(
        checks,
        "reference_group_order",
        reference.group_order == MGXS_DONJON_GROUP_ORDER,
        f"reference_flux group_order={reference.group_order!r}",
        (
            f"reference_flux group_order {reference.group_order!r} "
            f"!= {MGXS_DONJON_GROUP_ORDER!r}"
        ),
    )
    _append_audit_check(
        checks,
        "reference_mixture_order",
        reference_names == expected_names,
        "reference_flux mixture_names match MGXS mixture order",
        "reference_flux mixture_names do not match MGXS mixture order",
    )
    _append_audit_check(
        checks,
        "reference_energy_groups",
        reference_groups == expected_groups,
        "reference_flux energy group count matches MGXS",
        f"reference_flux energy_groups {reference_groups!r} != {expected_groups!r}",
    )
    _append_audit_check(
        checks,
        "mgxs_mixture_order_declared",
        bool(getattr(flux_map_preflight, "mgxs_declared_mixture_order", False)),
        "MGXS declares /mixture_names order",
        "MGXS does not declare /mixture_names order",
    )
    _append_audit_check(
        checks,
        "mgxs_source_domain_order",
        not mgxs_domain_order_errors,
        "MGXS source_domain_index values match /mixture_names order",
        "; ".join(mgxs_domain_order_errors)
        or "MGXS source_domain_index contract unavailable",
    )

    for workflow in artifact_metadata.workflows:
        label = f"iter{workflow.iteration}"
        _append_dataset_audit_checks(
            checks,
            f"{label}_donjon_volume_flux",
            workflow.donjon_volume_flux,
            reference_names=reference_names,
            reference_groups=reference_groups,
        )
        _append_dataset_audit_checks(
            checks,
            f"{label}_sph_sidecar",
            workflow.sph_sidecar,
            reference_names=reference_names,
            reference_groups=reference_groups,
        )

    final_sidecar = artifact_metadata.final_sph_sidecar
    _append_audit_check(
        checks,
        "final_sph_sidecar_present",
        final_sidecar is not None or not artifact_metadata.workflows,
        "final SPH sidecar metadata present",
        "final SPH sidecar metadata missing",
    )
    if final_sidecar is not None:
        _append_dataset_audit_checks(
            checks,
            "final_sph_sidecar",
            final_sidecar,
            reference_names=reference_names,
            reference_groups=reference_groups,
        )

    errors = tuple(str(item["message"]) for item in checks if not item["passed"])
    return {
        "passed": not errors,
        "errors": list(errors),
        "checks": checks,
        "openmc_xs_policy": OPENMC_XS_POLICY,
        "reference": {
            "source": getattr(reference, "source", None),
            "group_order": reference.group_order,
            "energy_groups": reference.energy_groups,
            "mixture_names": list(reference.mixture_names),
            "std_dev_source": getattr(reference, "std_dev_source", None),
            "std_dev_dataset": getattr(reference, "std_dev_dataset", None),
            "std_dev_max_rel": getattr(reference, "std_dev_max_rel", None),
            "std_dev_worst": getattr(reference, "std_dev_worst", None),
        },
        "flux_map": {
            "passed": flux_map_preflight.passed,
            "map_kind": flux_map_preflight.map_kind,
            "scalar_flux_ids": list(flux_map_preflight.scalar_flux_ids),
            "minimum_required_flux_unknown_count": (
                flux_map_preflight.minimum_required_flux_unknown_count
            ),
            "mixture_flux_map": [
                {"mixture": mixture, "scalar_flux_id": scalar_id}
                for mixture, scalar_id in flux_map_preflight.mixture_flux_map
            ],
            "mgxs_declared_mixture_order": bool(
                getattr(flux_map_preflight, "mgxs_declared_mixture_order", False)
            ),
            "mgxs_source_domain_indices": list(
                getattr(flux_map_preflight, "mgxs_source_domain_indices", ())
            ),
            "mgxs_source_domain_order_errors": list(mgxs_domain_order_errors),
        },
        "artifact_counts": {
            "workflows": len(artifact_metadata.workflows),
            "solves": solve_count,
            "postprocesses": postprocess_count,
        },
    }


def _append_dataset_audit_checks(
    checks: list[dict[str, object]],
    label: str,
    metadata: DatasetMetadataLike,
    *,
    reference_names: tuple[str, ...],
    reference_groups: int | None,
) -> None:
    _append_audit_check(
        checks,
        f"{label}_group_order",
        metadata.group_order == MGXS_DONJON_GROUP_ORDER,
        f"{label} group_order={metadata.group_order!r}",
        f"{label} group_order {metadata.group_order!r} != {MGXS_DONJON_GROUP_ORDER!r}",
    )
    _append_audit_check(
        checks,
        f"{label}_mixture_order",
        tuple(metadata.mixture_names) == reference_names,
        f"{label} mixture_names match reference_flux",
        f"{label} mixture_names do not match reference_flux",
    )
    _append_audit_check(
        checks,
        f"{label}_energy_groups",
        metadata.energy_groups == reference_groups,
        f"{label} energy_groups={metadata.energy_groups!r}",
        f"{label} energy_groups {metadata.energy_groups!r} != {reference_groups!r}",
    )


def _append_audit_check(
    checks: list[dict[str, object]],
    name: str,
    passed: bool,
    pass_message: str,
    fail_message: str,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "message": pass_message if passed else fail_message,
        }
    )
