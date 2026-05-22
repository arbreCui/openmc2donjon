"""Artifact metadata collection for SPH loop reports."""

from __future__ import annotations

from pathlib import Path

from .hdf5_metadata import read_hdf5_dataset_metadata
from .sph_loop_records import SphLoopArtifactMetadata, SphLoopWorkflowMetadata
from .sph_workflow import SphIterationWorkflowReport


def collect_artifact_metadata(
    *,
    reference_flux: str,
    workflows: tuple[SphIterationWorkflowReport, ...],
    final_sph_sidecar: Path | None,
) -> SphLoopArtifactMetadata:
    """Collect mixture-order and group-order metadata for loop artifacts."""

    workflow_metadata = tuple(
        SphLoopWorkflowMetadata(
            iteration=index,
            donjon_volume_flux=read_hdf5_dataset_metadata(
                f"{workflow.donjon_volume_flux_h5}::donjon_volume_flux",
                default_datasets=("donjon_volume_flux", "volume_flux"),
            ),
            sph_sidecar=read_hdf5_dataset_metadata(
                f"{workflow.sph_sidecar}::sph",
                default_datasets=("sph",),
            ),
        )
        for index, workflow in enumerate(workflows, start=1)
    )
    return SphLoopArtifactMetadata(
        reference_flux=read_hdf5_dataset_metadata(
            reference_flux,
            default_datasets=("openmc_volume_flux", "reference_flux", "volume_flux"),
        ),
        workflows=workflow_metadata,
        final_sph_sidecar=(
            None
            if final_sph_sidecar is None
            else read_hdf5_dataset_metadata(
                f"{final_sph_sidecar}::sph",
                default_datasets=("sph",),
            )
        ),
    )
