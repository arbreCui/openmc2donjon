"""Build OpenMC-side SPH sidecars from CE/MG flux comparisons."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from . import __version__
from .sph_augment import SphSidecarReport, create_table_sph_sidecar
from .sph_iteration import SphUpdateTableReport, create_sph_update_table


SCHEMA = "openmc2donjon.openmc-sph-sidecar.v1"
PASS_DECISION = "openmc2donjon_openmc_sph_sidecar_passed"


@dataclass(frozen=True)
class OpenmcSphSidecarReport:
    input_h5: Path
    output_h5: Path
    output_table: Path
    reference_flux: str | Path
    mg_flux: str | Path
    update: SphUpdateTableReport
    sidecar: SphSidecarReport


def create_openmc_sph_sidecar(
    input_h5: Path,
    output_h5: Path,
    *,
    reference_flux: str | Path,
    mg_flux: str | Path,
    table_output: Path | None = None,
    previous_sph: str | Path | None = None,
    damping: float = 1.0,
    clip_min: float | None = None,
    clip_max: float | None = None,
    flux_normalization: str = "none",
    sph_target: str = "flux",
    zero_flux_policy: str = "reject",
    flux_floor_rel: float | None = None,
    freeze_groups: tuple[int, ...] | None = None,
    require_reference_flux_std_dev: bool = False,
    max_reference_flux_std_dev_rel: float | None = None,
    require_mg_flux_std_dev: bool = False,
    max_mg_flux_std_dev_rel: float | None = None,
    source_label: str = "openmc-ce-mg-sph",
    sph_kind: str = "openmc-ce-mg",
    sph_real: bool = True,
    sph_applied: bool = False,
    force: bool = False,
    summary_json: Path | None = None,
) -> OpenmcSphSidecarReport:
    """Compute OpenMC CE/MG SPH factors and write a sidecar HDF5.

    ``reference_flux`` is the OpenMC continuous-energy reference flux and
    ``mg_flux`` is the OpenMC multi-group macro flux. Both must use the same
    geometry, mixture ordering, and energy-group order as ``input_h5``.
    """

    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    output_table = (
        Path(table_output)
        if table_output is not None
        else output_h5.with_suffix(".sph.csv")
    )
    if output_table == output_h5:
        raise ValueError("--table-output must be different from --output")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")

    update = create_sph_update_table(
        input_h5,
        output_table,
        reference_flux=reference_flux,
        low_order_flux=mg_flux,
        previous_sph=previous_sph,
        damping=damping,
        clip_min=clip_min,
        clip_max=clip_max,
        flux_normalization=flux_normalization,
        sph_target=sph_target,
        zero_flux_policy=zero_flux_policy,
        flux_floor_rel=flux_floor_rel,
        freeze_groups=freeze_groups,
        require_reference_flux_std_dev=require_reference_flux_std_dev,
        max_reference_flux_std_dev_rel=max_reference_flux_std_dev_rel,
        require_low_order_flux_std_dev=require_mg_flux_std_dev,
        max_low_order_flux_std_dev_rel=max_mg_flux_std_dev_rel,
        source_label=source_label,
        force=force,
        summary_json=None,
    )
    sidecar = create_table_sph_sidecar(
        input_h5,
        output_h5,
        table=output_table,
        force=force,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        summary_json=None,
    )
    report = OpenmcSphSidecarReport(
        input_h5=input_h5,
        output_h5=output_h5,
        output_table=output_table,
        reference_flux=reference_flux,
        mg_flux=mg_flux,
        update=update,
        sidecar=sidecar,
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: OpenmcSphSidecarReport) -> None:
    print("OpenMC CE/MG SPH sidecar")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output: {report.output_h5}")
    print(f"  table: {report.output_table}")
    print(f"  reference_flux: {report.reference_flux}")
    print(f"  mg_flux: {report.mg_flux}")
    print(
        f"  mixtures={len(report.sidecar.mixture_names)} "
        f"groups={report.sidecar.energy_groups} "
        f"sph_range={report.sidecar.sph_min:g}..{report.sidecar.sph_max:g} "
        f"clipped={report.update.clipped_count}"
    )
    print()
    print("OpenMC SPH sidecar decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: OpenmcSphSidecarReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "input_h5": str(report.input_h5),
        "output_h5": str(report.output_h5),
        "output_table": str(report.output_table),
        "reference_flux": str(report.reference_flux),
        "reference_flux_dataset": report.update.reference_flux_dataset,
        "reference_flux_std_dev_dataset": report.update.reference_flux_std_dev_dataset,
        "reference_flux_max_relative_std_dev": (
            report.update.reference_flux_max_relative_std_dev
        ),
        "mg_flux": str(report.mg_flux),
        "mg_flux_dataset": report.update.low_order_flux_dataset,
        "mg_flux_std_dev_dataset": report.update.low_order_flux_std_dev_dataset,
        "mg_flux_max_relative_std_dev": report.update.low_order_flux_max_relative_std_dev,
        "previous_sph": None
        if report.update.previous_sph_source is None
        else str(report.update.previous_sph_source),
        "previous_sph_dataset": report.update.previous_sph_dataset,
        "mixture_count": len(report.sidecar.mixture_names),
        "mixture_names": list(report.sidecar.mixture_names),
        "energy_groups": report.sidecar.energy_groups,
        "damping": report.update.damping,
        "clip_min": report.update.clip_min,
        "clip_max": report.update.clip_max,
        "flux_normalization": report.update.flux_normalization,
        "sph_target": report.update.sph_target,
        "zero_flux_policy": report.update.zero_flux_policy,
        "identity_bin_count": report.update.identity_bin_count,
        "flux_floor_rel": report.update.flux_floor_rel,
        "floored_bin_count": report.update.floored_bin_count,
        "freeze_groups": None
        if report.update.freeze_groups is None
        else list(report.update.freeze_groups),
        "frozen_group_bin_count": report.update.frozen_group_bin_count,
        "normalization_factor": report.update.normalization_factor,
        "sph_min": report.sidecar.sph_min,
        "sph_max": report.sidecar.sph_max,
        "sph_kind": report.sidecar.sph_kind,
        "sph_real": report.sidecar.sph_real,
        "sph_applied": report.sidecar.sph_applied,
        "raw_update_minimum": report.update.raw_update_minimum,
        "raw_update_maximum": report.update.raw_update_maximum,
        "clipped_count": report.update.clipped_count,
        "source_label": report.update.source_label,
        "formula": (
            "sph = previous_sph * "
            "(normalized_openmc_mg_flux / (previous_sph * openmc_ce_reference_flux)) "
            "** damping"
            if report.update.sph_target == "rate"
            else "sph = previous_sph * "
            "(openmc_ce_reference_flux / normalized_openmc_mg_flux) ** damping"
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
