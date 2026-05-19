#!/usr/bin/env python3
"""Unfold C5G7 diagonal-wedge boundary currents to assembly-wise cells."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
DEFAULT_IN = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/c5g7_boundary_currents.h5"
)
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_boundary_currents_full.h5"
)
FULL_SURFACE_NAMES = (
    "x-min out",
    "x-min in",
    "x-max out",
    "x-max in",
    "y-min out",
    "y-min in",
    "y-max out",
    "y-max in",
)
FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
PARTIAL_FACE_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7))

# Raw OpenMC coordinates are (x, y<=0). The DONJON assembly convention used by
# the C5G7 scripts is (X=x, Y=-y), so raw y-min/y-max swap in the full view.
RAW_TO_FULL_SURFACE = np.asarray([0, 1, 2, 3, 6, 7, 4, 5], dtype=np.int64)

# Reflection across the diagonal X == Y swaps x faces with y faces.
DIAGONAL_MIRROR_SURFACE = np.asarray([4, 5, 6, 7, 0, 1, 2, 3], dtype=np.int64)


def main() -> int:
    args = _parse_args()
    raw = _read_raw(args.input)
    full = _unfold(raw)
    checks = _interface_checks(full["mean"])
    _write_full(args.output, raw, full, checks)
    print(f"Wrote {args.output}")
    print(
        "Full current shape: "
        f"{full['mean'].shape} [mesh_y, mesh_x, group, surface]"
    )
    print(
        "Max shared-interface mismatch: "
        f"{checks['max_abs_mismatch']:.6e}"
    )
    if full.get("volume_flux") is not None:
        print(
            "Full volume-flux shape: "
            f"{full['volume_flux']['average'].shape} [mesh_y, mesh_x, group]"
        )
    if full.get("surface_flux") is not None:
        print(
            "Full surface-flux shape: "
            f"{full['surface_flux']['mean'].shape} [mesh_y, mesh_x, group, face]"
        )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_IN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def _read_raw(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        grp = h5["boundary_currents"]
        mean = grp["mean"][:]
        std_dev = grp["std_dev"][:]
        if mean.shape != std_dev.shape or mean.ndim != 4 or mean.shape[-1] != 8:
            raise ValueError(
                "expected raw mean/std_dev shape [mesh_y, mesh_x, group, 8]"
            )
        out = {
            "path": str(path),
            "attrs": dict(h5.attrs),
            "current_attrs": dict(grp.attrs),
            "energy_bounds": h5["energy_bounds"][:],
            "mean": mean,
            "std_dev": std_dev,
            "surface_names": [
                name.decode() if isinstance(name, bytes) else str(name)
                for name in grp["surface_names"][:]
            ],
        }
        if "volume_flux" in h5:
            flux_grp = h5["volume_flux"]
            integral = flux_grp["integral"][:]
            std_dev_flux = flux_grp["std_dev"][:]
            average = flux_grp["average"][:]
            effective_volume = flux_grp["effective_volume"][:]
            if (
                integral.shape != std_dev_flux.shape
                or integral.shape != average.shape
                or integral.ndim != 3
            ):
                raise ValueError(
                    "expected volume flux shape [mesh_y, mesh_x, group]"
                )
            if effective_volume.shape != integral.shape[:2]:
                raise ValueError(
                    "expected volume effective_volume shape [mesh_y, mesh_x]"
                )
            out["volume_flux"] = {
                "attrs": dict(flux_grp.attrs),
                "integral": integral,
                "std_dev": std_dev_flux,
                "average": average,
                "effective_volume": effective_volume,
            }
        if "surface_flux" in h5:
            surf_grp = h5["surface_flux"]
            surface_flux = {
                "attrs": dict(surf_grp.attrs),
                "mean": surf_grp["mean"][:],
                "std_dev": surf_grp["std_dev"][:],
                "face_names": [
                    name.decode() if isinstance(name, bytes) else str(name)
                    for name in surf_grp["face_names"][:]
                ],
                "mu_edges": surf_grp["mu_edges"][:],
                "mu_midpoints": surf_grp["mu_midpoints"][:],
            }
            for name in (
                "angular_current_mean",
                "angular_current_std_dev",
                "partial_surface_flux_mean",
                "partial_surface_flux_std_dev",
            ):
                if name in surf_grp:
                    surface_flux[name] = surf_grp[name][:]
            out["surface_flux"] = surface_flux
        return out


def _unfold(raw: dict[str, object]) -> dict[str, object]:
    raw_mean = np.asarray(raw["mean"], dtype=float)
    raw_std_dev = np.asarray(raw["std_dev"], dtype=float)
    mesh_dim = raw_mean.shape[0]
    if raw_mean.shape[1] != mesh_dim:
        raise ValueError("only square C5G7 assembly meshes are supported")

    source_mean = _raw_to_full_view(raw_mean)
    source_std_dev = _raw_to_full_view(raw_std_dev)

    mean = np.zeros_like(source_mean)
    std_dev = np.zeros_like(source_std_dev)
    source_mesh_index = np.zeros((mesh_dim, mesh_dim, 2), dtype=np.int32)
    source_full_mesh_index = np.zeros((mesh_dim, mesh_dim, 2), dtype=np.int32)
    mirrored = np.zeros((mesh_dim, mesh_dim), dtype=np.bool_)
    diagonal_completed = np.zeros((mesh_dim, mesh_dim), dtype=np.bool_)
    names: list[str] = []

    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            name = f"ASM_Y{y_index + 1:02d}_X{x_index + 1:02d}"
            names.append(name)
            src_x = max(x_index, y_index)
            src_y = min(x_index, y_index)
            source_mesh_index[y_index, x_index] = (src_x + 1, mesh_dim - src_y)
            source_full_mesh_index[y_index, x_index] = (src_x + 1, src_y + 1)
            if x_index > y_index:
                mean[y_index, x_index] = source_mean[src_y, src_x]
                std_dev[y_index, x_index] = source_std_dev[src_y, src_x]
            elif x_index == y_index:
                mean[y_index, x_index] = _complete_diagonal_cell(
                    source_mean[src_y, src_x]
                )
                std_dev[y_index, x_index] = _complete_diagonal_cell(
                    source_std_dev[src_y, src_x]
                )
                diagonal_completed[y_index, x_index] = True
            else:
                mean[y_index, x_index] = _mirror_surfaces(source_mean[src_y, src_x])
                std_dev[y_index, x_index] = _mirror_surfaces(source_std_dev[src_y, src_x])
                mirrored[y_index, x_index] = True

    out = {
        "mean": mean,
        "std_dev": std_dev,
        "net": _net_current(mean),
        "surface_names": FULL_SURFACE_NAMES,
        "assembly_names": np.asarray(names, dtype="S"),
        "source_mesh_index": source_mesh_index,
        "source_full_mesh_index": source_full_mesh_index,
        "mirrored": mirrored,
        "diagonal_completed": diagonal_completed,
    }
    if raw.get("volume_flux") is not None:
        out["volume_flux"] = _unfold_volume_flux(raw["volume_flux"], mesh_dim)
    if raw.get("surface_flux") is not None:
        out["surface_flux"] = _unfold_surface_flux(raw["surface_flux"], mesh_dim)
    return out


def _raw_to_full_view(raw_values: np.ndarray) -> np.ndarray:
    full = np.zeros_like(raw_values)
    mesh_dim = raw_values.shape[0]
    for raw_y in range(mesh_dim):
        full_y = mesh_dim - raw_y - 1
        for raw_surface, full_surface in enumerate(RAW_TO_FULL_SURFACE):
            full[full_y, :, :, full_surface] = raw_values[raw_y, :, :, raw_surface]
    return full


def _raw_to_full_angular_view(raw_values: np.ndarray) -> np.ndarray:
    full = np.zeros_like(raw_values)
    mesh_dim = raw_values.shape[0]
    for raw_y in range(mesh_dim):
        full_y = mesh_dim - raw_y - 1
        for raw_surface, full_surface in enumerate(RAW_TO_FULL_SURFACE):
            full[full_y, :, :, full_surface, :] = raw_values[
                raw_y, :, :, raw_surface, :
            ]
    return full


def _raw_volume_to_full_view(raw_values: np.ndarray) -> np.ndarray:
    full = np.zeros_like(raw_values)
    mesh_dim = raw_values.shape[0]
    for raw_y in range(mesh_dim):
        full_y = mesh_dim - raw_y - 1
        full[full_y, :, :] = raw_values[raw_y, :, :]
    return full


def _mirror_surfaces(values: np.ndarray) -> np.ndarray:
    return values[:, DIAGONAL_MIRROR_SURFACE]


def _complete_diagonal_cell(values: np.ndarray) -> np.ndarray:
    reflected = _mirror_surfaces(values)
    return np.where(values != 0.0, values, reflected)


def _net_current(partial: np.ndarray) -> np.ndarray:
    net = np.zeros(partial.shape[:-1] + (4,), dtype=float)
    net[..., 0] = partial[..., 0] - partial[..., 1]
    net[..., 1] = partial[..., 2] - partial[..., 3]
    net[..., 2] = partial[..., 4] - partial[..., 5]
    net[..., 3] = partial[..., 6] - partial[..., 7]
    return net


def _unfold_volume_flux(
    raw_volume: dict[str, np.ndarray], mesh_dim: int
) -> dict[str, np.ndarray]:
    source_integral = _raw_volume_to_full_view(
        np.asarray(raw_volume["integral"], dtype=float)
    )
    source_std_dev = _raw_volume_to_full_view(
        np.asarray(raw_volume["std_dev"], dtype=float)
    )
    if source_integral.shape[:2] != (mesh_dim, mesh_dim):
        raise ValueError("volume flux mesh shape does not match current mesh")

    integral = np.zeros_like(source_integral)
    std_dev = np.zeros_like(source_std_dev)
    cell_volume = np.full((mesh_dim, mesh_dim), ASSEMBLY_PITCH**2, dtype=float)

    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            src_x = max(x_index, y_index)
            src_y = min(x_index, y_index)
            if x_index == y_index:
                integral[y_index, x_index] = 2.0 * source_integral[src_y, src_x]
                std_dev[y_index, x_index] = 2.0 * source_std_dev[src_y, src_x]
            else:
                integral[y_index, x_index] = source_integral[src_y, src_x]
                std_dev[y_index, x_index] = source_std_dev[src_y, src_x]

    average = np.divide(
        integral,
        cell_volume[:, :, np.newaxis],
        out=np.zeros_like(integral),
        where=cell_volume[:, :, np.newaxis] > 0.0,
    )
    return {
        "integral": integral,
        "std_dev": std_dev,
        "average": average,
        "cell_volume": cell_volume,
    }


def _unfold_surface_flux(
    raw_surface: dict[str, np.ndarray], mesh_dim: int
) -> dict[str, np.ndarray]:
    if "angular_current_mean" not in raw_surface:
        source_mean = _raw_face_to_full_view(np.asarray(raw_surface["mean"], dtype=float))
        source_std_dev = _raw_face_to_full_view(
            np.asarray(raw_surface["std_dev"], dtype=float)
        )
        return {
            "mean": _unfold_face_values(source_mean, mesh_dim),
            "std_dev": _unfold_face_values(source_std_dev, mesh_dim),
            "face_names": FACE_NAMES,
            "mu_edges": np.asarray(raw_surface["mu_edges"], dtype=float),
            "mu_midpoints": np.asarray(raw_surface["mu_midpoints"], dtype=float),
        }

    source_angular = _raw_to_full_angular_view(
        np.asarray(raw_surface["angular_current_mean"], dtype=float)
    )
    source_angular_std_dev = _raw_to_full_angular_view(
        np.asarray(raw_surface["angular_current_std_dev"], dtype=float)
    )
    angular = _unfold_partial_surface_values(source_angular, mesh_dim)
    angular_std_dev = _unfold_partial_surface_values(source_angular_std_dev, mesh_dim)
    (
        partial,
        partial_std_dev,
        surface_flux,
        surface_flux_std_dev,
    ) = _surface_flux_from_angular_currents(
        angular,
        angular_std_dev,
        np.asarray(raw_surface["mu_edges"], dtype=float),
    )
    return {
        "mean": surface_flux,
        "std_dev": surface_flux_std_dev,
        "face_names": FACE_NAMES,
        "surface_names": FULL_SURFACE_NAMES,
        "mu_edges": np.asarray(raw_surface["mu_edges"], dtype=float),
        "mu_midpoints": np.asarray(raw_surface["mu_midpoints"], dtype=float),
        "angular_current_mean": angular,
        "angular_current_std_dev": angular_std_dev,
        "partial_surface_flux_mean": partial,
        "partial_surface_flux_std_dev": partial_std_dev,
    }


def _raw_face_to_full_view(raw_values: np.ndarray) -> np.ndarray:
    full = np.zeros_like(raw_values)
    mesh_dim = raw_values.shape[0]
    # Raw Y coordinates are inverted relative to full assembly coordinates.
    raw_to_full_face = np.asarray([0, 1, 3, 2], dtype=np.int64)
    for raw_y in range(mesh_dim):
        full_y = mesh_dim - raw_y - 1
        for raw_face, full_face in enumerate(raw_to_full_face):
            full[full_y, :, :, full_face] = raw_values[raw_y, :, :, raw_face]
    return full


def _unfold_face_values(source: np.ndarray, mesh_dim: int) -> np.ndarray:
    out = np.zeros_like(source)
    mirror_face = np.asarray([2, 3, 0, 1], dtype=np.int64)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            src_x = max(x_index, y_index)
            src_y = min(x_index, y_index)
            if x_index > y_index:
                out[y_index, x_index] = source[src_y, src_x]
            elif x_index == y_index:
                reflected = source[src_y, src_x][:, mirror_face]
                out[y_index, x_index] = np.where(
                    source[src_y, src_x] != 0.0,
                    source[src_y, src_x],
                    reflected,
                )
            else:
                out[y_index, x_index] = source[src_y, src_x][:, mirror_face]
    return out


def _unfold_partial_surface_values(source: np.ndarray, mesh_dim: int) -> np.ndarray:
    out = np.zeros_like(source)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            src_x = max(x_index, y_index)
            src_y = min(x_index, y_index)
            if x_index > y_index:
                out[y_index, x_index] = source[src_y, src_x]
            elif x_index == y_index:
                out[y_index, x_index] = _complete_diagonal_cell(source[src_y, src_x])
            else:
                out[y_index, x_index] = _mirror_surfaces(source[src_y, src_x])
    return out


def _surface_flux_from_angular_currents(
    angular: np.ndarray,
    angular_std_dev: np.ndarray,
    mu_edges: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mu_midpoints = 0.5 * (mu_edges[:-1] + mu_edges[1:])
    if np.any(mu_midpoints <= 0.0):
        raise ValueError("mu bin midpoints must be positive")
    weights = 1.0 / mu_midpoints
    partial = np.sum(angular * weights, axis=-1) / ASSEMBLY_PITCH
    partial_std_dev = (
        np.sqrt(np.sum((angular_std_dev * weights) ** 2, axis=-1)) / ASSEMBLY_PITCH
    )
    surface_flux = np.zeros(angular.shape[:3] + (len(FACE_NAMES),), dtype=float)
    surface_flux_std_dev = np.zeros_like(surface_flux)
    for face, (out_idx, in_idx) in enumerate(PARTIAL_FACE_PAIRS):
        surface_flux[..., face] = partial[..., out_idx] + partial[..., in_idx]
        surface_flux_std_dev[..., face] = np.sqrt(
            partial_std_dev[..., out_idx] ** 2 + partial_std_dev[..., in_idx] ** 2
        )
    return partial, partial_std_dev, surface_flux, surface_flux_std_dev


def _interface_checks(mean: np.ndarray) -> dict[str, float]:
    mismatches: list[np.ndarray] = []

    # Vertical interfaces: left x-max out/in should pair with right x-min in/out.
    mismatches.append(mean[:, :-1, :, 2] - mean[:, 1:, :, 1])
    mismatches.append(mean[:, :-1, :, 3] - mean[:, 1:, :, 0])

    # Horizontal interfaces: lower y-max out/in should pair with upper y-min in/out.
    mismatches.append(mean[:-1, :, :, 6] - mean[1:, :, :, 5])
    mismatches.append(mean[:-1, :, :, 7] - mean[1:, :, :, 4])

    all_mismatch = np.concatenate([arr.reshape(-1) for arr in mismatches])
    return {
        "max_abs_mismatch": float(np.max(np.abs(all_mismatch))),
        "rms_mismatch": float(np.sqrt(np.mean(all_mismatch**2))),
    }


def _write_full(
    path: Path,
    raw: dict[str, object],
    full: dict[str, object],
    checks: dict[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as h5:
        h5.attrs["source"] = "unfolded C5G7 assembly boundary partial currents"
        h5.attrs["raw_input"] = raw["path"]
        h5.attrs["layout"] = "[mesh_y, mesh_x, group, surface]"
        h5.attrs["surface_convention"] = "DONJON assembly coordinates X=x_openmc, Y=-y_openmc"
        h5.attrs["mirror_rule"] = "source cell is (max(x,y), min(x,y)); x/y faces are swapped when x<y"
        h5.attrs["max_abs_interface_mismatch"] = checks["max_abs_mismatch"]
        h5.attrs["rms_interface_mismatch"] = checks["rms_mismatch"]
        h5.create_dataset("energy_bounds", data=np.asarray(raw["energy_bounds"]))

        grp = h5.create_group("boundary_currents")
        grp.attrs["mesh_dimension"] = np.asarray(full["mean"].shape[:2], dtype=np.int32)
        grp.create_dataset("surface_names", data=np.asarray(FULL_SURFACE_NAMES, dtype="S"))
        grp.create_dataset("assembly_names", data=full["assembly_names"])
        grp.create_dataset("source_mesh_index", data=full["source_mesh_index"])
        grp.create_dataset("source_full_mesh_index", data=full["source_full_mesh_index"])
        grp.create_dataset("mirrored", data=full["mirrored"])
        grp.create_dataset("diagonal_completed", data=full["diagonal_completed"])
        grp.create_dataset("mean", data=full["mean"])
        grp.create_dataset("std_dev", data=full["std_dev"])
        grp.create_dataset("net", data=full["net"])

        volume_flux = full.get("volume_flux")
        if volume_flux is not None:
            flux_grp = h5.create_group("volume_flux")
            flux_grp.attrs["layout"] = "[mesh_y, mesh_x, group]"
            flux_grp.attrs["units_integral"] = "tracklength per source particle"
            flux_grp.attrs["units_average"] = (
                "tracklength per source particle per cm^3"
            )
            flux_grp.attrs["cell_volume_units"] = "cm^3, with unit axial height"
            flux_grp.create_dataset("integral", data=volume_flux["integral"])
            flux_grp.create_dataset("std_dev", data=volume_flux["std_dev"])
            flux_grp.create_dataset("average", data=volume_flux["average"])
            flux_grp.create_dataset("cell_volume", data=volume_flux["cell_volume"])

        surface_flux = full.get("surface_flux")
        if surface_flux is not None:
            surf_grp = h5.create_group("surface_flux")
            surf_grp.attrs["source"] = (
                "unfolded OpenMC angular mesh-surface flux reconstruction"
            )
            surf_grp.attrs["layout"] = "[mesh_y, mesh_x, group, face]"
            surf_grp.attrs["face_area_cm2_unit_height"] = ASSEMBLY_PITCH
            surf_grp.create_dataset(
                "face_names", data=np.asarray(surface_flux["face_names"], dtype="S")
            )
            surf_grp.create_dataset("mu_edges", data=surface_flux["mu_edges"])
            surf_grp.create_dataset("mu_midpoints", data=surface_flux["mu_midpoints"])
            surf_grp.create_dataset("mean", data=surface_flux["mean"])
            surf_grp.create_dataset("std_dev", data=surface_flux["std_dev"])
            if "surface_names" in surface_flux:
                surf_grp.create_dataset(
                    "surface_names",
                    data=np.asarray(surface_flux["surface_names"], dtype="S"),
                )
            for name in (
                "angular_current_mean",
                "angular_current_std_dev",
                "partial_surface_flux_mean",
                "partial_surface_flux_std_dev",
            ):
                if name in surface_flux:
                    surf_grp.create_dataset(name, data=surface_flux[name])

        assembly_grp = h5.create_group("assemblies")
        names = [
            name.decode() if isinstance(name, bytes) else str(name)
            for name in full["assembly_names"]
        ]
        mesh_dim = full["mean"].shape[0]
        for y_index in range(mesh_dim):
            for x_index in range(mesh_dim):
                name = names[y_index * mesh_dim + x_index]
                item = assembly_grp.create_group(name)
                item.attrs["mesh_index"] = np.asarray(
                    (x_index + 1, y_index + 1), dtype=np.int32
                )
                item.attrs["source_mesh_index"] = full["source_mesh_index"][
                    y_index, x_index
                ]
                item.attrs["source_full_mesh_index"] = full["source_full_mesh_index"][
                    y_index, x_index
                ]
                item.attrs["mirrored"] = bool(full["mirrored"][y_index, x_index])
                item.attrs["diagonal_completed"] = bool(
                    full["diagonal_completed"][y_index, x_index]
                )
                item.create_dataset("mean", data=full["mean"][y_index, x_index])
                item.create_dataset("std_dev", data=full["std_dev"][y_index, x_index])
                item.create_dataset("net", data=full["net"][y_index, x_index])
                if volume_flux is not None:
                    item.create_dataset(
                        "volume_flux_integral",
                        data=volume_flux["integral"][y_index, x_index],
                    )
                    item.create_dataset(
                        "volume_flux_std_dev",
                        data=volume_flux["std_dev"][y_index, x_index],
                    )
                    item.create_dataset(
                        "volume_flux_average",
                        data=volume_flux["average"][y_index, x_index],
                    )
                    item.attrs["cell_volume"] = volume_flux["cell_volume"][
                        y_index, x_index
                    ]

                if surface_flux is not None:
                    item.create_dataset(
                        "surface_flux_mean",
                        data=surface_flux["mean"][y_index, x_index],
                    )
                    item.create_dataset(
                        "surface_flux_std_dev",
                        data=surface_flux["std_dev"][y_index, x_index],
                    )


if __name__ == "__main__":
    raise SystemExit(main())
