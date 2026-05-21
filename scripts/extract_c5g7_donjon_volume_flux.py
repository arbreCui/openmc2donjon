#!/usr/bin/env python3
"""Extract C5G7 assembly-wise DONJON volume flux from an ``L_FLUX`` dump."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np

from openmc2donjon import lcm_ascii as lcm


DEFAULT_MAP_H5 = Path(
    "/Users/wen/openmc-workspace/openmc2donjon/examples/donjon_openmc2donjon/"
    "c5g7_homogeneous_face_flux_donjon.h5"
)


def main() -> int:
    args = _parse_args()
    mesh = _read_mesh_map(args.map_h5)
    flux_vectors = _read_flux_vectors(args.flux_dump, mesh["energy_groups"])
    volume_flux = _extract_volume_flux(flux_vectors, mesh["kn"], mesh["mixture_names"])
    _write_output(args.output, args, mesh, volume_flux)
    print(
        "C5G7 DONJON volume flux extracted: "
        f"mesh={volume_flux.shape[0]}x{volume_flux.shape[1]} "
        f"groups={volume_flux.shape[2]} "
        f"range={float(np.min(volume_flux)):.6g}..{float(np.max(volume_flux)):.6g}"
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flux-dump",
        type=Path,
        required=True,
        help="DONJON result containing UTL L_FLUX dump",
    )
    parser.add_argument(
        "--map-h5",
        type=Path,
        default=DEFAULT_MAP_H5,
        help="HDF5 file carrying C5G7 kn, energy_bounds, and mixture_names datasets",
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="output HDF5 path")
    return parser.parse_args()


def _read_mesh_map(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        energy_bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
        mixture_names = np.asarray(h5["mixture_names"][:])
        kn = np.asarray(h5["kn"][:], dtype=int)
    if mixture_names.ndim != 2:
        raise ValueError(f"{path}: mixture_names must be a 2D mesh")
    expected_cells = int(np.prod(mixture_names.shape))
    if kn.shape[0] != expected_cells or kn.shape[1] < 1:
        raise ValueError(
            f"{path}: kn shape {kn.shape} is incompatible with mixture mesh "
            f"{mixture_names.shape}"
        )
    return {
        "path": str(path),
        "energy_bounds": energy_bounds,
        "energy_groups": int(energy_bounds.size - 1),
        "mixture_names": mixture_names,
        "kn": kn,
    }


def _read_flux_vectors(path: Path, energy_groups: int) -> np.ndarray:
    blocks = lcm.read_lcm_ascii(path)
    vectors = [
        np.asarray(block.data, dtype=float)
        for block in blocks
        if block.name is None
        and block.data is not None
        and block.type_code == 2
        and block.trailing
    ]
    if len(vectors) < energy_groups:
        raise ValueError(f"{path}: found {len(vectors)} FLUX vectors, expected {energy_groups}")
    lengths = {vector.size for vector in vectors[:energy_groups]}
    if len(lengths) != 1:
        raise ValueError(f"{path}: inconsistent FLUX vector lengths {lengths}")
    return np.stack(vectors[:energy_groups])


def _extract_volume_flux(
    flux_vectors: np.ndarray,
    kn: np.ndarray,
    mixture_names: np.ndarray,
) -> np.ndarray:
    energy_groups = flux_vectors.shape[0]
    mesh_shape = mixture_names.shape
    volume_flux = np.empty(mesh_shape + (energy_groups,), dtype=float)
    for y_index in range(mesh_shape[0]):
        for x_index in range(mesh_shape[1]):
            element = y_index * mesh_shape[1] + x_index
            flux_id = int(kn[element, 0])
            if flux_id <= 0:
                raise ValueError(f"KN element {element + 1} has no scalar flux id")
            volume_flux[y_index, x_index, :] = flux_vectors[:, flux_id - 1]
    return volume_flux


def _write_output(
    path: Path,
    args: argparse.Namespace,
    mesh: dict[str, object],
    volume_flux: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["source"] = "DONJON L_FLUX scalar unknown extraction"
        h5.attrs["flux_dump"] = str(args.flux_dump)
        h5.attrs["map_h5"] = str(args.map_h5)
        h5.create_dataset("energy_bounds", data=np.asarray(mesh["energy_bounds"], dtype=float))
        h5.create_dataset("mixture_names", data=np.asarray(mesh["mixture_names"]))
        h5.create_dataset("kn", data=np.asarray(mesh["kn"], dtype=int))
        h5.create_dataset("donjon_volume_flux", data=volume_flux)
        h5.create_dataset("volume_flux", data=volume_flux)


if __name__ == "__main__":
    raise SystemExit(main())
