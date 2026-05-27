"""Summarize the CE/MG 33g OpenMC-side SPH minicase outputs.

The report is intentionally small and auditable.  It does not decide whether
the minicase is a benchmark; it records what happened in one run:

* CE and MG flux uncertainty levels,
* SPH factor ranges by mixture,
* whether the augmented HDF5 and final ASCII handoff carry NSPH data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


SUMMARY_SCHEMA = "openmc2donjon.openmc-ce-mg-33g-sph-physics-summary.v1"


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
        "ascii": handoff_dir / "out_with_openmc_sph.mcompo.txt",
    }
    _require_paths(paths)

    sph_summary = _read_json(paths["sph_summary"])
    augment_summary = _read_json(paths["augment_summary"])
    mixture_names = _read_mixture_names(paths["augmented_mgxs"])
    energy_groups, legendre_order = _read_mgxs_shape(paths["mgxs"])
    ce_flux, ce_std = _read_flux(paths["ce_flux"], "openmc_volume_flux")
    mg_flux, mg_std = _read_flux(paths["mg_flux"], "openmc_mg_flux")
    sph = _read_sph(paths["augmented_mgxs"], mixture_names)
    normalization_factor = float(sph_summary.get("normalization_factor", 1.0))
    normalized_mg_flux = mg_flux * normalization_factor
    flux_ratio = normalized_mg_flux / ce_flux
    nsp_block_count = _count_ascii_block(paths["ascii"], "NSPH")

    return {
        "schema": SUMMARY_SCHEMA,
        "route": "OpenMC CE reference + OpenMC MG 33g same geometry -> OpenMC-side SPH",
        "handoff_dir": str(handoff_dir),
        "mixture_count": len(mixture_names),
        "energy_groups": energy_groups,
        "legendre_order": legendre_order,
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
            "ce_max_relative_std_dev": _max_relative_std_dev(ce_flux, ce_std),
            "mg_max_relative_std_dev": _max_relative_std_dev(mg_flux, mg_std),
            "ce_dataset": "openmc_volume_flux",
            "mg_dataset": "openmc_mg_flux",
        },
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
        "handoff": {
            "augmented_hdf5_has_sph": _augmented_hdf5_has_sph(paths["augmented_mgxs"], mixture_names),
            "ascii_nsp_block_count": nsp_block_count,
            "ascii_path": str(paths["ascii"]),
            "augmented_hdf5_path": str(paths["augmented_mgxs"]),
        },
        "per_mixture": _per_mixture_stats(mixture_names, ce_flux, mg_flux, flux_ratio, sph),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    sph = summary["sph"]
    flux = summary["flux_uncertainty"]
    handoff = summary["handoff"]
    lines = [
        "# OpenMC CE/MG 33g SPH Physics Summary",
        "",
        f"Route: `{summary['route']}`",
        "",
        "## Run",
        "",
        f"- Mixtures: {summary['mixture_count']}",
        f"- Energy groups: {summary['energy_groups']}",
        f"- Legendre order: P{summary['legendre_order']}",
        f"- OpenMC SPH decision: `{summary['decisions']['openmc_sph']}`",
        f"- SPH augment decision: `{summary['decisions']['sph_augment']}`",
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
        "The augmented HDF5 and final ASCII carry SPH as equivalence factors",
        "(`NSPH`) for DONJON consumption; the macro cross sections are not",
        "silently multiplied in this route.",
        "",
        "## Flux Uncertainty",
        "",
        f"- CE flux max relative std_dev: {_fmt(flux['ce_max_relative_std_dev'])}",
        f"- MG flux max relative std_dev: {_fmt(flux['mg_max_relative_std_dev'])}",
        "",
        "## Handoff",
        "",
        f"- Augmented HDF5 has SPH datasets: `{handoff['augmented_hdf5_has_sph']}`",
        f"- ASCII NSPH block count: {handoff['ascii_nsp_block_count']}",
        f"- ASCII: `{handoff['ascii_path']}`",
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


def _fmt(value: float) -> str:
    return f"{value:.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
