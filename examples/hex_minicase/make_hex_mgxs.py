#!/usr/bin/env python3
"""Build a synthetic hex-domain MGXS HDF5 handoff for openmc2donjon."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np


MIXTURE_NAMES = ("HEX_C", "HEX_E", "HEX_NE", "HEX_NW", "HEX_W", "HEX_SW", "HEX_SE")
FACE_NAMES = ("FD_E", "FD_NE", "FD_NW", "FD_W", "FD_SW", "FD_SE")
ENERGY_BOUNDS_EV = np.asarray([1.0e-5, 6.25e-1, 1.0e5, 2.0e7], dtype=float)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, required=True, help="output HDF5 path")
    parser.add_argument("--summary-json", type=Path, default=None, help="write summary JSON")
    parser.add_argument("--force", action="store_true", help="overwrite output")
    args = parser.parse_args()

    summary = write_hex_handoff(args.output, force=args.force)
    print(
        "wrote hex minicase MGXS handoff: "
        f"mixtures={summary['mixture_count']} groups={summary['energy_groups']} "
        f"P{summary['legendre_order']} faces={','.join(summary['adf_faces'])}"
    )
    print(f"  output: {summary['output_h5']}")
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"  summary: {args.summary_json}")
    return 0


def write_hex_handoff(output: Path, *, force: bool) -> dict[str, object]:
    output = Path(output)
    if output.exists() and not force:
        raise FileExistsError(f"output exists; use --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(output, "w") as h5:
        h5.attrs["source"] = "examples/hex_minicase synthetic OpenMC-style handoff"
        h5.attrs["case"] = "hex_minicase"
        h5.attrs["domain_mode"] = "hex_cell_domains"
        h5.attrs["domain_type"] = "cell"
        h5.attrs["geometry_kind"] = "hexagonal"
        h5.attrs["spatial_mapping"] = "one OpenMC hex cell domain -> one DONJON mixture"
        h5.attrs["energy_groups"] = 3
        h5.attrs["legendre_order"] = 1
        h5.attrs["scatter_axes"] = "moment,from,to"
        h5.attrs["hex_pitch_cm"] = 21.0
        h5.attrs["hex_axial_height_cm"] = 1.0
        h5.create_dataset("energy_bounds", data=ENERGY_BOUNDS_EV)

        mixtures = h5.create_group("mixtures")
        for index, name in enumerate(MIXTURE_NAMES):
            _write_mixture(mixtures, index, name)

    return {
        "schema": "openmc2donjon.hex-minicase-summary.v1",
        "output_h5": str(output),
        "mixture_count": len(MIXTURE_NAMES),
        "mixture_names": list(MIXTURE_NAMES),
        "energy_groups": 3,
        "legendre_order": 1,
        "adf_faces": list(FACE_NAMES),
    }


def _write_mixture(parent: h5py.Group, index: int, name: str) -> None:
    group = parent.create_group(name)
    fissionable = name != "HEX_C"
    ring_factor = 1.0 + 0.012 * index
    leakage_factor = 1.0 + 0.004 * (index % 3)

    total = np.asarray([0.48, 0.72, 1.18], dtype=float) * ring_factor
    absorption = np.asarray([0.030, 0.080, 0.210], dtype=float) * ring_factor
    scatter_p0 = np.asarray(
        [
            [0.360, 0.055, 0.000],
            [0.002, 0.500, 0.080],
            [0.000, 0.004, 0.830],
        ],
        dtype=float,
    ) * ring_factor
    scatter_p1 = np.asarray(
        [
            [0.045, 0.006, 0.000],
            [0.000, 0.052, 0.007],
            [0.000, 0.000, 0.060],
        ],
        dtype=float,
    ) * ring_factor
    scatter = np.stack([scatter_p0, scatter_p1])
    transport_total = np.asarray([0.42, 0.62, 0.96], dtype=float) * leakage_factor

    fission = np.zeros(3, dtype=float)
    nu_fission = np.zeros(3, dtype=float)
    chi = np.zeros(3, dtype=float)
    if fissionable:
        fuel_factor = 1.0 - 0.01 * (index - 1)
        fission = np.asarray([0.010, 0.020, 0.155], dtype=float) * fuel_factor
        nu_fission = np.asarray([0.025, 0.050, 0.390], dtype=float) * fuel_factor
        chi = np.asarray([0.72, 0.23, 0.05], dtype=float)

    adf = _adf_matrix(index)

    group.attrs["fissionable"] = bool(fissionable)
    group.attrs["volume"] = float(381.971863 * (1.0 if name == "HEX_C" else 1.02))
    group.attrs["hex_ring"] = 0 if name == "HEX_C" else 1
    group.attrs["hex_position"] = name.replace("HEX_", "")
    group.attrs["scatter_format"] = "legendre"
    group.attrs["scatter_axes"] = "moment,from,to"
    group.create_dataset("total", data=total)
    group.create_dataset("absorption", data=absorption)
    group.create_dataset("fission", data=fission)
    group.create_dataset("nu_fission", data=nu_fission)
    group.create_dataset("chi", data=chi)
    group.create_dataset("scatter_matrix", data=scatter)
    group.create_dataset("transport_total", data=transport_total)
    group.create_dataset("flux_weight", data=np.asarray([1.0, 0.85, 0.65]) * ring_factor)
    adf_dataset = group.create_dataset("adf", data=adf)
    adf_dataset.attrs["face_names"] = np.asarray(FACE_NAMES, dtype="S")
    adf_dataset.attrs["adf_kind"] = "synthetic-six-face-hex"
    adf_dataset.attrs["adf_real"] = False


def _adf_matrix(index: int) -> np.ndarray:
    base = np.asarray([1.000, 1.010, 0.990], dtype=float)
    rows = []
    for face_index, _face in enumerate(FACE_NAMES):
        face_shift = 0.004 * (face_index - 2.5)
        domain_shift = 0.002 * (index - 3)
        rows.append(base + face_shift + domain_shift)
    return np.asarray(rows, dtype=float)


if __name__ == "__main__":
    raise SystemExit(main())
