#!/usr/bin/env python3
"""Run C5G7 assembly-face current and optional surface-flux tallies.

This is a diagnostic for the OpenMC -> DONJON equivalence-factor path. OpenMC
records incoming and outgoing partial currents on the coarse assembly mesh
faces. With ``--mu-bins``, it also bins the mesh-surface current by crossing
angle and reconstructs a scalar surface-flux estimate from
``sum(current_mu / mu_midpoint)``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import h5py
import numpy as np
import openmc


C5G7_DIR = Path("/Users/wen/openmc-workspace/c5g7_converter_test")
DEFAULT_OUT = Path(
    "/Users/wen/dragon-5.1/Donjon/data/openmc2donjon/"
    "c5g7_boundary_currents_smoke.h5"
)
DEFAULT_RUN_DIR = Path("/private/tmp/openmc2donjon_c5g7_boundary_current_smoke")

PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
FACE_AREA = ASSEMBLY_PITCH
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
FACE_NAMES = ("FD_XMIN", "FD_XMAX", "FD_YMIN", "FD_YMAX")
PARTIAL_FACE_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7))


def main() -> int:
    args = _parse_args()
    os.chdir(C5G7_DIR)

    materials = openmc.Materials.from_xml(C5G7_DIR / "materials.xml")
    for material in materials:
        if material._macroscopic is None:
            material.add_macroscopic(material.name)
    geometry = openmc.Geometry.from_xml(C5G7_DIR / "geometry.xml", materials=materials)
    settings = openmc.Settings.from_xml(C5G7_DIR / "settings.xml")
    settings.particles = args.particles
    settings.batches = args.batches
    settings.inactive = args.inactive
    settings.output = {"summary": True, "tallies": False}

    energy_bounds = np.asarray(
        [
            1.0e-5,
            5.17947468e-4,
            2.68269580e-2,
            1.38949549e0,
            7.19685673e1,
            3.72759372e3,
            1.93069773e5,
            1.0e7,
        ],
        dtype=np.float64,
    )

    mesh = _assembly_mesh(args.assembly_mesh)
    energy_filter = openmc.EnergyFilter(energy_bounds)
    mesh_surface_filter = openmc.MeshSurfaceFilter(mesh)
    current_tally = openmc.Tally(name="assembly_mesh_surface_current")
    current_tally.filters = [mesh_surface_filter, energy_filter]
    current_tally.scores = ["current"]

    tallies = [current_tally]
    angular_tally_name = None
    mu_edges = None
    if args.mu_bins:
        mu_edges = np.linspace(0.0, 1.0, args.mu_bins + 1)
        angular_tally = openmc.Tally(name="assembly_mesh_mu_surface_current")
        angular_tally.filters = [
            mesh_surface_filter,
            openmc.MuSurfaceFilter(mu_edges),
            energy_filter,
        ]
        angular_tally.scores = ["current"]
        angular_tally_name = angular_tally.name
        tallies.append(angular_tally)

    flux_tally = openmc.Tally(name="assembly_mesh_volume_flux")
    flux_tally.filters = [openmc.MeshFilter(mesh), energy_filter]
    flux_tally.scores = ["flux"]
    tallies.append(flux_tally)

    model = openmc.Model(
        geometry, materials, settings, openmc.Tallies(tallies)
    )
    args.run_dir.mkdir(parents=True, exist_ok=True)
    model.export_to_xml(directory=str(args.run_dir))

    print(
        "Running OpenMC boundary-current diagnostic: "
        f"{args.particles} particles x {args.batches} batches "
        f"({args.inactive} inactive)"
    )
    print(f"run_dir: {args.run_dir}")
    sp_path = model.run(output=True, threads=args.threads, cwd=str(args.run_dir))
    print(f"statepoint: {sp_path}")

    with openmc.StatePoint(str(sp_path)) as sp:
        print(f"keff = {sp.keff.nominal_value:.5f} +/- {sp.keff.std_dev * 1e5:.0f} pcm")
        _dump_currents(
            sp,
            current_tally.name,
            flux_tally.name,
            args.output,
            energy_bounds,
            args.assembly_mesh,
            args.particles,
            args.batches,
            args.inactive,
            angular_tally_name=angular_tally_name,
            mu_edges=mu_edges,
        )
    print(f"Wrote {args.output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly-mesh", type=int, default=3)
    parser.add_argument("--particles", type=int, default=1000)
    parser.add_argument("--batches", type=int, default=20)
    parser.add_argument("--inactive", type=int, default=5)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--mu-bins",
        type=int,
        default=0,
        help=(
            "also tally mesh-surface current in this many mu bins over [0, 1] "
            "and reconstruct scalar surface flux"
        ),
    )
    args = parser.parse_args()
    if args.assembly_mesh <= 0:
        parser.error("--assembly-mesh must be positive")
    if args.batches <= args.inactive:
        parser.error("--batches must be greater than --inactive")
    if args.mu_bins < 0:
        parser.error("--mu-bins must be non-negative")
    return args


def _assembly_mesh(dimension: int) -> openmc.RegularMesh:
    side = dimension * ASSEMBLY_PITCH
    mesh = openmc.RegularMesh(mesh_id=2001, name="C5G7 assembly face mesh")
    mesh.dimension = (dimension, dimension)
    mesh.lower_left = (0.0, -side)
    mesh.upper_right = (side, 0.0)
    return mesh


def _dump_currents(
    sp: openmc.StatePoint,
    current_tally_name: str,
    flux_tally_name: str,
    out_path: Path,
    energy_bounds: np.ndarray,
    assembly_mesh: int,
    particles: int,
    batches: int,
    inactive: int,
    *,
    angular_tally_name: str | None,
    mu_edges: np.ndarray | None,
) -> None:
    tally = sp.get_tally(name=current_tally_name)
    mean = _reshape_current_values(
        tally.get_values(value="mean"), assembly_mesh, len(energy_bounds) - 1
    )
    std_dev = _reshape_current_values(
        tally.get_values(value="std_dev"), assembly_mesh, len(energy_bounds) - 1
    )
    flux_tally = sp.get_tally(name=flux_tally_name)
    flux_integral = _reshape_volume_values(
        flux_tally.get_values(value="mean"), assembly_mesh, len(energy_bounds) - 1
    )
    flux_std_dev = _reshape_volume_values(
        flux_tally.get_values(value="std_dev"), assembly_mesh, len(energy_bounds) - 1
    )
    effective_volume = _raw_effective_volumes(assembly_mesh)
    flux_average = np.divide(
        flux_integral,
        effective_volume[:, :, np.newaxis],
        out=np.zeros_like(flux_integral),
        where=effective_volume[:, :, np.newaxis] > 0.0,
    )
    angular = None
    angular_std_dev = None
    surface_flux = None
    surface_flux_std_dev = None
    partial_surface_flux = None
    partial_surface_flux_std_dev = None
    if angular_tally_name is not None:
        if mu_edges is None:
            raise ValueError("mu_edges are required for angular surface-current tally")
        angular_tally = sp.get_tally(name=angular_tally_name)
        angular = _reshape_angular_current_values(
            angular_tally.get_values(value="mean"),
            assembly_mesh,
            len(energy_bounds) - 1,
            len(mu_edges) - 1,
        )
        angular_std_dev = _reshape_angular_current_values(
            angular_tally.get_values(value="std_dev"),
            assembly_mesh,
            len(energy_bounds) - 1,
            len(mu_edges) - 1,
        )
        (
            partial_surface_flux,
            partial_surface_flux_std_dev,
            surface_flux,
            surface_flux_std_dev,
        ) = _surface_flux_from_angular_currents(angular, angular_std_dev, mu_edges)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w") as h5:
        h5.attrs["source"] = "OpenMC MeshSurfaceFilter current tally plus mesh flux"
        h5.attrs["note"] = (
            "Partial currents only; OpenMC does not support mesh-surface flux "
            "tallies. A P1 surface-flux proxy can be derived from partial "
            "currents and compared with the volume flux."
        )
        h5.attrs["particles"] = particles
        h5.attrs["batches"] = batches
        h5.attrs["inactive"] = inactive
        h5.attrs["energy_order"] = "group-index order, high energy to low energy"
        h5.create_dataset("energy_bounds", data=energy_bounds)

        grp = h5.create_group("boundary_currents")
        grp.attrs["layout"] = "[mesh_y, mesh_x, group, surface]"
        grp.attrs["mesh_region"] = (
            "raw OpenMC diagonal-symmetry wedge; zero cells are outside the "
            "modeled wedge, not physical full-core zero currents"
        )
        grp.attrs["mesh_dimension"] = np.asarray(
            (assembly_mesh, assembly_mesh), dtype=np.int32
        )
        grp.attrs["mesh_lower_left"] = np.asarray((0.0, -assembly_mesh * ASSEMBLY_PITCH))
        grp.attrs["mesh_upper_right"] = np.asarray((assembly_mesh * ASSEMBLY_PITCH, 0.0))
        grp.attrs["units"] = "particles per source particle"
        grp.create_dataset("surface_names", data=np.asarray(SURFACE_NAMES_2D, dtype="S"))
        grp.create_dataset("mean", data=mean)
        grp.create_dataset("std_dev", data=std_dev)

        net = _net_current(mean)
        grp.create_dataset("net", data=net)

        flux_grp = h5.create_group("volume_flux")
        flux_grp.attrs["layout"] = "[mesh_y, mesh_x, group]"
        flux_grp.attrs["units_integral"] = "tracklength per source particle"
        flux_grp.attrs["units_average"] = "tracklength per source particle per cm^3"
        flux_grp.attrs["mesh_region"] = grp.attrs["mesh_region"]
        flux_grp.create_dataset("effective_volume", data=effective_volume)
        flux_grp.create_dataset("integral", data=flux_integral)
        flux_grp.create_dataset("std_dev", data=flux_std_dev)
        flux_grp.create_dataset("average", data=flux_average)

        if angular is not None:
            surf_grp = h5.create_group("surface_flux")
            surf_grp.attrs["source"] = (
                "OpenMC MeshSurfaceFilter current binned by MuSurfaceFilter"
            )
            surf_grp.attrs["layout"] = "[mesh_y, mesh_x, group, face]"
            surf_grp.attrs["partial_layout"] = (
                "[mesh_y, mesh_x, group, surface, mu]"
            )
            surf_grp.attrs["formula"] = (
                "surface_flux = sum_mu(current_mu / mu_midpoint) / face_area"
            )
            surf_grp.attrs["face_area_cm2_unit_height"] = FACE_AREA
            surf_grp.create_dataset("face_names", data=np.asarray(FACE_NAMES, dtype="S"))
            surf_grp.create_dataset(
                "surface_names", data=np.asarray(SURFACE_NAMES_2D, dtype="S")
            )
            surf_grp.create_dataset("mu_edges", data=mu_edges)
            surf_grp.create_dataset(
                "mu_midpoints", data=0.5 * (mu_edges[:-1] + mu_edges[1:])
            )
            surf_grp.create_dataset("angular_current_mean", data=angular)
            surf_grp.create_dataset("angular_current_std_dev", data=angular_std_dev)
            surf_grp.create_dataset(
                "partial_surface_flux_mean", data=partial_surface_flux
            )
            surf_grp.create_dataset(
                "partial_surface_flux_std_dev", data=partial_surface_flux_std_dev
            )
            surf_grp.create_dataset("mean", data=surface_flux)
            surf_grp.create_dataset("std_dev", data=surface_flux_std_dev)


def _reshape_current_values(values: np.ndarray, mesh_dim: int, ngroups: int) -> np.ndarray:
    """Return values as [y, x, group, surface] in high-to-low energy order."""
    values = np.asarray(values, dtype=float).reshape(-1)
    nsurfaces = len(SURFACE_NAMES_2D)
    expected = mesh_dim * mesh_dim * nsurfaces * ngroups
    if values.size != expected:
        raise ValueError(f"expected {expected} current values, found {values.size}")

    out = np.zeros((mesh_dim, mesh_dim, ngroups, nsurfaces), dtype=float)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            cell = y_index * mesh_dim + x_index
            for surface in range(nsurfaces):
                start = (cell * nsurfaces + surface) * ngroups
                stop = start + ngroups
                # EnergyFilter stores low-to-high energy bins; converter HDF5
                # keeps OpenMC group-index order, high-to-low.
                out[y_index, x_index, :, surface] = values[start:stop][::-1]
    return out


def _reshape_volume_values(values: np.ndarray, mesh_dim: int, ngroups: int) -> np.ndarray:
    """Return mesh values as [y, x, group] in high-to-low energy order."""
    values = np.asarray(values, dtype=float).reshape(-1)
    expected = mesh_dim * mesh_dim * ngroups
    if values.size != expected:
        raise ValueError(f"expected {expected} volume values, found {values.size}")

    out = np.zeros((mesh_dim, mesh_dim, ngroups), dtype=float)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            cell = y_index * mesh_dim + x_index
            start = cell * ngroups
            stop = start + ngroups
            out[y_index, x_index] = values[start:stop][::-1]
    return out


def _reshape_angular_current_values(
    values: np.ndarray,
    mesh_dim: int,
    ngroups: int,
    nmu: int,
) -> np.ndarray:
    """Return angular currents as [y, x, group, surface, mu]."""
    values = np.asarray(values, dtype=float).reshape(-1)
    nsurfaces = len(SURFACE_NAMES_2D)
    expected = mesh_dim * mesh_dim * nsurfaces * nmu * ngroups
    if values.size != expected:
        raise ValueError(f"expected {expected} angular current values, found {values.size}")

    out = np.zeros((mesh_dim, mesh_dim, ngroups, nsurfaces, nmu), dtype=float)
    for y_index in range(mesh_dim):
        for x_index in range(mesh_dim):
            cell = y_index * mesh_dim + x_index
            for surface in range(nsurfaces):
                for mu_index in range(nmu):
                    start = ((cell * nsurfaces + surface) * nmu + mu_index) * ngroups
                    stop = start + ngroups
                    out[y_index, x_index, :, surface, mu_index] = values[start:stop][::-1]
    return out


def _surface_flux_from_angular_currents(
    angular: np.ndarray,
    angular_std_dev: np.ndarray,
    mu_edges: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mu_midpoints = 0.5 * (mu_edges[:-1] + mu_edges[1:])
    if np.any(mu_midpoints <= 0.0):
        raise ValueError("mu bin midpoints must be positive")
    if angular.shape != angular_std_dev.shape:
        raise ValueError("angular current mean/std_dev shapes differ")
    if angular.shape[-1] != mu_midpoints.size:
        raise ValueError("angular current mu dimension does not match mu_edges")

    weights = 1.0 / mu_midpoints
    partial = np.sum(angular * weights, axis=-1) / FACE_AREA
    partial_std_dev = np.sqrt(np.sum((angular_std_dev * weights) ** 2, axis=-1)) / FACE_AREA

    surface_flux = np.zeros(angular.shape[:3] + (len(FACE_NAMES),), dtype=float)
    surface_flux_std_dev = np.zeros_like(surface_flux)
    for face, (out_idx, in_idx) in enumerate(PARTIAL_FACE_PAIRS):
        surface_flux[..., face] = partial[..., out_idx] + partial[..., in_idx]
        surface_flux_std_dev[..., face] = np.sqrt(
            partial_std_dev[..., out_idx] ** 2 + partial_std_dev[..., in_idx] ** 2
        )
    return partial, partial_std_dev, surface_flux, surface_flux_std_dev


def _raw_effective_volumes(mesh_dim: int) -> np.ndarray:
    full_volume = ASSEMBLY_PITCH**2
    volume = np.zeros((mesh_dim, mesh_dim), dtype=float)
    for raw_y in range(mesh_dim):
        full_y = mesh_dim - raw_y - 1
        for x_index in range(mesh_dim):
            if x_index > full_y:
                volume[raw_y, x_index] = full_volume
            elif x_index == full_y:
                volume[raw_y, x_index] = 0.5 * full_volume
    return volume


def _net_current(partial: np.ndarray) -> np.ndarray:
    """Combine outgoing minus incoming current for each geometric face."""
    net = np.zeros(partial.shape[:-1] + (4,), dtype=float)
    net[..., 0] = partial[..., 0] - partial[..., 1]
    net[..., 1] = partial[..., 2] - partial[..., 3]
    net[..., 2] = partial[..., 4] - partial[..., 5]
    net[..., 3] = partial[..., 6] - partial[..., 7]
    return net


if __name__ == "__main__":
    raise SystemExit(main())
