#!/usr/bin/env python3
"""Export a local C5G7 OpenMC statepoint through the package HDF5 exporter."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import openmc
import openmc.mgxs as mgxs

from openmc2donjon import DomainExportSpec, export_openmc_mgxs_library


DEFAULT_C5G7_DIR = Path("/Users/wen/openmc-workspace/c5g7_converter_test")
PITCH = 1.26
ASSEMBLY_PITCH = 17 * PITCH
SIDE = 3 * ASSEMBLY_PITCH
C5G7_7G_BOUNDS = [
    1.0e-5,
    5.17947468e-4,
    2.68269580e-2,
    1.38949549e0,
    7.19685673e1,
    3.72759372e3,
    1.93069773e5,
    1.0e7,
]


def main() -> int:
    args = _parse_args()
    previous_cwd = Path.cwd()
    os.chdir(args.c5g7_dir)
    try:
        materials = openmc.Materials.from_xml("materials.xml")
        for material in materials:
            if material._macroscopic is None:
                material.add_macroscopic(material.name)
        geometry = openmc.Geometry.from_xml("geometry.xml", materials=materials)
        library = _build_library(
            geometry,
            domain_mode=args.domain_mode,
            assembly_mesh=args.assembly_mesh,
            legendre_order=args.legendre_order,
        )

        tallies = openmc.Tallies()
        library.add_to_tallies_file(tallies, merge=True)

        with openmc.StatePoint(str(args.statepoint)) as statepoint:
            library.load_from_statepoint(statepoint)
            keff = statepoint.keff
            print(f"keff = {keff.nominal_value:.5f} +/- {keff.std_dev * 1e5:.0f} pcm")

        _export_library(
            library,
            args.output,
            domain_mode=args.domain_mode,
            assembly_mesh=args.assembly_mesh,
        )
    finally:
        os.chdir(previous_cwd)

    print(f"wrote {args.output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c5g7-dir", type=Path, default=DEFAULT_C5G7_DIR)
    parser.add_argument("--statepoint", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--domain-mode",
        choices=("material", "assembly"),
        default="assembly",
    )
    parser.add_argument("--assembly-mesh", type=int, default=3)
    parser.add_argument("--legendre-order", type=int, default=1)
    args = parser.parse_args()
    args.c5g7_dir = args.c5g7_dir.resolve()
    args.statepoint = args.statepoint.resolve()
    args.output = args.output.resolve()
    if args.assembly_mesh <= 0:
        parser.error("--assembly-mesh must be positive")
    if args.legendre_order < 0:
        parser.error("--legendre-order must be non-negative")
    return args


def _build_library(
    geometry: openmc.Geometry,
    *,
    domain_mode: str,
    assembly_mesh: int,
    legendre_order: int,
) -> mgxs.Library:
    library = mgxs.Library(geometry)
    library.energy_groups = mgxs.EnergyGroups(C5G7_7G_BOUNDS)
    library.mgxs_types = [
        "total",
        "absorption",
        "fission",
        "nu-fission",
        "chi",
        "consistent nu-scatter matrix",
    ]
    if domain_mode == "material":
        library.domain_type = "material"
        library.domains = list(geometry.get_all_materials().values())
    else:
        mesh = openmc.RegularMesh(mesh_id=1001, name="C5G7 assembly mesh")
        mesh.dimension = (assembly_mesh, assembly_mesh, 1)
        mesh.lower_left = (0.0, -SIDE, 0.0)
        mesh.upper_right = (SIDE, 0.0, 1.0)
        library.domain_type = "mesh"
        library.domains = [mesh]
    library.by_nuclide = False
    library.legendre_order = legendre_order
    library.build_library()
    return library


def _export_library(
    library: mgxs.Library,
    output: Path,
    *,
    domain_mode: str,
    assembly_mesh: int,
) -> None:
    root_attrs = {
        "scatter_axes": "moment,G_in,G_out",
        "domain_mode": domain_mode,
    }
    if domain_mode == "material":
        export_openmc_mgxs_library(library, output, root_attrs=root_attrs)
    else:
        export_openmc_mgxs_library(
            library,
            output,
            domain_specs=_assembly_specs(library.domains[0], assembly_mesh),
            root_attrs={
                **root_attrs,
                "mesh_dimension": assembly_mesh,
                "mesh_lower_left": np.asarray((0.0, -SIDE, 0.0), dtype=float),
                "mesh_upper_right": np.asarray((SIDE, 0.0, 1.0), dtype=float),
            },
        )
    if library.legendre_order > 0:
        _add_p1_transport_total(output)


def _assembly_specs(domain: object, assembly_mesh: int) -> list[DomainExportSpec]:
    full_volume = (SIDE / assembly_mesh) ** 2
    specs = []
    for y_index in range(assembly_mesh):
        for x_index in range(assembly_mesh):
            source_x = max(x_index, y_index)
            source_y = min(x_index, y_index)
            subdomain = (source_x + 1, assembly_mesh - source_y, 1)
            specs.append(
                DomainExportSpec(
                    domain=domain,
                    name=f"ASM_Y{y_index + 1:02d}_X{x_index + 1:02d}",
                    xs_kwargs={"subdomains": [subdomain]},
                    volume=full_volume,
                    attrs={
                        "mesh_index": np.asarray(
                            (x_index + 1, y_index + 1, 1),
                            dtype=np.int32,
                        ),
                        "source_subdomain": np.asarray(subdomain, dtype=np.int32),
                    },
                )
            )
    return specs


def _add_p1_transport_total(output: Path) -> None:
    import h5py

    with h5py.File(output, "r+") as h5:
        for name, group in h5["mixtures"].items():
            if "transport_total" in group:
                continue
            scatter = np.asarray(group["scatter_matrix"][:], dtype=float)
            if scatter.shape[0] <= 1:
                continue
            transport_total = np.asarray(group["total"][:], dtype=float) - scatter[1].sum(
                axis=1
            )
            if np.any(transport_total <= 0.0):
                raise ValueError(
                    f"non-positive transport total in domain {name}: {transport_total}"
                )
            group.create_dataset("transport_total", data=transport_total)


if __name__ == "__main__":
    raise SystemExit(main())
