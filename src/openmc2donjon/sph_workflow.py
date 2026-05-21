"""Production SPH iteration workflow from DONJON flux dumps."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from . import __version__
from .donjon_flux import DonjonVolumeFluxReport, extract_donjon_volume_flux
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .sph_augment import (
    SphAugmentReport,
    SphSidecarReport,
    augment_hdf5_with_sph,
    create_table_sph_sidecar,
)
from .sph_iteration import SphUpdateTableReport, create_sph_update_table


SCHEMA = "openmc2donjon.sph-iteration-workflow.v1"
PASS_DECISION = "openmc2donjon_sph_iteration_workflow_passed"


@dataclass(frozen=True)
class SphIterationWorkflowReport:
    input_h5: Path
    output_dir: Path
    reference_flux: str
    flux_dump: Path
    map_h5: Path | None
    previous_sph: str | None
    output_format: str
    donjon_volume_flux_h5: Path
    sph_table: Path
    sph_sidecar: Path
    augmented_h5: Path
    ascii_output: Path
    summary_json: Path
    mixture_count: int
    energy_groups: int
    damping: float
    sph_minimum: float
    sph_maximum: float


def run_sph_iteration_workflow(
    input_h5: str | Path,
    output_dir: str | Path,
    *,
    reference_flux: str | Path,
    flux_dump: str | Path,
    map_h5: str | Path | None = None,
    scalar_flux_ids: dict[str, int] | None = None,
    scalar_flux_column: int = 0,
    list_offset: int = 0,
    previous_sph: str | Path | None = None,
    damping: float = 1.0,
    clip_min: float | None = None,
    clip_max: float | None = None,
    output_format: str = "macrolib",
    root_name: str = DEFAULT_ROOT_NAME,
    h_factor_default: float | None = None,
    sph_kind: str = "sph-iteration",
    sph_real: bool = True,
    sph_applied: bool = False,
    source_label: str = "DONJON low-order SPH iteration workflow",
    force: bool = False,
    summary_json: str | Path | None = None,
) -> SphIterationWorkflowReport:
    """Run one fixed-OpenMC SPH update from a DONJON ``L_FLUX`` dump.

    The OpenMC MGXS file is treated as the immutable base.  This workflow
    extracts the DONJON volume flux, computes the next SPH factors, writes a
    sidecar, injects the sidecar into a copy of the base MGXS, and converts the
    augmented handoff to DONJON ASCII.
    """

    input_path = Path(input_h5)
    output_root = Path(output_dir)
    flux_dump_path = Path(flux_dump)
    map_path = None if map_h5 is None else Path(map_h5)
    previous_sph_ref = None if previous_sph is None else str(previous_sph)
    summary_path = (
        output_root / "sph_iteration_workflow_summary.json"
        if summary_json is None
        else Path(summary_json)
    )
    if output_format not in {"macrolib", "multicompo"}:
        raise ValueError("output_format must be 'macrolib' or 'multicompo'")

    output_root.mkdir(parents=True, exist_ok=True)
    paths = _workflow_paths(output_root, output_format)
    _check_outputs(paths, summary_path, force=force)

    donjon_report = extract_donjon_volume_flux(
        input_path,
        flux_dump_path,
        paths["donjon_volume_flux"],
        map_h5=map_path,
        scalar_flux_ids=scalar_flux_ids,
        scalar_flux_column=scalar_flux_column,
        list_offset=list_offset,
        source_label=f"{source_label}: DONJON flux extraction",
        force=force,
        summary_json=paths["donjon_volume_flux_summary"],
    )
    sph_report = create_sph_update_table(
        input_path,
        paths["sph_table"],
        reference_flux=reference_flux,
        low_order_flux=f"{paths['donjon_volume_flux']}::donjon_volume_flux",
        previous_sph=previous_sph,
        damping=damping,
        clip_min=clip_min,
        clip_max=clip_max,
        source_label=source_label,
        force=force,
        summary_json=paths["sph_table_summary"],
    )
    sidecar_report = create_table_sph_sidecar(
        input_path,
        paths["sph_sidecar"],
        table=paths["sph_table"],
        force=force,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        summary_json=paths["sph_sidecar_summary"],
    )
    augment_report = augment_hdf5_with_sph(
        input_path,
        sph_source=paths["sph_sidecar"],
        output_h5=paths["augmented_h5"],
        force=force,
        sph_kind=sph_kind,
        sph_real=sph_real,
        sph_applied=sph_applied,
        sph_source_label=source_label,
        summary_json=paths["sph_augment_summary"],
    )
    if output_format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            paths["augmented_h5"],
            paths["ascii_output"],
            h_factor_default=h_factor_default,
        )
    else:
        convert_mgxs_hdf5(
            paths["augmented_h5"],
            paths["ascii_output"],
            root_name=root_name,
            comment=f"SPH iteration workflow from {input_path.name}",
            h_factor_default=h_factor_default,
        )

    report = _build_report(
        input_path=input_path,
        output_root=output_root,
        reference_flux=str(reference_flux),
        flux_dump_path=flux_dump_path,
        map_path=map_path,
        previous_sph=previous_sph_ref,
        output_format=output_format,
        paths=paths,
        summary_path=summary_path,
        donjon_report=donjon_report,
        sph_report=sph_report,
        sidecar_report=sidecar_report,
        augment_report=augment_report,
    )
    print_report(report)
    write_summary(summary_path, report)
    return report


def print_report(report: SphIterationWorkflowReport) -> None:
    print("OpenMC-to-DONJON SPH iteration workflow")
    print(f"  schema: {SCHEMA}")
    print(f"  input: {report.input_h5}")
    print(f"  output_dir: {report.output_dir}")
    print(f"  reference_flux: {report.reference_flux}")
    print(f"  flux_dump: {report.flux_dump}")
    if report.map_h5 is not None:
        print(f"  map_h5: {report.map_h5}")
    if report.previous_sph is not None:
        print(f"  previous_sph: {report.previous_sph}")
    print(
        f"  mixtures={report.mixture_count} groups={report.energy_groups} "
        f"damping={report.damping:g} format={report.output_format}"
    )
    print(
        f"  outputs: flux={report.donjon_volume_flux_h5.name} "
        f"sph={report.sph_sidecar.name} ascii={report.ascii_output.name}"
    )
    print(f"  SPH range: {report.sph_minimum:g}..{report.sph_maximum:g}")
    print()
    print("SPH iteration workflow decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SphIterationWorkflowReport) -> None:
    payload = {
        "schema": SCHEMA,
        "decision": PASS_DECISION,
        "package_version": __version__,
        "input_h5": str(report.input_h5),
        "output_dir": str(report.output_dir),
        "reference_flux": report.reference_flux,
        "flux_dump": str(report.flux_dump),
        "map_h5": None if report.map_h5 is None else str(report.map_h5),
        "previous_sph": report.previous_sph,
        "output_format": report.output_format,
        "donjon_volume_flux_h5": str(report.donjon_volume_flux_h5),
        "sph_table": str(report.sph_table),
        "sph_sidecar": str(report.sph_sidecar),
        "augmented_h5": str(report.augmented_h5),
        "ascii_output": str(report.ascii_output),
        "summary_json": str(report.summary_json),
        "mixture_count": report.mixture_count,
        "energy_groups": report.energy_groups,
        "damping": report.damping,
        "sph_minimum": report.sph_minimum,
        "sph_maximum": report.sph_maximum,
        "formula": "next_sph = previous_sph * (reference_flux / donjon_low_order_flux) ** damping",
        "openmc_xs_policy": "fixed base MGXS; only SPH sidecar changes between iterations",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _workflow_paths(output_dir: Path, output_format: str) -> dict[str, Path]:
    suffix = "macrolib.txt" if output_format == "macrolib" else "mcompo.txt"
    return {
        "donjon_volume_flux": output_dir / "donjon_volume_flux.h5",
        "donjon_volume_flux_summary": output_dir / "donjon_volume_flux_summary.json",
        "sph_table": output_dir / "next_sph.csv",
        "sph_table_summary": output_dir / "next_sph_summary.json",
        "sph_sidecar": output_dir / "next_sph.sidecar.h5",
        "sph_sidecar_summary": output_dir / "next_sph_sidecar_summary.json",
        "augmented_h5": output_dir / "mgxs_with_sph.h5",
        "sph_augment_summary": output_dir / "sph_augment_summary.json",
        "ascii_output": output_dir / f"out.{suffix}",
    }


def _check_outputs(paths: dict[str, Path], summary_path: Path, *, force: bool) -> None:
    if force:
        return
    existing = [path for path in [*paths.values(), summary_path] if path.exists()]
    if existing:
        rendered = ", ".join(str(path) for path in existing[:5])
        if len(existing) > 5:
            rendered += ", ..."
        raise FileExistsError(f"workflow output already exists; use --force: {rendered}")


def _build_report(
    *,
    input_path: Path,
    output_root: Path,
    reference_flux: str,
    flux_dump_path: Path,
    map_path: Path | None,
    previous_sph: str | None,
    output_format: str,
    paths: dict[str, Path],
    summary_path: Path,
    donjon_report: DonjonVolumeFluxReport,
    sph_report: SphUpdateTableReport,
    sidecar_report: SphSidecarReport,
    augment_report: SphAugmentReport,
) -> SphIterationWorkflowReport:
    if sidecar_report.mixture_names != augment_report.mixture_names:
        raise ValueError("internal workflow error: sidecar/augment mixture mismatch")
    return SphIterationWorkflowReport(
        input_h5=input_path,
        output_dir=output_root,
        reference_flux=reference_flux,
        flux_dump=flux_dump_path,
        map_h5=map_path,
        previous_sph=previous_sph,
        output_format=output_format,
        donjon_volume_flux_h5=paths["donjon_volume_flux"],
        sph_table=paths["sph_table"],
        sph_sidecar=paths["sph_sidecar"],
        augmented_h5=paths["augmented_h5"],
        ascii_output=paths["ascii_output"],
        summary_json=summary_path,
        mixture_count=len(donjon_report.mixture_names),
        energy_groups=donjon_report.energy_groups,
        damping=sph_report.damping,
        sph_minimum=sidecar_report.sph_min,
        sph_maximum=sidecar_report.sph_max,
    )
