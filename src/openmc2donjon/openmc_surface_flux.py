"""Export OpenMC mesh-surface angular-current tallies as face-flux HDF5."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from . import __version__
from .hdf5_names import read_mixture_names


SCHEMA = "openmc2donjon.surface-flux.v1"
PASS_DECISION = "openmc2donjon_surface_flux_export_passed"
DEFAULT_TALLY_NAME = "openmc2donjon_surface_current_mu"
DEFAULT_FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
SURFACE_NAMES_2D = (
    "x-min out",
    "x-min in",
    "x-max out",
    "x-max in",
    "y-min out",
    "y-min in",
    "y-max out",
    "y-max in",
)
PARTIAL_FACE_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7))


@dataclass(frozen=True)
class SurfaceFluxReport:
    statepoint: Path | None
    output_h5: Path
    tally_name: str
    mesh_shape: tuple[int, int]
    mixture_names: tuple[str, ...]
    face_names: tuple[str, ...]
    energy_groups: int
    mu_edges: tuple[float, ...]
    face_area: float
    minimum: float
    median: float
    maximum: float


def export_openmc_surface_flux(
    statepoint: Path,
    output_h5: Path,
    *,
    mgxs_h5: Path | None = None,
    tally_name: str = DEFAULT_TALLY_NAME,
    mesh_shape: tuple[int, int] | None = None,
    mu_edges: tuple[float, ...],
    face_area: float = 1.0,
    face_names: tuple[str, ...] = DEFAULT_FACE_NAMES,
    mixture_names: tuple[str, ...] | None = None,
    energy_bounds: tuple[float, ...] | None = None,
    force: bool = False,
    summary_json: Path | None = None,
) -> SurfaceFluxReport:
    """Export an OpenMC statepoint angular-current tally to face-flux HDF5."""

    import openmc

    statepoint = Path(statepoint)
    if not statepoint.exists():
        raise FileNotFoundError(f"statepoint does not exist: {statepoint}")

    metadata = _resolve_metadata(
        mgxs_h5=mgxs_h5,
        mixture_names=mixture_names,
        energy_bounds=energy_bounds,
        mesh_shape=mesh_shape,
    )
    mesh_shape = metadata["mesh_shape"]
    mixture_names = metadata["mixture_names"]
    energy_bounds_array = metadata["energy_bounds"]
    energy_groups = len(energy_bounds_array) - 1
    _validate_common(
        mesh_shape=mesh_shape,
        mixture_names=mixture_names,
        face_names=face_names,
        mu_edges=mu_edges,
        face_area=face_area,
        energy_groups=energy_groups,
    )

    with openmc.StatePoint(str(statepoint)) as sp:
        tally = sp.get_tally(name=tally_name)
        mean = tally.get_values(value="mean")
        std_dev = tally.get_values(value="std_dev")

    angular_mean = reshape_angular_surface_current(
        mean,
        mesh_shape=mesh_shape,
        energy_groups=energy_groups,
        mu_edges=mu_edges,
    )
    angular_std_dev = reshape_angular_surface_current(
        std_dev,
        mesh_shape=mesh_shape,
        energy_groups=energy_groups,
        mu_edges=mu_edges,
    )
    _partial_mean, _partial_std, surface_flux, surface_flux_std = (
        reconstruct_surface_flux_from_angular_currents(
            angular_mean,
            angular_std_dev,
            mu_edges=mu_edges,
            face_area=face_area,
        )
    )
    return write_surface_flux_hdf5(
        output_h5,
        surface_flux=surface_flux,
        surface_flux_std_dev=surface_flux_std,
        energy_bounds=energy_bounds_array,
        mixture_names=mixture_names,
        face_names=face_names,
        tally_name=tally_name,
        mu_edges=mu_edges,
        face_area=face_area,
        statepoint=statepoint,
        force=force,
        summary_json=summary_json,
    )


def write_surface_flux_hdf5(
    output_h5: Path,
    *,
    surface_flux: np.ndarray,
    surface_flux_std_dev: np.ndarray,
    energy_bounds: np.ndarray,
    mixture_names: tuple[str, ...],
    face_names: tuple[str, ...],
    tally_name: str,
    mu_edges: tuple[float, ...],
    face_area: float,
    statepoint: Path | None = None,
    force: bool = False,
    summary_json: Path | None = None,
) -> SurfaceFluxReport:
    """Write normalized surface flux values in the flux-ratio input layout."""

    import h5py

    output_h5 = Path(output_h5)
    if output_h5.exists() and not force:
        raise FileExistsError(f"output already exists; use --force to overwrite: {output_h5}")
    energy_bounds = np.asarray(energy_bounds, dtype=float).reshape(-1)
    surface_flux = np.asarray(surface_flux, dtype=float)
    surface_flux_std_dev = np.asarray(surface_flux_std_dev, dtype=float)
    if surface_flux.shape != surface_flux_std_dev.shape:
        raise ValueError("surface flux mean/std_dev shapes differ")
    if surface_flux.ndim != 4:
        raise ValueError("surface flux must have shape (Y, X, G, F)")
    mesh_shape = (int(surface_flux.shape[0]), int(surface_flux.shape[1]))
    energy_groups = int(surface_flux.shape[2])
    _validate_common(
        mesh_shape=mesh_shape,
        mixture_names=mixture_names,
        face_names=face_names,
        mu_edges=mu_edges,
        face_area=face_area,
        energy_groups=energy_groups,
    )
    if energy_bounds.shape != (energy_groups + 1,):
        raise ValueError(
            f"energy_bounds must have shape ({energy_groups + 1},), got {energy_bounds.shape}"
        )
    if not np.all(np.isfinite(surface_flux)) or not np.all(np.isfinite(surface_flux_std_dev)):
        raise ValueError("surface flux mean/std_dev must be finite")

    output_h5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_h5, "w") as h5:
        h5.attrs["schema"] = SCHEMA
        h5.attrs["package_version"] = __version__
        h5.attrs["source"] = "OpenMC MeshSurfaceFilter current binned by MuSurfaceFilter"
        h5.attrs["tally_name"] = tally_name
        h5.attrs["formula"] = "surface_flux = sum_mu(current_mu / mu_midpoint) / face_area"
        h5.attrs["energy_order"] = "group-index order, high energy to low energy"
        h5.attrs["face_area"] = float(face_area)
        if statepoint is not None:
            h5.attrs["statepoint"] = str(statepoint)
        h5.create_dataset("energy_bounds", data=energy_bounds)
        h5.create_dataset(
            "mixture_names",
            data=np.asarray(mixture_names, dtype="S").reshape(mesh_shape),
        )
        h5.create_dataset("face_names", data=np.asarray(face_names, dtype="S"))
        group = h5.create_group("surface_flux")
        group.attrs["layout"] = "[mesh_y, mesh_x, group, face]"
        group.attrs["face_area"] = float(face_area)
        group.create_dataset("mean", data=surface_flux)
        group.create_dataset("std_dev", data=surface_flux_std_dev)
        group.create_dataset("face_names", data=np.asarray(face_names, dtype="S"))
        group.create_dataset("mu_edges", data=np.asarray(mu_edges, dtype=float))
        group.create_dataset(
            "mu_midpoints",
            data=0.5 * (np.asarray(mu_edges[:-1]) + np.asarray(mu_edges[1:])),
        )

    stats = _stats(surface_flux)
    report = SurfaceFluxReport(
        statepoint=statepoint,
        output_h5=output_h5,
        tally_name=tally_name,
        mesh_shape=mesh_shape,
        mixture_names=mixture_names,
        face_names=face_names,
        energy_groups=energy_groups,
        mu_edges=tuple(float(value) for value in mu_edges),
        face_area=float(face_area),
        minimum=stats["min"],
        median=stats["median"],
        maximum=stats["max"],
    )
    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def reshape_angular_surface_current(
    values: np.ndarray,
    *,
    mesh_shape: tuple[int, int],
    energy_groups: int,
    mu_edges: tuple[float, ...],
) -> np.ndarray:
    """Return OpenMC tally values as ``[mesh_y, mesh_x, group, surface, mu]``."""

    values = np.asarray(values, dtype=float).reshape(-1)
    mesh_y, mesh_x = mesh_shape
    nsurfaces = len(SURFACE_NAMES_2D)
    nmu = len(mu_edges) - 1
    expected = mesh_y * mesh_x * nsurfaces * nmu * energy_groups
    if values.size != expected:
        raise ValueError(f"expected {expected} angular-current values, found {values.size}")

    out = np.zeros((mesh_y, mesh_x, energy_groups, nsurfaces, nmu), dtype=float)
    for y_index in range(mesh_y):
        for x_index in range(mesh_x):
            cell = y_index * mesh_x + x_index
            for surface in range(nsurfaces):
                for mu_index in range(nmu):
                    start = ((cell * nsurfaces + surface) * nmu + mu_index) * energy_groups
                    stop = start + energy_groups
                    # OpenMC EnergyFilter bins are low-to-high; MGXS handoff
                    # arrays are high-to-low group-index order.
                    out[y_index, x_index, :, surface, mu_index] = values[start:stop][::-1]
    return out


def reconstruct_surface_flux_from_angular_currents(
    angular_mean: np.ndarray,
    angular_std_dev: np.ndarray,
    *,
    mu_edges: tuple[float, ...],
    face_area: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reconstruct scalar face flux from mu-binned surface current."""

    angular_mean = np.asarray(angular_mean, dtype=float)
    angular_std_dev = np.asarray(angular_std_dev, dtype=float)
    if angular_mean.shape != angular_std_dev.shape:
        raise ValueError("angular current mean/std_dev shapes differ")
    if angular_mean.ndim != 5 or angular_mean.shape[-2] != len(SURFACE_NAMES_2D):
        raise ValueError("angular current must have shape (Y, X, G, surface, mu)")
    mu_edges_array = np.asarray(mu_edges, dtype=float)
    mu_midpoints = 0.5 * (mu_edges_array[:-1] + mu_edges_array[1:])
    if np.any(mu_midpoints <= 0.0):
        raise ValueError("mu bin midpoints must be positive")
    if angular_mean.shape[-1] != mu_midpoints.size:
        raise ValueError("angular current mu dimension does not match mu_edges")
    if face_area <= 0.0 or not np.isfinite(face_area):
        raise ValueError("face_area must be positive and finite")

    weights = 1.0 / mu_midpoints
    partial = np.sum(angular_mean * weights, axis=-1) / face_area
    partial_std_dev = np.sqrt(np.sum((angular_std_dev * weights) ** 2, axis=-1)) / face_area
    surface_flux = np.zeros(angular_mean.shape[:3] + (len(DEFAULT_FACE_NAMES),), dtype=float)
    surface_flux_std_dev = np.zeros_like(surface_flux)
    for face, (out_idx, in_idx) in enumerate(PARTIAL_FACE_PAIRS):
        surface_flux[..., face] = partial[..., out_idx] + partial[..., in_idx]
        surface_flux_std_dev[..., face] = np.sqrt(
            partial_std_dev[..., out_idx] ** 2 + partial_std_dev[..., in_idx] ** 2
        )
    return partial, partial_std_dev, surface_flux, surface_flux_std_dev


def print_report(report: SurfaceFluxReport) -> None:
    print("OpenMC-to-DONJON surface flux export")
    print(f"  schema: {SCHEMA}")
    if report.statepoint is not None:
        print(f"  statepoint: {report.statepoint}")
    print(f"  output: {report.output_h5}")
    print(
        f"  tally={report.tally_name} mesh={report.mesh_shape[0]}x{report.mesh_shape[1]} "
        f"mixtures={len(report.mixture_names)} groups={report.energy_groups} "
        f"faces={','.join(report.face_names)}"
    )
    print(
        "  surface_flux range: "
        f"min={report.minimum:.6g} median={report.median:.6g} max={report.maximum:.6g}"
    )
    print()
    print("Surface flux export decision")
    print(f"  {PASS_DECISION}")


def write_summary(path: Path, report: SurfaceFluxReport) -> None:
    payload = {
        "schema": SCHEMA,
        "package_version": __version__,
        "decision": PASS_DECISION,
        "statepoint": None if report.statepoint is None else str(report.statepoint),
        "output_h5": str(report.output_h5),
        "tally_name": report.tally_name,
        "mesh_shape": list(report.mesh_shape),
        "mixture_count": len(report.mixture_names),
        "mixture_names": list(report.mixture_names),
        "face_names": list(report.face_names),
        "energy_groups": report.energy_groups,
        "mu_edges": list(report.mu_edges),
        "face_area": report.face_area,
        "min": report.minimum,
        "median": report.median,
        "max": report.maximum,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_metadata(
    *,
    mgxs_h5: Path | None,
    mixture_names: tuple[str, ...] | None,
    energy_bounds: tuple[float, ...] | None,
    mesh_shape: tuple[int, int] | None,
) -> dict[str, object]:
    mgxs_names: tuple[str, ...] | None = None
    mgxs_energy: np.ndarray | None = None
    if mgxs_h5 is not None:
        import h5py

        with h5py.File(mgxs_h5, "r") as h5:
            if "mixtures" not in h5:
                raise ValueError(f"{mgxs_h5}: missing /mixtures group")
            mgxs_names = read_mixture_names(h5)
            if "energy_bounds" not in h5:
                raise ValueError(f"{mgxs_h5}: missing /energy_bounds dataset")
            mgxs_energy = np.asarray(h5["energy_bounds"][:], dtype=float)
    names = mixture_names or mgxs_names
    if not names:
        raise ValueError("mixture names must be supplied, either via --mgxs or --mixture-names")
    energy = np.asarray(energy_bounds if energy_bounds is not None else mgxs_energy, dtype=float)
    if energy.size == 0:
        raise ValueError("energy bounds must be supplied, either via --mgxs or --energy-bounds")
    if mesh_shape is None:
        mesh_shape = (1, len(names))
    return {
        "mesh_shape": mesh_shape,
        "mixture_names": tuple(names),
        "energy_bounds": energy,
    }


def _validate_common(
    *,
    mesh_shape: tuple[int, int],
    mixture_names: tuple[str, ...],
    face_names: tuple[str, ...],
    mu_edges: tuple[float, ...],
    face_area: float,
    energy_groups: int,
) -> None:
    mesh_y, mesh_x = mesh_shape
    if mesh_y <= 0 or mesh_x <= 0:
        raise ValueError("mesh_shape entries must be positive")
    if len(mixture_names) != mesh_y * mesh_x:
        raise ValueError(
            f"mixture count {len(mixture_names)} does not match mesh_shape {mesh_shape}"
        )
    if len(face_names) != len(DEFAULT_FACE_NAMES):
        raise ValueError("exactly four face names are required for 2D mesh-surface export")
    if energy_groups <= 0:
        raise ValueError("energy group count must be positive")
    mu_edges_array = np.asarray(mu_edges, dtype=float)
    if mu_edges_array.ndim != 1 or mu_edges_array.size < 2:
        raise ValueError("mu_edges must contain at least two values")
    if not np.all(np.isfinite(mu_edges_array)) or not np.all(np.diff(mu_edges_array) > 0.0):
        raise ValueError("mu_edges must be finite and strictly ascending")
    if face_area <= 0.0 or not np.isfinite(face_area):
        raise ValueError("face_area must be positive and finite")


def _stats(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "max": float(np.max(values)),
    }
