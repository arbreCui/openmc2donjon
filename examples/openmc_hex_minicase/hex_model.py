"""Minimal OpenMC hex-lattice case for openmc2donjon.

This example is intentionally tiny, but it uses the real production entry:

1. build a continuous-energy OpenMC hexagonal lattice;
2. tally MGXS on cell domains, one hex cell domain per DONJON mixture;
3. run OpenMC to produce a statepoint;
4. export that statepoint with ``openmc2donjon-from-openmc``.

The model is a seven-position hex lattice: one central hex cell and one ring of
six neighboring hex cells.  It is a capability example, not a reference
benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

import openmc
import openmc.mgxs as mgxs


CASE_NAME = "openmc_hex_minicase"
DOMAIN_MODE = "hex_cell"
DOMAIN_TYPE = "cell"
HEX_PITCH_CM = 1.40
HEIGHT_CM = 2.0
N_RINGS = 2
HEX_CELL_VOLUME_CM3 = math.sqrt(3.0) / 2.0 * HEX_PITCH_CM**2 * HEIGHT_CM
HEX_OUTER_EDGE_CM = N_RINGS * HEX_PITCH_CM / math.sqrt(3.0)
LEGENDRE_ORDER = 1
ENERGY_BOUNDS_EV = [1.0e-5, 6.25e-1, 2.0e7]
MGXS_TYPES = [
    "total",
    "absorption",
    "fission",
    "nu-fission",
    "chi",
    "consistent nu-scatter matrix",
    "transport",
]

HEX_DOMAIN_IDS = {
    "HEX_C": 201,
    "HEX_E": 202,
    "HEX_NE": 203,
    "HEX_NW": 204,
    "HEX_W": 205,
    "HEX_SW": 206,
    "HEX_SE": 207,
}
DOMAIN_NAME_BY_ID = {cell_id: name for name, cell_id in HEX_DOMAIN_IDS.items()}
RING_ORDER = ("HEX_E", "HEX_NE", "HEX_NW", "HEX_W", "HEX_SW", "HEX_SE")


@dataclass(frozen=True)
class RunSettings:
    batches: int = 10
    inactive: int = 4
    particles: int = 300
    seed: int = 31


def default_case_dir() -> Path:
    return Path(os.environ.get("OPENMC2DONJON_HEX_MINICASE_DIR", Path(__file__).parent)).resolve()


def build_materials() -> openmc.Materials:
    fuel = openmc.Material(material_id=1, name="hex fuel")
    fuel.set_density("g/cm3", 10.2)
    fuel.add_nuclide("U235", 4.7e-2)
    fuel.add_nuclide("U238", 2.15e-2)
    fuel.add_nuclide("O16", 1.37e-1)

    water = openmc.Material(material_id=2, name="hex moderator")
    water.set_density("g/cm3", 0.74)
    water.add_nuclide("H1", 4.95e-2)
    water.add_nuclide("O16", 2.475e-2)

    materials = openmc.Materials([fuel, water])
    cross_sections = openmc.config.get("cross_sections")
    if cross_sections:
        materials.cross_sections = str(cross_sections)
    return materials


def build_geometry(materials: openmc.Materials | None = None) -> openmc.Geometry:
    materials = materials or build_materials()
    by_name = {material.name: material for material in materials}
    fuel = by_name["hex fuel"]
    water = by_name["hex moderator"]

    bottom = openmc.ZPlane(surface_id=301, z0=-HEIGHT_CM / 2.0, boundary_type="reflective")
    top = openmc.ZPlane(surface_id=302, z0=HEIGHT_CM / 2.0, boundary_type="reflective")
    boundary = openmc.model.HexagonalPrism(
        edge_length=HEX_OUTER_EDGE_CM,
        origin=(0.0, 0.0),
        boundary_type="reflective",
        orientation="x",
    )
    container_region = -boundary & +bottom & -top

    lattice = openmc.HexLattice(lattice_id=401, name="seven cell hex lattice")
    lattice.orientation = "x"
    lattice.center = (0.0, 0.0)
    lattice.pitch = (HEX_PITCH_CM,)
    lattice.universes = [
        [_hex_universe(name, fuel) for name in RING_ORDER],
        [_hex_universe("HEX_C", water)],
    ]
    lattice.outer = _outer_universe(water)

    container = openmc.Cell(cell_id=200, name="hex minicase container")
    container.region = container_region
    container.fill = lattice

    root = openmc.Universe(universe_id=500, name="openmc2donjon hex minicase root")
    root.add_cell(container)
    return openmc.Geometry(root)


def _hex_universe(name: str, material: openmc.Material) -> openmc.Universe:
    cell = openmc.Cell(cell_id=HEX_DOMAIN_IDS[name], name=name)
    cell.fill = material
    cell.volume = HEX_CELL_VOLUME_CM3
    return openmc.Universe(universe_id=HEX_DOMAIN_IDS[name] + 1000, name=f"{name} universe", cells=[cell])


def _outer_universe(material: openmc.Material) -> openmc.Universe:
    cell = openmc.Cell(cell_id=299, name="hex outer filler")
    cell.fill = material
    return openmc.Universe(universe_id=1299, name="hex outer filler universe", cells=[cell])


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
            (-HEX_OUTER_EDGE_CM, -HEX_OUTER_EDGE_CM, -HEIGHT_CM / 2.0),
            (HEX_OUTER_EDGE_CM, HEX_OUTER_EDGE_CM, HEIGHT_CM / 2.0),
        ),
        constraints={"fissionable": True},
    )
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    return settings


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    cells = geometry.get_all_cells()
    domains = [cells[HEX_DOMAIN_IDS[name]] for name in ("HEX_C", *RING_ORDER)]
    for cell in domains:
        cell.volume = HEX_CELL_VOLUME_CM3
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
    return tallies


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
            print(f"OpenMC hex minicase keff = {keff}")


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "geometry_kind": "hexagonal",
        "spatial_mapping": "one OpenMC hex cell domain -> one DONJON mixture",
        "hex_pitch_cm": HEX_PITCH_CM,
        "hex_axial_height_cm": HEIGHT_CM,
    }
