#!/usr/bin/env python3
"""Adapt the local UOX 5x5 TG6 APEX HDF5 into the openmc2donjon contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

import h5py
import numpy as np


DEFAULT_INPUT = (
    Path("/Users/wen/dragon-5.1")
    / "Dragon/data/UOX_5x5_TG6_sym8_multiDom_proc/UOX_5x5_TG6_sym8_multiDom.h5"
)
FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="source APEX HDF5")
    parser.add_argument("-o", "--output", type=Path, required=True, help="MGXS-contract HDF5")
    parser.add_argument("--summary-json", type=Path, default=None, help="write a summary JSON")
    parser.add_argument("--calc", type=int, default=1, help="source calculation index, default 1")
    parser.add_argument(
        "--domain-mode",
        choices=("subdomain", "total"),
        default="subdomain",
        help="write six spatial domains or one assembly-total domain",
    )
    parser.add_argument("--force", action="store_true", help="overwrite output")
    args = parser.parse_args()

    summary = adapt_apex_hdf5(
        args.input,
        args.output,
        calc_index=args.calc,
        domain_mode=args.domain_mode,
        force=args.force,
    )
    print(
        "adapted UOX 5x5 TG6 APEX HDF5: "
        f"mixtures={summary['mixture_count']} groups={summary['energy_groups']} "
        f"P{summary['legendre_order']} domain_mode={summary['domain_mode']}"
    )
    print(f"  source: {summary['input_h5']}")
    print(f"  output: {summary['output_h5']}")
    print(
        "  source reference: "
        f"KINF={summary['source_kinf']:.8g} KEFF={summary['source_keff']:.8g} "
        f"B2={summary['source_b2']:.8g}"
    )
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  summary: {args.summary_json}")
    return 0


def adapt_apex_hdf5(
    input_h5: Path,
    output_h5: Path,
    *,
    calc_index: int,
    domain_mode: str,
    force: bool,
) -> dict[str, Any]:
    input_h5 = Path(input_h5)
    output_h5 = Path(output_h5)
    if not input_h5.exists():
        raise FileNotFoundError(f"source APEX HDF5 does not exist: {input_h5}")
    if output_h5.exists() and not force:
        raise FileExistsError(f"output exists; use --force: {output_h5}")
    if calc_index < 1:
        raise ValueError("--calc must be one-based and positive")

    with h5py.File(input_h5, "r") as source:
        calc = f"calc       {calc_index}"
        if calc not in source:
            raise ValueError(f"source calculation {calc_index} not found")
        energy_bounds = _energy_bounds_eV(source)
        macro_sources = _macro_sources(source, calc, domain_mode)
        source_summary = _source_summary(source, calc)

        output_h5.parent.mkdir(parents=True, exist_ok=True)
        with h5py.File(output_h5, "w") as out:
            out.attrs["source"] = "APEX APOLLO2-A HDF5 adapted by examples/uox_5x5_tg6"
            out.attrs["source_path"] = str(input_h5)
            out.attrs["source_calculation"] = calc_index
            out.attrs["source_structure_type"] = _string_dataset(source, "structure_type")
            out.attrs["source_structure_version"] = _string_dataset(source, "structure_version")
            out.attrs["domain_mode"] = f"uox_5x5_tg6_{domain_mode}"
            out.attrs["energy_groups"] = energy_bounds.size - 1
            out.attrs["legendre_order"] = 1
            out.attrs["scatter_axes"] = "moment,from,to"
            out.create_dataset("energy_bounds", data=energy_bounds)
            mixtures = out.create_group("mixtures")
            for mixture in macro_sources:
                _write_mixture(mixtures, source, calc, mixture, domain_mode)

    return {
        "schema": "openmc2donjon.uox-5x5-tg6-adapter-summary.v1",
        "input_h5": str(input_h5),
        "output_h5": str(output_h5),
        "source_calculation": calc_index,
        "domain_mode": domain_mode,
        "energy_groups": int(energy_bounds.size - 1),
        "legendre_order": 1,
        "mixture_count": len(macro_sources),
        "mixture_names": [mixture["name"] for mixture in macro_sources],
        **source_summary,
    }


def _energy_bounds_eV(source: h5py.File) -> np.ndarray:
    edges_mev = np.asarray(source["physconst/ENRGS"][:], dtype=float)
    if edges_mev.ndim != 1 or edges_mev.size < 2:
        raise ValueError("physconst/ENRGS must be one-dimensional")
    if not np.all(np.diff(edges_mev) < 0.0):
        raise ValueError("physconst/ENRGS must be descending in energy")
    return edges_mev[::-1] * 1.0e6


def _macro_sources(source: h5py.File, calc: str, domain_mode: str) -> list[dict[str, str]]:
    if domain_mode == "total":
        return [{"name": "assemblage", "xs": f"{calc}/xs", "macro": f"{calc}/xs/mac/TOTAL"}]

    out: list[dict[str, str]] = []
    for key in sorted(name for name in source[calc] if name.startswith("xs       ")):
        base = f"{calc}/{key}"
        media_name = _string_dataset(source, f"{base}/MEDIA_NAME")
        out.append(
            {
                "name": _safe_name(media_name or key.strip()),
                "xs": base,
                "macro": f"{base}/mac/TOTAL",
            }
        )
    if not out:
        raise ValueError(f"{calc}: no subdomain xs groups found")
    return out


def _write_mixture(
    mixtures: h5py.Group,
    source: h5py.File,
    calc: str,
    mixture: dict[str, str],
    domain_mode: str,
) -> None:
    ngroups = int(source["physconst/ENRGS"].shape[0] - 1)
    group = mixtures.create_group(mixture["name"])
    macro = mixture["macro"]
    xs_base = mixture["xs"]
    total = _vector(source, f"{macro}/TOTA", ngroups)
    absorption = _vector(source, f"{macro}/ABSO", ngroups)
    fission = _optional_vector(source, f"{macro}/FISS", ngroups)
    nu_fission = _optional_vector(source, f"{macro}/NUFI", ngroups)
    chi = _optional_vector(source, f"{macro}/CHI", ngroups)
    scatter = _matrix(source, f"{macro}/SCAT", (2, ngroups, ngroups))
    diffusion_coefficient = _matrix(source, f"{macro}/DIFF", (2, ngroups))[0]
    if np.any(diffusion_coefficient <= 0.0):
        raise ValueError(f"{macro}/DIFF[0]: diffusion coefficients must be positive")
    transport_total = 1.0 / (3.0 * diffusion_coefficient)

    group.attrs["source_path"] = macro
    group.attrs["source_media"] = _string_dataset(source, f"{xs_base}/MEDIA_NAME")
    group.attrs["volume"] = float(_vector(source, f"{xs_base}/MEDIA_VOLUME", 1)[0])
    group.attrs["fissionable"] = bool(np.any(nu_fission > 0.0) or np.any(fission > 0.0))
    group.attrs["scatter_format"] = "legendre"
    group.attrs["scatter_axes"] = "moment,from,to"
    group.attrs["transport_total_source"] = "1 / (3 * APEX macro DIFF[0])"
    group.attrs["source_diffusion_coefficient_path"] = f"{macro}/DIFF[0]"
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=fission)
    group.create_dataset("nu_fission", data=nu_fission)
    group.create_dataset("chi", data=chi)
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport_total)
    group.create_dataset("source_diffusion_coefficient", data=diffusion_coefficient)
    if f"{xs_base}/FLUX" in source:
        group.create_dataset("flux_weight", data=_vector(source, f"{xs_base}/FLUX", ngroups))
    if domain_mode == "total" and f"{calc}/miscellaneous/ADF" in source:
        adf = np.asarray(source[f"{calc}/miscellaneous/ADF"][:], dtype=float).T
        dataset = group.create_dataset("adf", data=adf)
        dataset.attrs["face_names"] = np.asarray(FACE_NAMES, dtype="S")
        dataset.attrs["source_path"] = f"{calc}/miscellaneous/ADF"


def _source_summary(source: h5py.File, calc: str) -> dict[str, Any]:
    return {
        "source_comment": _string_dataset(source, f"{calc}/GENERAL/Comment"),
        "source_burnup": float(_vector(source, f"{calc}/PARAM/Burnup", 1)[0]),
        "source_boron_ppm": float(_vector(source, f"{calc}/PARAM/BoronPPM", 1)[0]),
        "source_fuel_temperature_K": float(_vector(source, f"{calc}/PARAM/FuelTemperature", 1)[0]),
        "source_moderator_density": float(_vector(source, f"{calc}/PARAM/ModeratorDensity", 1)[0]),
        "source_kinf": float(_vector(source, f"{calc}/miscellaneous/KINF", 1)[0]),
        "source_keff": float(_vector(source, f"{calc}/miscellaneous/KEFF", 1)[0]),
        "source_b2": float(_vector(source, f"{calc}/miscellaneous/B2", 1)[0]),
    }


def _vector(source: h5py.File, path: str, size: int) -> np.ndarray:
    values = np.asarray(source[path][:], dtype=float).reshape(-1)
    if values.shape != (size,):
        raise ValueError(f"{path}: shape {values.shape} != ({size},)")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{path}: non-finite values")
    return values.astype(float)


def _optional_vector(source: h5py.File, path: str, size: int) -> np.ndarray:
    if path not in source:
        return np.zeros(size, dtype=float)
    return _vector(source, path, size)


def _matrix(source: h5py.File, path: str, shape: tuple[int, ...]) -> np.ndarray:
    values = np.asarray(source[path][:], dtype=float)
    if values.shape != shape:
        raise ValueError(f"{path}: shape {values.shape} != {shape}")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{path}: non-finite values")
    return values.astype(float)


def _string_dataset(source: h5py.File, path: str) -> str:
    if path not in source:
        return ""
    values = np.asarray(source[path][()]).reshape(-1)
    if not len(values):
        return ""
    value = values[0]
    if isinstance(value, bytes):
        return value.decode(errors="replace").rstrip("\x00").strip()
    return str(value).strip()


def _safe_name(raw: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip())
    return name or "mixture"


if __name__ == "__main__":
    raise SystemExit(main())
