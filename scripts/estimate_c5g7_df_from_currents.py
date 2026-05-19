#!/usr/bin/env python3
"""Estimate C5G7 surface/volume flux ratios from assembly-face data.

This is a diagnostic for discontinuity-factor work, not a final ADF generator.
If the input contains ``/surface_flux`` from a mu-binned mesh-surface tally, that
surface-flux reconstruction is used. Otherwise, the script falls back to the P1
relation ``phi_s ~= 2 * (J_out + J_in)``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
FACE_AREA = ASSEMBLY_PITCH
DEFAULT_IN = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_boundary_currents_full.h5"
)
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_current_df_proxy.h5"
)
FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
PARTIAL_FACE_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7))


def main() -> int:
    args = _parse_args()
    data = _read_input(args.input)
    proxy = _estimate_proxy(data)
    _write_output(args.output, data, proxy)
    _print_summary(proxy)
    print(f"Wrote {args.output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_IN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def _read_input(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        if "volume_flux" not in h5:
            raise ValueError("input file must contain /volume_flux")
        current = h5["boundary_currents/mean"][:]
        current_std_dev = h5["boundary_currents/std_dev"][:]
        volume_average = h5["volume_flux/average"][:]
        volume_std_dev = h5["volume_flux/std_dev"][:]
        cell_volume = h5["volume_flux/cell_volume"][:]
        if current.ndim != 4 or current.shape[-1] != 8:
            raise ValueError("expected current shape [mesh_y, mesh_x, group, 8]")
        if volume_average.shape != current.shape[:3]:
            raise ValueError("volume flux shape does not match current bins")
        return {
            "path": str(path),
            "attrs": dict(h5.attrs),
            "energy_bounds": h5["energy_bounds"][:],
            "current": current,
            "current_std_dev": current_std_dev,
            "volume_average": volume_average,
            "volume_std_dev": volume_std_dev,
            "cell_volume": cell_volume,
            "surface_flux": h5["surface_flux/mean"][:] if "surface_flux" in h5 else None,
            "surface_flux_std_dev": (
                h5["surface_flux/std_dev"][:] if "surface_flux" in h5 else None
            ),
        }


def _estimate_proxy(data: dict[str, object]) -> dict[str, np.ndarray]:
    current = np.asarray(data["current"], dtype=float)
    current_std_dev = np.asarray(data["current_std_dev"], dtype=float)
    volume_average = np.asarray(data["volume_average"], dtype=float)
    measured_surface_flux = data.get("surface_flux")
    measured_surface_flux_std_dev = data.get("surface_flux_std_dev")

    surface_flux = np.zeros(current.shape[:3] + (4,), dtype=float)
    surface_flux_std_dev = np.zeros_like(surface_flux)
    net_current_density = np.zeros_like(surface_flux)
    net_current_std_dev = np.zeros_like(surface_flux)

    for face, (out_idx, in_idx) in enumerate(PARTIAL_FACE_PAIRS):
        outgoing = current[..., out_idx]
        incoming = current[..., in_idx]
        outgoing_std = current_std_dev[..., out_idx]
        incoming_std = current_std_dev[..., in_idx]
        surface_flux[..., face] = 2.0 * (outgoing + incoming) / FACE_AREA
        surface_flux_std_dev[..., face] = (
            2.0 * np.sqrt(outgoing_std**2 + incoming_std**2) / FACE_AREA
        )
        net_current_density[..., face] = (outgoing - incoming) / FACE_AREA
        net_current_std_dev[..., face] = (
            np.sqrt(outgoing_std**2 + incoming_std**2) / FACE_AREA
        )
    if measured_surface_flux is not None:
        measured_surface_flux = np.asarray(measured_surface_flux, dtype=float)
        if measured_surface_flux.shape != surface_flux.shape:
            raise ValueError("surface_flux shape does not match current bins")
        surface_flux = measured_surface_flux
        if measured_surface_flux_std_dev is not None:
            surface_flux_std_dev = np.asarray(measured_surface_flux_std_dev, dtype=float)

    ratio = np.divide(
        surface_flux,
        volume_average[:, :, :, np.newaxis],
        out=np.zeros_like(surface_flux),
        where=volume_average[:, :, :, np.newaxis] > 0.0,
    )
    ratio_std_dev_current_only = np.divide(
        surface_flux_std_dev,
        volume_average[:, :, :, np.newaxis],
        out=np.zeros_like(surface_flux_std_dev),
        where=volume_average[:, :, :, np.newaxis] > 0.0,
    )
    interior_face_mask = _interior_face_mask(current.shape[:2])
    return {
        "surface_flux_proxy": surface_flux,
        "surface_flux_proxy_std_dev": surface_flux_std_dev,
        "net_current_density": net_current_density,
        "net_current_density_std_dev": net_current_std_dev,
        "surface_to_volume_ratio": ratio,
        "surface_to_volume_ratio_std_dev_current_only": ratio_std_dev_current_only,
        "interior_face_mask": interior_face_mask,
        "uses_angular_surface_flux": np.asarray(measured_surface_flux is not None),
    }


def _interior_face_mask(mesh_shape: tuple[int, int]) -> np.ndarray:
    mesh_y, mesh_x = mesh_shape
    mask = np.zeros((mesh_y, mesh_x, 4), dtype=np.bool_)
    for y_index in range(mesh_y):
        for x_index in range(mesh_x):
            mask[y_index, x_index, 0] = x_index > 0
            mask[y_index, x_index, 1] = x_index < mesh_x - 1
            mask[y_index, x_index, 2] = y_index > 0
            mask[y_index, x_index, 3] = y_index < mesh_y - 1
    return mask


def _write_output(
    path: Path, data: dict[str, object], proxy: dict[str, np.ndarray]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        if bool(proxy["uses_angular_surface_flux"]):
            h5.attrs["source"] = "OpenMC mu-binned mesh-surface flux reconstruction"
            h5.attrs["formula"] = "surface_flux = sum_mu(current_mu / mu_midpoint) / face_area"
        else:
            h5.attrs["source"] = "P1 surface-flux proxy from OpenMC partial currents"
            h5.attrs["formula"] = "surface_flux_proxy = 2*(J_out+J_in)/face_area"
        h5.attrs["input"] = data["path"]
        h5.attrs["warning"] = (
            "Diagnostic only: this is heterogeneous surface flux divided by "
            "OpenMC volume-average flux, not a final DONJON ADF."
        )
        h5.attrs["face_area_cm2_unit_height"] = FACE_AREA
        h5.attrs["layout"] = "[mesh_y, mesh_x, group, face]"
        h5.create_dataset("energy_bounds", data=np.asarray(data["energy_bounds"]))
        h5.create_dataset("face_names", data=np.asarray(FACE_NAMES, dtype="S"))
        h5.create_dataset("volume_flux_average", data=data["volume_average"])
        h5.create_dataset("volume_flux_std_dev", data=data["volume_std_dev"])
        h5.create_dataset("cell_volume", data=data["cell_volume"])
        for name, values in proxy.items():
            h5.create_dataset(name, data=values)


def _print_summary(proxy: dict[str, np.ndarray]) -> None:
    ratio = proxy["surface_to_volume_ratio"]
    source = (
        "mu-binned surface flux"
        if bool(proxy["uses_angular_surface_flux"])
        else "P1 current proxy"
    )
    print(f"Surface-flux source: {source}")
    mask = ratio > 0.0
    values = ratio[mask]
    print(
        "Surface/volume proxy ratio over nonzero bins: "
        f"min={np.min(values):.6g}, median={np.median(values):.6g}, "
        f"max={np.max(values):.6g}"
    )
    interior_mask = np.broadcast_to(
        proxy["interior_face_mask"][:, :, np.newaxis, :], ratio.shape
    )
    interior_values = ratio[interior_mask & mask]
    print(
        "Interior-face proxy ratio over nonzero bins: "
        f"min={np.min(interior_values):.6g}, "
        f"median={np.median(interior_values):.6g}, "
        f"max={np.max(interior_values):.6g}"
    )
    for group in range(ratio.shape[2]):
        group_values = ratio[:, :, group, :][ratio[:, :, group, :] > 0.0]
        print(
            f"  group {group + 1}: "
            f"min={np.min(group_values):.6g}, "
            f"median={np.median(group_values):.6g}, "
            f"max={np.max(group_values):.6g}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
