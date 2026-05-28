"""Summarize the CE/MG OpenMC-side SPH minicase outputs.

The report is intentionally small and auditable.  It does not decide whether
the minicase is a benchmark; it records what happened in one run:

* CE and MG flux uncertainty levels,
* SPH factor ranges by mixture,
* whether the augmented HDF5 and ASCII handoffs carry NSPH data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


SUMMARY_SCHEMA = "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1"
PRODUCTION_FLUX_REL_STD_DEV = 0.05
DEMONSTRATION_FLUX_REL_STD_DEV = 0.30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--handoff-dir",
        type=Path,
        required=True,
        help="directory produced by run_workflow.sh",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="summary JSON path (default: <handoff-dir>/physics_summary.json)",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Markdown report path (default: <handoff-dir>/physics_summary.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handoff_dir = args.handoff_dir.resolve()
    summary = summarize_handoff(handoff_dir)

    json_path = args.output_json or handoff_dir / "physics_summary.json"
    md_path = args.output_md or handoff_dir / "physics_summary.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(summary), encoding="utf-8")

    print(f"wrote physics summary JSON: {json_path}")
    print(f"wrote physics summary Markdown: {md_path}")
    return 0


def summarize_handoff(handoff_dir: Path) -> dict[str, Any]:
    paths = {
        "mgxs": handoff_dir / "mgxs_library.h5",
        "augmented_mgxs": handoff_dir / "mgxs_with_openmc_sph.h5",
        "ce_flux": handoff_dir / "openmc_ce_flux.h5",
        "mg_flux": handoff_dir / "openmc_mg_flux.h5",
        "sph_sidecar": handoff_dir / "openmc_sph_sidecar.h5",
        "sph_summary": handoff_dir / "openmc_sph_summary.json",
        "augment_summary": handoff_dir / "sph_augment_summary.json",
        "mg_macro_summary": handoff_dir / "mg_macro_summary.json",
        "multicompo_ascii": handoff_dir / "out_with_openmc_sph.mcompo.txt",
        "macrolib_ascii": handoff_dir / "out_with_openmc_sph.macrolib.txt",
    }
    _require_paths({name: path for name, path in paths.items() if name != "mg_macro_summary"})

    sph_summary = _read_json(paths["sph_summary"])
    augment_summary = _read_json(paths["augment_summary"])
    mg_macro_summary = (
        _read_json(paths["mg_macro_summary"])
        if paths["mg_macro_summary"].exists()
        else {"scatter_format": "unknown"}
    )
    mixture_names = _read_mixture_names(paths["augmented_mgxs"])
    energy_groups, legendre_order = _read_mgxs_shape(paths["mgxs"])
    ce_flux, ce_std = _read_flux(paths["ce_flux"], "openmc_volume_flux")
    mg_flux, mg_std = _read_flux(paths["mg_flux"], "openmc_mg_flux")
    ce_flux_rel_std = _max_relative_std_dev(ce_flux, ce_std)
    mg_flux_rel_std = _max_relative_std_dev(mg_flux, mg_std)
    sph = _read_sph(paths["augmented_mgxs"], mixture_names)
    normalization_factor = float(sph_summary.get("normalization_factor", 1.0))
    normalized_mg_flux = mg_flux * normalization_factor
    flux_ratio = normalized_mg_flux / ce_flux
    multicompo_nsp_block_count = _count_ascii_block(paths["multicompo_ascii"], "NSPH")
    macrolib_nsp_block_count = _count_ascii_block(paths["macrolib_ascii"], "NSPH")
    augmented_has_sph = _augmented_hdf5_has_sph(paths["augmented_mgxs"], mixture_names)
    sph_iterations = _read_sph_iterations(handoff_dir, sph_summary)

    return {
        "schema": SUMMARY_SCHEMA,
        "route": "OpenMC CE reference + OpenMC MG same geometry -> OpenMC-side SPH",
        "handoff_dir": str(handoff_dir),
        "mixture_count": len(mixture_names),
        "energy_groups": energy_groups,
        "legendre_order": legendre_order,
        "handoff_scatter": {
            "format": "legendre",
            "legendre_order": legendre_order,
        },
        "mg_macro_scatter": mg_macro_summary,
        "mixture_names": mixture_names,
        "decisions": {
            "openmc_sph": sph_summary.get("decision"),
            "sph_augment": augment_summary.get("decision"),
        },
        "normalization": {
            "method": sph_summary.get("flux_normalization"),
            "factor": normalization_factor,
            "formula": sph_summary.get("formula"),
        },
        "flux_uncertainty": {
            "ce_max_relative_std_dev": ce_flux_rel_std,
            "mg_max_relative_std_dev": mg_flux_rel_std,
            "ce_dataset": "openmc_volume_flux",
            "mg_dataset": "openmc_mg_flux",
        },
        "quality": _quality_summary(
            ce_flux_rel_std=ce_flux_rel_std,
            mg_flux_rel_std=mg_flux_rel_std,
            augmented_hdf5_has_sph=augmented_has_sph,
            multicompo_nsp_block_count=multicompo_nsp_block_count,
            macrolib_nsp_block_count=macrolib_nsp_block_count,
        ),
        "sph": {
            "kind": sph_summary.get("sph_kind"),
            "real": bool(sph_summary.get("sph_real")),
            "applied_to_xs": bool(augment_summary.get("sph_applied")),
            "minimum": float(np.min(sph)),
            "maximum": float(np.max(sph)),
            "mean": float(np.mean(sph)),
            "max_abs_delta_from_unity": float(np.max(np.abs(sph - 1.0))),
            "clipped_count": int(sph_summary.get("clipped_count", 0)),
        },
        "sph_iterations": sph_iterations,
        "handoff": {
            "augmented_hdf5_has_sph": augmented_has_sph,
            "multicompo_ascii_nsp_block_count": multicompo_nsp_block_count,
            "multicompo_ascii_path": str(paths["multicompo_ascii"]),
            "macrolib_ascii_nsp_block_count": macrolib_nsp_block_count,
            "macrolib_ascii_path": str(paths["macrolib_ascii"]),
            "accepted_sph_consumption_format": "macrolib",
            # Backward-compatible aliases used by the web summary panel.  These
            # point at the accepted DONJON SPH consumption artifact.
            "ascii_nsp_block_count": macrolib_nsp_block_count,
            "ascii_path": str(paths["macrolib_ascii"]),
            "augmented_hdf5_path": str(paths["augmented_mgxs"]),
        },
        "per_mixture": _per_mixture_stats(mixture_names, ce_flux, mg_flux, flux_ratio, sph),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    sph = summary["sph"]
    flux = summary["flux_uncertainty"]
    handoff = summary["handoff"]
    quality = summary.get("quality", {})
    production_threshold = float(
        quality.get("production_flux_relative_std_dev_threshold", PRODUCTION_FLUX_REL_STD_DEV)
    )
    demonstration_threshold = float(
        quality.get("demonstration_flux_relative_std_dev_threshold", DEMONSTRATION_FLUX_REL_STD_DEV)
    )
    lines = [
        "# OpenMC CE/MG SPH Physics Summary",
        "",
        f"Route: `{summary['route']}`",
        "",
        "## Run",
        "",
        f"- Mixtures: {summary['mixture_count']}",
        f"- Energy groups: {summary['energy_groups']}",
        f"- Converter handoff scatter: P{summary['legendre_order']} Legendre",
        f"- OpenMC MG macro scatter: {_render_mg_macro_scatter(summary['mg_macro_scatter'])}",
        f"- OpenMC SPH decision: `{summary['decisions']['openmc_sph']}`",
        f"- SPH augment decision: `{summary['decisions']['sph_augment']}`",
        "",
        "## Quality",
        "",
        f"- Decision: `{quality.get('decision', 'unknown')}`",
        f"- Production-ready: `{quality.get('production_ready', False)}`",
        f"- Demonstration-quality: `{quality.get('demonstration_quality', False)}`",
        f"- Max flux relative std_dev: {_fmt(float(quality.get('max_flux_relative_std_dev', 0.0)))}",
        f"- Production threshold: {_fmt(production_threshold)}",
        f"- Demonstration threshold: {_fmt(demonstration_threshold)}",
        "",
        *_quality_note_lines(quality),
        "",
        "## SPH Factors",
        "",
        f"- Kind: `{sph['kind']}`",
        f"- Range: {_fmt(sph['minimum'])} .. {_fmt(sph['maximum'])}",
        f"- Mean: {_fmt(sph['mean'])}",
        f"- Max |SPH - 1|: {_fmt(sph['max_abs_delta_from_unity'])}",
        f"- Clipped bins: {sph['clipped_count']}",
        f"- Applied directly to XS: `{sph['applied_to_xs']}`",
        "",
        "The augmented HDF5 carries SPH as explicit equivalence factors",
        "(`NSPH`). For DONJON `DSPH:`/`MAC:` consumption, use the MACROLIB",
        "ASCII handoff because it writes those factors as `GROUP/*/NSPH`.",
        "The macro cross sections are not silently multiplied in this route.",
        "",
        *_sph_iteration_lines(summary.get("sph_iterations", [])),
        "## Flux Uncertainty",
        "",
        f"- CE flux max relative std_dev: {_fmt(flux['ce_max_relative_std_dev'])}",
        f"- MG flux max relative std_dev: {_fmt(flux['mg_max_relative_std_dev'])}",
        "",
        "## Handoff",
        "",
        f"- Augmented HDF5 has SPH datasets: `{handoff['augmented_hdf5_has_sph']}`",
        f"- Accepted SPH consumption format: `{handoff['accepted_sph_consumption_format']}`",
        f"- MULTICOMPO NSPH block count: {handoff['multicompo_ascii_nsp_block_count']}",
        f"- MULTICOMPO ASCII: `{handoff['multicompo_ascii_path']}`",
        f"- MACROLIB NSPH block count: {handoff['macrolib_ascii_nsp_block_count']}",
        f"- MACROLIB ASCII: `{handoff['macrolib_ascii_path']}`",
        "",
        "## Per-Mixture Summary",
        "",
        "| mixture | SPH min | SPH max | max abs(SPH-1) | CE flux range | MG flux range |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["per_mixture"]:
        lines.append(
            "| {mixture} | {sph_min} | {sph_max} | {sph_delta} | {ce_range} | {mg_range} |".format(
                mixture=row["mixture"],
                sph_min=_fmt(row["sph_min"]),
                sph_max=_fmt(row["sph_max"]),
                sph_delta=_fmt(row["max_abs_sph_minus_1"]),
                ce_range=f"{_fmt(row['ce_flux_min'])}..{_fmt(row['ce_flux_max'])}",
                mg_range=f"{_fmt(row['mg_flux_min'])}..{_fmt(row['mg_flux_max'])}",
            )
        )
    lines.append("")
    return "\n".join(lines)


def _require_paths(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing minicase output(s): " + "; ".join(missing))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_mg_macro_scatter(summary: dict[str, Any]) -> str:
    scatter_format = summary.get("scatter_format")
    if scatter_format == "histogram":
        return f"H{summary.get('histogram_bins')} histogram"
    if scatter_format == "legendre":
        return f"P{summary.get('legendre_order')} Legendre"
    return "unknown"


def _read_sph_iterations(
    handoff_dir: Path,
    final_sph_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    iteration_paths = sorted(handoff_dir.glob("openmc_sph_summary_iter*.json"))
    if iteration_paths:
        summaries = [
            (_iteration_number_from_path(path, fallback=index), _read_json(path))
            for index, path in enumerate(iteration_paths, start=1)
        ]
    else:
        summaries = [(1, final_sph_summary)]

    rows: list[dict[str, Any]] = []
    for iteration, summary in summaries:
        apply_path = handoff_dir / f"sph_apply_summary_iter{iteration:02d}.json"
        apply_summary = _read_json(apply_path) if apply_path.exists() else None
        rows.append(
            {
                "iteration": iteration,
                "decision": summary.get("decision"),
                "sph_min": _optional_float(summary.get("sph_min")),
                "sph_max": _optional_float(summary.get("sph_max")),
                "raw_update_minimum": _optional_float(summary.get("raw_update_minimum")),
                "raw_update_maximum": _optional_float(summary.get("raw_update_maximum")),
                "damping": _optional_float(summary.get("damping")),
                "clipped_count": int(summary.get("clipped_count", 0)),
                "normalization_factor": _optional_float(summary.get("normalization_factor")),
                "reference_flux_max_relative_std_dev": _optional_float(
                    summary.get("reference_flux_max_relative_std_dev")
                ),
                "mg_flux_max_relative_std_dev": _optional_float(
                    summary.get("mg_flux_max_relative_std_dev")
                ),
                "previous_sph": summary.get("previous_sph"),
                "mg_flux": summary.get("mg_flux"),
                "output_h5": summary.get("output_h5"),
                "output_table": summary.get("output_table"),
                "openmc_mgxs_apply": _sph_apply_iteration_payload(apply_summary),
            }
        )
    return rows


def _iteration_number_from_path(path: Path, *, fallback: int) -> int:
    suffix = path.stem.removeprefix("openmc_sph_summary_iter")
    return int(suffix) if suffix.isdigit() else fallback


def _sph_apply_iteration_payload(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "decision": summary.get("decision"),
        "input_format": summary.get("input_format"),
        "input_h5": summary.get("input_h5"),
        "output_h5": summary.get("output_h5"),
        "sph_source": summary.get("sph_source"),
        "scaled_dataset_count": int(summary.get("scaled_dataset_count", 0)),
        "sph_min": _optional_float(summary.get("sph_min")),
        "sph_max": _optional_float(summary.get("sph_max")),
    }


def _sph_iteration_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    lines = [
        "## SPH Iterations",
        "",
        "Each row is one OpenMC CE/MG SPH update. `OpenMC MGXS apply` means",
        "the previous SPH sidecar was divided into an OpenMC-native `setN`",
        "`mgxs.h5` before rerunning the OpenMC MG macro calculation.",
        "",
        (
            "| iter | OpenMC MGXS apply | damping | clipped | SPH range | "
            "update range | CE flux rel std | MG flux rel std |"
        ),
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        apply_summary = row.get("openmc_mgxs_apply")
        if isinstance(apply_summary, dict):
            apply_text = "{fmt}, {count} datasets".format(
                fmt=apply_summary.get("input_format", "unknown"),
                count=apply_summary.get("scaled_dataset_count", 0),
            )
        else:
            apply_text = "none"
        lines.append(
            (
                "| {iteration} | {apply} | {damping} | {clipped} | {sph_min}..{sph_max} | "
                "{update_min}..{update_max} | {ce_std} | {mg_std} |"
            ).format(
                iteration=row["iteration"],
                apply=apply_text,
                damping=_fmt_optional(row.get("damping")),
                clipped=row.get("clipped_count", 0),
                sph_min=_fmt_optional(row.get("sph_min")),
                sph_max=_fmt_optional(row.get("sph_max")),
                update_min=_fmt_optional(row.get("raw_update_minimum")),
                update_max=_fmt_optional(row.get("raw_update_maximum")),
                ce_std=_fmt_optional(row.get("reference_flux_max_relative_std_dev")),
                mg_std=_fmt_optional(row.get("mg_flux_max_relative_std_dev")),
            )
        )
    lines.extend(["", ""])
    return lines


def _read_mixture_names(path: Path) -> list[str]:
    with h5py.File(path, "r") as h5:
        return [_decode_name(value) for value in h5["mixture_names"][()]]


def _read_mgxs_shape(path: Path) -> tuple[int, int]:
    with h5py.File(path, "r") as h5:
        energy_groups = int(len(h5["energy_bounds"][()]) - 1)
        legendre_order = int(h5.attrs.get("legendre_order", 0))
    return energy_groups, legendre_order


def _read_flux(path: Path, dataset_name: str) -> tuple[np.ndarray, np.ndarray]:
    with h5py.File(path, "r") as h5:
        values = np.asarray(h5[dataset_name][()], dtype=float)
        std_dev = np.asarray(h5[f"{dataset_name}_std_dev"][()], dtype=float)
    return values, std_dev


def _read_sph(path: Path, mixture_names: list[str]) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        return np.asarray([h5[f"mixtures/{name}/sph"][()] for name in mixture_names], dtype=float)


def _augmented_hdf5_has_sph(path: Path, mixture_names: list[str]) -> bool:
    with h5py.File(path, "r") as h5:
        return all(f"mixtures/{name}/sph" in h5 for name in mixture_names)


def _count_ascii_block(path: Path, block_name: str) -> int:
    return path.read_text(encoding="utf-8", errors="replace").count(block_name)


def _max_relative_std_dev(values: np.ndarray, std_dev: np.ndarray) -> float:
    relative = np.divide(
        np.abs(std_dev),
        np.abs(values),
        out=np.zeros_like(std_dev, dtype=float),
        where=np.abs(values) > 0.0,
    )
    return float(np.max(relative))


def _quality_summary(
    *,
    ce_flux_rel_std: float,
    mg_flux_rel_std: float,
    augmented_hdf5_has_sph: bool,
    multicompo_nsp_block_count: int,
    macrolib_nsp_block_count: int,
) -> dict[str, Any]:
    max_flux_rel_std = max(ce_flux_rel_std, mg_flux_rel_std)
    structural_passed = (
        augmented_hdf5_has_sph
        and multicompo_nsp_block_count > 0
        and macrolib_nsp_block_count > 0
    )
    production_ready = structural_passed and max_flux_rel_std <= PRODUCTION_FLUX_REL_STD_DEV
    demonstration_quality = structural_passed and max_flux_rel_std <= DEMONSTRATION_FLUX_REL_STD_DEV
    if not structural_passed:
        decision = "openmc_ce_mg_sph_structural_review_required"
    elif production_ready:
        decision = "openmc_ce_mg_sph_production_quality"
    elif demonstration_quality:
        decision = "openmc_ce_mg_sph_demonstration_quality"
    else:
        decision = "openmc_ce_mg_sph_statistical_review_required"

    notes = []
    if not structural_passed:
        notes.append("SPH datasets or ASCII NSPH blocks are missing.")
    if max_flux_rel_std > PRODUCTION_FLUX_REL_STD_DEV:
        notes.append(
            "Flux statistical uncertainty exceeds the production-quality "
            f"threshold {PRODUCTION_FLUX_REL_STD_DEV:g}."
        )
    if max_flux_rel_std > DEMONSTRATION_FLUX_REL_STD_DEV:
        notes.append(
            "Flux statistical uncertainty also exceeds the demonstration "
            f"threshold {DEMONSTRATION_FLUX_REL_STD_DEV:g}; increase particles/batches."
        )
    if not notes:
        notes.append("SPH handoff structure and flux uncertainty meet the production-quality threshold.")

    return {
        "decision": decision,
        "structural_passed": structural_passed,
        "production_ready": production_ready,
        "demonstration_quality": demonstration_quality,
        "max_flux_relative_std_dev": max_flux_rel_std,
        "production_flux_relative_std_dev_threshold": PRODUCTION_FLUX_REL_STD_DEV,
        "demonstration_flux_relative_std_dev_threshold": DEMONSTRATION_FLUX_REL_STD_DEV,
        "notes": notes,
    }


def _quality_note_lines(quality: dict[str, Any]) -> list[str]:
    notes = quality.get("notes")
    if not isinstance(notes, list) or not notes:
        return []
    lines = ["Notes:"]
    lines.extend(f"- {note}" for note in notes)
    return lines


def _per_mixture_stats(
    names: list[str],
    ce_flux: np.ndarray,
    mg_flux: np.ndarray,
    flux_ratio: np.ndarray,
    sph: np.ndarray,
) -> list[dict[str, Any]]:
    rows = []
    for index, name in enumerate(names):
        rows.append(
            {
                "mixture": name,
                "ce_flux_min": float(np.min(ce_flux[index])),
                "ce_flux_max": float(np.max(ce_flux[index])),
                "mg_flux_min": float(np.min(mg_flux[index])),
                "mg_flux_max": float(np.max(mg_flux[index])),
                "normalized_mg_over_ce_min": float(np.min(flux_ratio[index])),
                "normalized_mg_over_ce_max": float(np.max(flux_ratio[index])),
                "sph_min": float(np.min(sph[index])),
                "sph_max": float(np.max(sph[index])),
                "sph_mean": float(np.mean(sph[index])),
                "max_abs_sph_minus_1": float(np.max(np.abs(sph[index] - 1.0))),
            }
        )
    return rows


def _decode_name(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _fmt_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    return _fmt(float(value))


def _fmt(value: float) -> str:
    return f"{value:.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
