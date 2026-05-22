"""Minimal full-core OpenMC case for assembly-wise MGXS export.

This is the smallest production-shaped case in the repository:

1. build one 3D core model, not isolated single-assembly models;
2. tally MGXS on one OpenMC cell domain per assembly position;
3. preserve the spatial map when exporting to the openmc2donjon HDF5 contract.

Each ``ASM_Y##_X##`` cell is one homogenized assembly domain and therefore one
DONJON mixture after conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import numpy as np
import openmc
import openmc.mgxs as mgxs


CASE_NAME = "openmc_full_core_minicase"
DOMAIN_MODE = "full_core_assembly"
DOMAIN_TYPE = "cell"
CORE_SHAPE = (3, 3)
AXIAL_LAYERS = 1
PITCH_CM = 3.0
HEIGHT_CM = 4.0
HALF_WIDTH_CM = PITCH_CM * CORE_SHAPE[0] / 2.0
DOMAIN_VOLUME_CM3 = PITCH_CM * PITCH_CM * HEIGHT_CM
ENERGY_BOUNDS_EV = [1.0e-5, 6.25e-1, 2.0e7]
ENERGY_GROUP_STRUCTURE = "OPENMC2DONJON-FULL-CORE-MINICASE-2G"
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
VOLUME_FLUX_TALLY_NAME = "openmc2donjon_full_core_volume_flux"


@dataclass(frozen=True)
class AssemblyDomain:
    cell_id: int
    name: str
    x_index: int
    y_index: int
    material_key: str
    volume: float = DOMAIN_VOLUME_CM3
    axial_layer: int = 1


@dataclass(frozen=True)
class RunSettings:
    batches: int = 14
    inactive: int = 4
    particles: int = 3000
    seed: int = 91


ASSEMBLIES: tuple[AssemblyDomain, ...] = tuple(
    AssemblyDomain(
        cell_id=1100 + y_index * 10 + x_index,
        name=f"ASM_Y{y_index:02d}_X{x_index:02d}",
        x_index=x_index,
        y_index=y_index,
        material_key=material_key,
    )
    for y_index, row in enumerate(
        (
            ("fuel_low", "fuel_mid", "fuel_low"),
            ("fuel_mid", "fuel_high", "fuel_mid"),
            ("fuel_low", "fuel_mid", "fuel_low"),
        ),
        start=1,
    )
    for x_index, material_key in enumerate(row, start=1)
)
DOMAIN_NAME_BY_ID = {assembly.cell_id: assembly.name for assembly in ASSEMBLIES}
DOMAIN_VOLUME_BY_ID = {assembly.cell_id: assembly.volume for assembly in ASSEMBLIES}
DOMAIN_BY_ID = {assembly.cell_id: assembly for assembly in ASSEMBLIES}
DOMAIN_IDS = tuple(assembly.cell_id for assembly in ASSEMBLIES)


def default_case_dir() -> Path:
    return Path(
        os.environ.get("OPENMC2DONJON_FULL_CORE_MINICASE_DIR", Path(__file__).parent)
    ).resolve()


def build_materials() -> openmc.Materials:
    fuel_low = _fuel_material(1, "full-core fuel low", u235=3.8e-2, u238=2.25e-2)
    fuel_mid = _fuel_material(2, "full-core fuel mid", u235=4.5e-2, u238=2.15e-2)
    fuel_high = _fuel_material(3, "full-core fuel high", u235=5.2e-2, u238=2.05e-2)
    materials = openmc.Materials([fuel_low, fuel_mid, fuel_high])
    cross_sections = openmc.config.get("cross_sections")
    if cross_sections:
        materials.cross_sections = str(cross_sections)
    return materials


def _fuel_material(material_id: int, name: str, *, u235: float, u238: float) -> openmc.Material:
    material = openmc.Material(material_id=material_id, name=name)
    material.set_density("g/cm3", 5.5)
    material.add_nuclide("U235", u235)
    material.add_nuclide("U238", u238)
    material.add_nuclide("O16", 2.0 * (u235 + u238) + 3.0e-2)
    material.add_nuclide("H1", 6.0e-2)
    return material


def build_geometry(materials: openmc.Materials | None = None) -> openmc.Geometry:
    materials = materials or build_materials()
    material_by_key = {
        "fuel_low": materials[0],
        "fuel_mid": materials[1],
        "fuel_high": materials[2],
    }

    x_planes = [
        openmc.XPlane(
            surface_id=1200 + index,
            x0=-HALF_WIDTH_CM + index * PITCH_CM,
            boundary_type="reflective" if index in (0, CORE_SHAPE[0]) else "transmission",
        )
        for index in range(CORE_SHAPE[0] + 1)
    ]
    y_planes = [
        openmc.YPlane(
            surface_id=1210 + index,
            y0=-HALF_WIDTH_CM + index * PITCH_CM,
            boundary_type="reflective" if index in (0, CORE_SHAPE[1]) else "transmission",
        )
        for index in range(CORE_SHAPE[1] + 1)
    ]
    z_min = openmc.ZPlane(surface_id=1220, z0=-HEIGHT_CM / 2.0, boundary_type="reflective")
    z_max = openmc.ZPlane(surface_id=1221, z0=HEIGHT_CM / 2.0, boundary_type="reflective")

    cells = []
    for assembly in ASSEMBLIES:
        x_left = x_planes[assembly.x_index - 1]
        x_right = x_planes[assembly.x_index]
        y_band = CORE_SHAPE[1] - assembly.y_index
        y_low = y_planes[y_band]
        y_high = y_planes[y_band + 1]
        cell = openmc.Cell(cell_id=assembly.cell_id, name=assembly.name)
        cell.fill = material_by_key[assembly.material_key]
        cell.region = +x_left & -x_right & +y_low & -y_high & +z_min & -z_max
        cell.volume = assembly.volume
        cells.append(cell)

    root = openmc.Universe(universe_id=1300, name="openmc2donjon full-core root")
    root.add_cells(cells)
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
        space=openmc.stats.Box(
            (-HALF_WIDTH_CM + 0.01, -HALF_WIDTH_CM + 0.01, -HEIGHT_CM / 2.0 + 0.01),
            (HALF_WIDTH_CM - 0.01, HALF_WIDTH_CM - 0.01, HEIGHT_CM / 2.0 - 0.01),
        ),
        constraints={"fissionable": True},
    )
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    return settings


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    cells = geometry.get_all_cells()
    domains = [cells[cell_id] for cell_id in DOMAIN_IDS]
    for cell in domains:
        cell.volume = DOMAIN_VOLUME_BY_ID[cell.id]
    return domains


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
    return tallies


def build_volume_flux_tally() -> openmc.Tally:
    tally = openmc.Tally(name=VOLUME_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter(list(DOMAIN_IDS)),
        openmc.EnergyFilter(ENERGY_BOUNDS_EV),
    ]
    tally.scores = ["flux"]
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
            print(f"OpenMC full-core minicase keff = {keff}")


def extract_volume_flux(statepoint_path: Path) -> np.ndarray:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=VOLUME_FLUX_TALLY_NAME)
        values = np.asarray(tally.get_values(scores=["flux"], value="mean"), dtype=float)
    energy_filter_order = np.squeeze(values).reshape(
        (len(DOMAIN_IDS), len(ENERGY_BOUNDS_EV) - 1)
    )
    # OpenMC tally bins follow the EnergyFilter bin order; the converter HDF5
    # contract stores group-wise arrays in MGXS/DONJON group order.
    return energy_filter_order[:, ::-1]


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
        dataset.attrs["group_order"] = "mgxs_donjon"
        dataset.attrs["source_group_order"] = "openmc_energy_filter_reversed"


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_group_count": len(ENERGY_BOUNDS_EV) - 1,
        "legendre_order": LEGENDRE_ORDER,
        "core_shape": np.asarray(CORE_SHAPE, dtype=np.int32),
        "axial_layers": AXIAL_LAYERS,
        "assembly_count": len(DOMAIN_IDS),
        "spatial_mapping": "one full-core assembly cell domain -> one DONJON mixture",
    }
