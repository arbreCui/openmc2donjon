#!/usr/bin/env python3
"""Compare normalized 91-position fission-power shapes for Stage 3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

from openmc2donjon.hdf5_names import read_mixture_names
from openmc2donjon.sph_augment import load_sph_source


SCHEMA = "openmc2donjon.irena30-sph-stage3-power-shape.v1"


def _split_source(source: str, default_dataset: str) -> tuple[Path, str]:
    if "::" not in source:
        return Path(source), default_dataset
    path, dataset = source.rsplit("::", 1)
    if not path or not dataset:
        raise ValueError(f"invalid HDF5 source: {source!r}")
    return Path(path), dataset


def _load_flux(source: str, *, shape: tuple[int, int], default_dataset: str) -> np.ndarray:
    path, dataset = _split_source(source, default_dataset)
    if not path.is_file():
        raise FileNotFoundError(f"flux HDF5 does not exist: {path}")
    with h5py.File(path, "r") as h5:
        if dataset not in h5:
            raise ValueError(f"flux dataset does not exist: {path}::{dataset}")
        values = np.asarray(h5[dataset][:], dtype=float)
    if values.shape != shape:
        raise ValueError(f"flux shape {values.shape} != {shape}: {path}::{dataset}")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError(f"flux values must be finite and non-negative: {path}::{dataset}")
    return values


def _normalized_power(kappa_fission: np.ndarray, flux: np.ndarray) -> np.ndarray:
    power = np.sum(kappa_fission * flux, axis=1)
    total = float(np.sum(power))
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("integrated fission power must be positive and finite")
    return power / total


def _shape_metrics(
    reference: np.ndarray,
    candidate: np.ndarray,
    mixture_names: tuple[str, ...],
) -> dict[str, object]:
    active = reference > 0.0
    relative = (candidate[active] - reference[active]) / reference[active]
    worst_index = int(np.argmax(np.abs(relative)))
    active_names = np.asarray(mixture_names)[active]
    return {
        "maximum_absolute_relative_error": float(np.max(np.abs(relative))),
        "rms_relative_error": float(np.sqrt(np.mean(np.square(relative)))),
        "l1_normalized_power_error": float(np.sum(np.abs(candidate - reference))),
        "worst_mixture": str(active_names[worst_index]),
        "worst_signed_relative_error": float(relative[worst_index]),
    }


def compare_power_shapes(
    mgxs_h5: Path,
    *,
    reference_flux: str,
    uncorrected_flux: str,
    corrected_flux: str,
    corrected_sph: Path,
    summary_json: Path | None = None,
) -> dict[str, object]:
    """Return CE, uncorrected-MG, and corrected-MG power-shape metrics."""

    mgxs_h5 = Path(mgxs_h5)
    with h5py.File(mgxs_h5, "r") as h5:
        mixture_names = read_mixture_names(h5)
        kappa = np.stack(
            [np.asarray(h5["mixtures"][name]["kappa_fission"][:]) for name in mixture_names]
        )
    shape = kappa.shape
    reference = _load_flux(
        reference_flux, shape=shape, default_dataset="openmc_volume_flux"
    )
    uncorrected = _load_flux(
        uncorrected_flux, shape=shape, default_dataset="openmc_mg_flux"
    )
    corrected = _load_flux(
        corrected_flux, shape=shape, default_dataset="openmc_mg_flux"
    )
    loaded = load_sph_source(
        Path(corrected_sph),
        mixture_names=mixture_names,
        energy_groups=shape[1],
    )
    sph = np.stack([loaded.sph[name] for name in mixture_names])

    reference_power = _normalized_power(kappa, reference)
    uncorrected_power = _normalized_power(kappa, uncorrected)
    corrected_power = _normalized_power(kappa / sph, corrected)
    uncorrected_metrics = _shape_metrics(
        reference_power, uncorrected_power, mixture_names
    )
    corrected_metrics = _shape_metrics(reference_power, corrected_power, mixture_names)
    improved = (
        corrected_metrics["maximum_absolute_relative_error"]
        < uncorrected_metrics["maximum_absolute_relative_error"]
        and corrected_metrics["rms_relative_error"]
        < uncorrected_metrics["rms_relative_error"]
    )
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "mgxs_h5": str(mgxs_h5),
        "reference_flux": reference_flux,
        "uncorrected_flux": uncorrected_flux,
        "corrected_flux": corrected_flux,
        "corrected_sph": str(corrected_sph),
        "mixture_count": len(mixture_names),
        "active_power_mixture_count": int(np.count_nonzero(reference_power > 0.0)),
        "uncorrected": uncorrected_metrics,
        "corrected": corrected_metrics,
        "corrected_improved": improved,
        "decision": "openmc2donjon_irena30_stage3_power_shape_compared",
    }
    if summary_json is not None:
        summary_json = Path(summary_json)
        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, required=True)
    parser.add_argument("--reference-flux", required=True)
    parser.add_argument("--uncorrected-flux", required=True)
    parser.add_argument("--corrected-flux", required=True)
    parser.add_argument("--corrected-sph", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = compare_power_shapes(
            args.mgxs,
            reference_flux=args.reference_flux,
            uncorrected_flux=args.uncorrected_flux,
            corrected_flux=args.corrected_flux,
            corrected_sph=args.corrected_sph,
            summary_json=args.summary,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    unc = payload["uncorrected"]
    cor = payload["corrected"]
    assert isinstance(unc, dict) and isinstance(cor, dict)
    print("IRENA-30 Stage 3 normalized power-shape comparison")
    for label, metrics in (("uncorrected", unc), ("corrected", cor)):
        print(
            f"  {label:11}: max={metrics['maximum_absolute_relative_error']:.2%} "
            f"rms={metrics['rms_relative_error']:.2%} "
            f"L1={metrics['l1_normalized_power_error']:.2%} "
            f"worst={metrics['worst_mixture']}"
        )
    print(f"  corrected improved: {payload['corrected_improved']}")
    print(f"  summary: {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
