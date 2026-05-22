"""Minimal production-style OpenMC case for openmc2donjon.

The case is deliberately tiny, but it uses the same shape as a real user
workflow:

1. build a continuous-energy OpenMC model;
2. add MGXS tallies for spatial domains;
3. run OpenMC to produce a statepoint;
4. export the statepoint with an ``openmc2donjon-from-openmc`` recipe.

The two OpenMC cell domains below represent two homogenized assembly-like
regions.  Each exported MGXS domain becomes one DONJON mixture.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import openmc
import openmc.mgxs as mgxs
import numpy as np


CASE_NAME = "production_minicase"
DOMAIN_MODE = "assembly"
DOMAIN_TYPE = "cell"
FUEL_CELL_ID = 101
MODERATOR_CELL_ID = 102
DOMAIN_NAME_BY_ID = {
    FUEL_CELL_ID: "ASM_FUEL_LEFT",
    MODERATOR_CELL_ID: "ASM_MOD_RIGHT",
}
DOMAIN_VOLUME_BY_ID = {
    FUEL_CELL_ID: 32.0,
    MODERATOR_CELL_ID: 32.0,
}
ENERGY_BOUNDS_EV = [1.0e-5, 6.25e-1, 2.0e7]
ENERGY_GROUP_STRUCTURE = "OPENMC2DONJON-PRODUCTION-MINICASE-2G"
LEGENDRE_ORDER = 1
MGXS_TYPES = [
    "total",
    "absorption",
    "fission",
    "kappa-fission",
    "nu-fission",
    "chi",
    "scatter matrix",
    "transport",
]
SURFACE_FLUX_TALLY_NAME = "openmc2donjon_surface_current_mu"
VOLUME_FLUX_TALLY_NAME = "openmc2donjon_volume_flux"
SURFACE_FLUX_MESH_SHAPE = (1, 2)
SURFACE_FLUX_MU_EDGES = [0.0, 0.25, 0.5, 0.75, 1.0]
SURFACE_FLUX_FACE_AREA = 4.0


@dataclass(frozen=True)
class RunSettings:
    batches: int = 12
    inactive: int = 4
    particles: int = 200
    seed: int = 17


def default_case_dir() -> Path:
    return Path(os.environ.get("OPENMC2DONJON_MINICASE_DIR", Path(__file__).parent)).resolve()


def build_materials() -> openmc.Materials:
    fuel = openmc.Material(material_id=1, name="fuel assembly material")
    fuel.set_density("g/cm3", 10.4)
    fuel.add_nuclide("U235", 4.8e-2)
    fuel.add_nuclide("U238", 2.10e-2)
    fuel.add_nuclide("O16", 1.38e-1)

    moderator = openmc.Material(material_id=2, name="moderator assembly material")
    moderator.set_density("g/cm3", 1.0)
    moderator.add_nuclide("H1", 6.66e-2)
    moderator.add_nuclide("O16", 3.33e-2)

    materials = openmc.Materials([fuel, moderator])
    cross_sections = openmc.config.get("cross_sections")
    if cross_sections:
        materials.cross_sections = str(cross_sections)
    return materials


def build_geometry(materials: openmc.Materials | None = None) -> openmc.Geometry:
    materials = materials or build_materials()
    by_name = {material.name: material for material in materials}
    fuel = by_name["fuel assembly material"]
    moderator = by_name["moderator assembly material"]

    x_mid = openmc.XPlane(surface_id=10, x0=0.0)
    x_min = openmc.XPlane(surface_id=11, x0=-2.0, boundary_type="reflective")
    x_max = openmc.XPlane(surface_id=12, x0=2.0, boundary_type="reflective")
    y_min = openmc.YPlane(surface_id=13, y0=-2.0, boundary_type="reflective")
    y_max = openmc.YPlane(surface_id=14, y0=2.0, boundary_type="reflective")
    z_min = openmc.ZPlane(surface_id=15, z0=-2.0, boundary_type="reflective")
    z_max = openmc.ZPlane(surface_id=16, z0=2.0, boundary_type="reflective")

    fuel_cell = openmc.Cell(cell_id=FUEL_CELL_ID, name=DOMAIN_NAME_BY_ID[FUEL_CELL_ID])
    fuel_cell.fill = fuel
    fuel_cell.region = +x_min & -x_mid & +y_min & -y_max & +z_min & -z_max
    fuel_cell.volume = DOMAIN_VOLUME_BY_ID[FUEL_CELL_ID]

    moderator_cell = openmc.Cell(
        cell_id=MODERATOR_CELL_ID,
        name=DOMAIN_NAME_BY_ID[MODERATOR_CELL_ID],
    )
    moderator_cell.fill = moderator
    moderator_cell.region = +x_mid & -x_max & +y_min & -y_max & +z_min & -z_max
    moderator_cell.volume = DOMAIN_VOLUME_BY_ID[MODERATOR_CELL_ID]

    root = openmc.Universe(universe_id=1, name="production minicase root")
    root.add_cells([fuel_cell, moderator_cell])
    return openmc.Geometry(root)


def build_settings(run_settings: RunSettings | None = None) -> openmc.Settings:
    run_settings = run_settings or RunSettings()
    settings = openmc.Settings()
    settings.run_mode = "eigenvalue"
    settings.batches = run_settings.batches
    settings.inactive = run_settings.inactive
    settings.particles = run_settings.particles
    settings.seed = run_settings.seed
    settings.source = openmc.IndependentSource(
        space=openmc.stats.Box((-1.9, -1.9, -1.9), (1.9, 1.9, 1.9)),
        constraints={"fissionable": True},
    )
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    return settings


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    cells = geometry.get_all_cells()
    selected = [cells[FUEL_CELL_ID], cells[MODERATOR_CELL_ID]]
    for cell in selected:
        cell.volume = DOMAIN_VOLUME_BY_ID[cell.id]
    return selected


def build_library(
    geometry: openmc.Geometry | None = None,
    *,
    case_dir: Path | None = None,
) -> mgxs.Library:
    if geometry is None:
        case_dir = Path(case_dir or default_case_dir()).resolve()
        materials = openmc.Materials.from_xml(str(case_dir / "materials.xml"))
        geometry = openmc.Geometry.from_xml(str(case_dir / "geometry.xml"), materials=materials)

    library = mgxs.Library(geometry)
    library.energy_groups = mgxs.EnergyGroups(ENERGY_BOUNDS_EV)
    library.mgxs_types = MGXS_TYPES
    library.domain_type = DOMAIN_TYPE
    library.domains = selected_domains(geometry)
    library.by_nuclide = False
    library.legendre_order = LEGENDRE_ORDER
    library.build_library()
    return library


def build_tallies(geometry: openmc.Geometry) -> openmc.Tallies:
    library = build_library(geometry)
    tallies = openmc.Tallies()
    if hasattr(library, "add_to_tallies"):
        library.add_to_tallies(tallies, merge=True)
    else:
        library.add_to_tallies_file(tallies, merge=True)
    tallies.append(build_volume_flux_tally())
    tallies.append(build_surface_flux_tally())
    return tallies


def build_volume_flux_tally() -> openmc.Tally:
    tally = openmc.Tally(name=VOLUME_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter([FUEL_CELL_ID, MODERATOR_CELL_ID]),
        openmc.EnergyFilter(ENERGY_BOUNDS_EV),
    ]
    tally.scores = ["flux"]
    return tally


def build_surface_flux_tally() -> openmc.Tally:
    mesh = openmc.RegularMesh(mesh_id=3001, name="openmc2donjon minicase face mesh")
    mesh.dimension = (SURFACE_FLUX_MESH_SHAPE[1], SURFACE_FLUX_MESH_SHAPE[0])
    mesh.lower_left = (-2.0, -2.0)
    mesh.upper_right = (2.0, 2.0)
    tally = openmc.Tally(name=SURFACE_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.MeshSurfaceFilter(mesh),
        openmc.MuSurfaceFilter(SURFACE_FLUX_MU_EDGES),
        openmc.EnergyFilter(ENERGY_BOUNDS_EV),
    ]
    tally.scores = ["current"]
    return tally


def export_openmc_xml(
    case_dir: Path,
    *,
    run_settings: RunSettings | None = None,
) -> None:
    case_dir = Path(case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    materials = build_materials()
    geometry = build_geometry(materials)
    settings = build_settings(run_settings)
    tallies = build_tallies(geometry)

    materials.export_to_xml(case_dir / "materials.xml")
    geometry.export_to_xml(case_dir / "geometry.xml")
    settings.export_to_xml(case_dir / "settings.xml")
    tallies.export_to_xml(case_dir / "tallies.xml")


def domain_names(library: mgxs.Library | None = None) -> dict[int, str]:
    return dict(DOMAIN_NAME_BY_ID)


def load_statepoint(library: mgxs.Library, statepoint_path: Path) -> None:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        library.load_from_statepoint(statepoint)
        keff = getattr(statepoint, "keff", None)
        if keff is not None:
            print(f"OpenMC minicase keff = {keff}")


def extract_volume_flux(statepoint_path: Path) -> np.ndarray:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=VOLUME_FLUX_TALLY_NAME)
        values = np.asarray(tally.get_values(scores=["flux"], value="mean"), dtype=float)
    return np.squeeze(values).reshape((len(DOMAIN_NAME_BY_ID), len(ENERGY_BOUNDS_EV) - 1))


def append_volume_flux_hdf5(
    output_path: Path,
    statepoint_path: Path,
    mixture_names: list[str],
) -> None:
    import h5py

    values = extract_volume_flux(statepoint_path)
    with h5py.File(output_path, "a") as h5:
        if "openmc_volume_flux" in h5:
            del h5["openmc_volume_flux"]
        dataset = h5.create_dataset("openmc_volume_flux", data=values)
        dataset.attrs["mixture_names"] = np.asarray(mixture_names, dtype="S")


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_group_count": len(ENERGY_BOUNDS_EV) - 1,
        "legendre_order": LEGENDRE_ORDER,
        "spatial_mapping": "one OpenMC cell domain -> one DONJON mixture",
    }
