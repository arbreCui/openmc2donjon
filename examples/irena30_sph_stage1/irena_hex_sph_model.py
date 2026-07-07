"""IRENA fissile-assembly CE/MG model for OpenMC-side SPH (Stage 1).

Three-model SPH route, single-assembly stage:

1. **CE fine model** — the TDT-validated 217-pin IRENA fissile assembly
   (``rnr_assembly.py`` from the IRENA workspace: He hole / MOX / He gap /
   AIM1 clad pins, EM10 wrapper, outer Na half-lame; white radial boundary,
   reflective axial).  The whole assembly is wrapped in ONE container cell
   so it is a single MGXS cell domain -> one SPH region -> one DONJON
   mixture.
2. **MG coarse model** — produced automatically by
   ``mgxs.Library.create_mg_mode()``: the container cell filled with the
   homogenized 33-group macro material, same boundary surfaces.
3. SPH(region=1, group=1..33) factors iterate until the MG coarse solve
   reproduces the CE region flux (the ``openmc2donjon`` CE/MG SPH loop).

Local input (not shipped): ``IRENA30_DIR`` (default
``/Users/wen/openmc-workspace/irena``) providing
``irena_colorset_assembly_pin/assembly/rnr_assembly.py``.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import openmc
import openmc.mgxs as mgxs

from openmc2donjon.energy_groups import load_energy_mesh
from openmc2donjon.openmc_volume_flux import (
    reverse_openmc_energy_filter_flux,
    write_openmc_volume_flux_hdf5,
)

CASE_NAME = "irena30_sph_stage1"
DOMAIN_MODE = "hex_assembly"
DOMAIN_TYPE = "cell"
CONTAINER_CELL_ID = 9001
REGION_NAME = "HEX_INT"
ENERGY_MESH_ID = "ecco_33"
ENERGY_GROUP_STRUCTURE = "ECCO-33"
HANDOFF_SCATTER_FORMAT = "legendre"
HANDOFF_LEGENDRE_ORDER = 3
MG_MACRO_SCATTER_FORMAT = "histogram"
MG_MACRO_HISTOGRAM_BINS = 16
MG_MACRO_LEGENDRE_ORDER = HANDOFF_LEGENDRE_ORDER
MGXS_TYPES = [
    "total",
    "absorption",
    "fission",
    "kappa-fission",
    "nu-fission",
    "chi",
    "scatter matrix",
    "nu-scatter matrix",
    "multiplicity matrix",
    "transport",
]
VOLUME_FLUX_TALLY_NAME = "irena30_sph_stage1_volume_flux"
AXIAL_HALF_HEIGHT_CM = 50.0


@dataclass(frozen=True)
class RunSettings:
    batches: int = 60
    inactive: int = 20
    particles: int = 20_000
    seed: int = 31


def default_irena_dir() -> Path:
    return Path(os.environ.get("IRENA30_DIR", "/Users/wen/openmc-workspace/irena")).resolve()


def default_case_dir() -> Path:
    return Path(os.environ.get("OPENMC2DONJON_IRENA_SPH_DIR", Path(__file__).parent)).resolve()


def _load_rnr_module():
    path = default_irena_dir() / "irena_colorset_assembly_pin" / "assembly" / "rnr_assembly.py"
    spec = importlib.util.spec_from_file_location("_openmc2donjon_rnr_assembly", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA assembly model: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def energy_bounds_ev() -> list[float]:
    """ECCO-33 boundaries in OpenMC ascending-energy order."""
    return load_energy_mesh(ENERGY_MESH_ID).boundaries_descending[::-1].tolist()


def _assembly_edge_cm(rnr) -> float:
    """Outer assembly hex edge length, reproducing rnr_assembly.make_geometry."""
    sin60 = math.sin(math.pi / 3.0)
    perp = rnr._hex_apothem_perp_glow(rnr.PIN_RINGS, rnr.SIDE)
    for layer in rnr.LAYER_PERP:
        perp += layer
    return perp / sin60


def container_volume_cm3(rnr) -> float:
    edge = _assembly_edge_cm(rnr)
    hex_area = 3.0 * math.sqrt(3.0) / 2.0 * edge**2
    return hex_area * 2.0 * AXIAL_HALF_HEIGHT_CM


def build_model_parts():
    """Build (materials, geometry, rnr_module) with the whole assembly in one
    container cell that carries all boundary conditions."""
    rnr = _load_rnr_module()
    materials, mats = rnr.make_materials()
    pin_universe = rnr.make_pin_universe(mats)

    pitch = rnr.SIDE * math.sqrt(3.0)
    lat = openmc.HexLattice(name="assembly_lattice")
    lat.center = (0.0, 0.0)
    lat.pitch = (pitch,)
    lat.orientation = "y"
    lat.universes = [
        [pin_universe] * (6 * k) if k > 0 else [pin_universe]
        for k in range(rnr.PIN_RINGS, -1, -1)
    ]
    lat.outer = openmc.Universe(
        cells=[openmc.Cell(fill=mats["coolant"], name="lat_outer_na")]
    )

    sin60 = math.sin(math.pi / 3.0)
    perp = [rnr._hex_apothem_perp_glow(rnr.PIN_RINGS, rnr.SIDE)]
    for layer in rnr.LAYER_PERP:
        perp.append(perp[-1] + layer)
    edge_inner = perp[1] / sin60
    edge_outer = perp[2] / sin60
    edge_asm = perp[3] / sin60

    # Interior surfaces carry NO boundary conditions; the container cell's
    # own surfaces do. Interior cells are left unbounded outward/axially and
    # are clipped by the container region, so no coincident boundary
    # surfaces exist.
    wrap_inner = openmc.model.HexagonalPrism(edge_length=edge_inner, orientation="y")
    wrap_outer = openmc.model.HexagonalPrism(edge_length=edge_outer, orientation="y")

    c_lat = openmc.Cell(fill=lat, region=-wrap_inner, name="lattice")
    c_wrap = openmc.Cell(
        fill=mats["em10"], region=+wrap_inner & -wrap_outer, name="wrapper_EM10"
    )
    c_outer = openmc.Cell(fill=mats["coolant"], region=+wrap_outer, name="outer_Na_lame")
    inner_universe = openmc.Universe(
        name="irena_fissile_assembly", cells=[c_lat, c_wrap, c_outer]
    )

    asm_outer = openmc.model.HexagonalPrism(
        edge_length=edge_asm, orientation="y", boundary_type="white"
    )
    z_lo = openmc.ZPlane(z0=-AXIAL_HALF_HEIGHT_CM, boundary_type="reflective")
    z_hi = openmc.ZPlane(z0=+AXIAL_HALF_HEIGHT_CM, boundary_type="reflective")
    container = openmc.Cell(
        cell_id=CONTAINER_CELL_ID,
        name=REGION_NAME,
        fill=inner_universe,
        region=-asm_outer & +z_lo & -z_hi,
    )
    container.volume = container_volume_cm3(rnr)

    geometry = openmc.Geometry(openmc.Universe(name="root", cells=[container]))
    return materials, geometry, rnr


def build_settings(
    run_settings: RunSettings | None = None,
    *,
    energy_mode: str = "continuous-energy",
) -> openmc.Settings:
    run_settings = run_settings or RunSettings()
    settings = openmc.Settings()
    settings.run_mode = "eigenvalue"
    settings.energy_mode = energy_mode
    settings.batches = run_settings.batches
    settings.inactive = run_settings.inactive
    settings.particles = run_settings.particles
    settings.seed = run_settings.seed
    if energy_mode == "continuous-energy":
        settings.temperature = {"method": "interpolation", "tolerance": 1000}
    half = 7.0
    settings.source = openmc.IndependentSource(
        space=openmc.stats.Box(
            (-half, -half, -AXIAL_HALF_HEIGHT_CM + 1.0),
            (half, half, AXIAL_HALF_HEIGHT_CM - 1.0),
        ),
        constraints={"fissionable": True},
    )
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    return settings


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    cells = geometry.get_all_cells()
    container = cells[CONTAINER_CELL_ID]
    if container.volume is None:
        container.volume = container_volume_cm3(_load_rnr_module())
    return [container]


def build_library(
    geometry: openmc.Geometry | None = None,
    *,
    case_dir: Path | None = None,
    scatter_format: str = HANDOFF_SCATTER_FORMAT,
    legendre_order: int = HANDOFF_LEGENDRE_ORDER,
    histogram_bins: int = MG_MACRO_HISTOGRAM_BINS,
) -> mgxs.Library:
    if geometry is None:
        case_dir = Path(case_dir or default_case_dir()).resolve()
        materials = openmc.Materials.from_xml(str(case_dir / "materials.xml"))
        geometry = openmc.Geometry.from_xml(str(case_dir / "geometry.xml"), materials=materials)

    library = mgxs.Library(geometry)
    library.energy_groups = mgxs.EnergyGroups(energy_bounds_ev())
    library.mgxs_types = MGXS_TYPES
    library.domain_type = DOMAIN_TYPE
    library.domains = selected_domains(geometry)
    library.by_nuclide = False
    library.correction = None
    library.scatter_format = scatter_format
    if scatter_format == "legendre":
        library.legendre_order = legendre_order
    elif scatter_format == "histogram":
        library.histogram_bins = histogram_bins
    else:
        raise ValueError("scatter_format must be 'legendre' or 'histogram'")
    library.build_library()
    return library


def build_volume_flux_tally() -> openmc.Tally:
    tally = openmc.Tally(name=VOLUME_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter([CONTAINER_CELL_ID], filter_id=9_101),
        openmc.EnergyFilter(energy_bounds_ev(), filter_id=9_102),
    ]
    tally.scores = ["flux"]
    return tally


def build_ce_tallies(geometry: openmc.Geometry) -> openmc.Tallies:
    library = build_library(geometry)
    tallies = openmc.Tallies()
    if hasattr(library, "add_to_tallies"):
        library.add_to_tallies(tallies, merge=True)
    else:
        library.add_to_tallies_file(tallies, merge=True)
    mg_macro_library = build_library(
        geometry,
        scatter_format=MG_MACRO_SCATTER_FORMAT,
        histogram_bins=MG_MACRO_HISTOGRAM_BINS,
    )
    if hasattr(mg_macro_library, "add_to_tallies"):
        mg_macro_library.add_to_tallies(tallies, merge=True)
    else:
        mg_macro_library.add_to_tallies_file(tallies, merge=True)
    tallies.append(build_volume_flux_tally())
    return tallies


def build_mg_tallies() -> openmc.Tallies:
    return openmc.Tallies([build_volume_flux_tally()])


def export_ce_xml(case_dir: Path, run_settings: RunSettings | None = None) -> None:
    case_dir = Path(case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    materials, geometry, _rnr = build_model_parts()
    settings = build_settings(run_settings, energy_mode="continuous-energy")
    tallies = build_ce_tallies(geometry)
    materials.export_to_xml(case_dir / "materials.xml")
    geometry.export_to_xml(case_dir / "geometry.xml")
    settings.export_to_xml(case_dir / "settings.xml")
    tallies.export_to_xml(case_dir / "tallies.xml")


def load_statepoint(library: mgxs.Library, statepoint_path: Path) -> None:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        library.load_from_statepoint(statepoint)
        keff = getattr(statepoint, "keff", None)
        if keff is not None:
            print(f"IRENA SPH stage1 keff = {keff}")


def extract_volume_flux_with_std_dev(statepoint_path: Path) -> tuple[np.ndarray, np.ndarray]:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=VOLUME_FLUX_TALLY_NAME)
        values = np.asarray(tally.get_values(scores=["flux"], value="mean"), dtype=float)
        std_dev = np.asarray(tally.get_values(scores=["flux"], value="std_dev"), dtype=float)
    shape = {"mixture_count": 1, "energy_groups": len(energy_bounds_ev()) - 1}
    return (
        reverse_openmc_energy_filter_flux(values, **shape),
        reverse_openmc_energy_filter_flux(std_dev, **shape),
    )


def append_volume_flux_hdf5(
    output_path: Path,
    statepoint_path: Path,
    mixture_names: list[str],
) -> None:
    values, std_dev = extract_volume_flux_with_std_dev(statepoint_path)
    write_openmc_volume_flux_hdf5(
        output_path,
        values,
        mixture_names=mixture_names,
        std_dev=std_dev,
    )


def domain_names(_library: mgxs.Library | None = None) -> dict[int, str]:
    return {CONTAINER_CELL_ID: REGION_NAME}


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "output_region_count": 1,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_group_count": len(energy_bounds_ev()) - 1,
        "legendre_order": HANDOFF_LEGENDRE_ORDER,
        "handoff_scatter_format": HANDOFF_SCATTER_FORMAT,
        "mg_macro_scatter_format": MG_MACRO_SCATTER_FORMAT,
        "mg_macro_histogram_bins": MG_MACRO_HISTOGRAM_BINS,
        "geometry_kind": "hexagonal",
        "boundary_conditions": "radial white, axial reflective (infinite lattice)",
        "spatial_mapping": "one IRENA fissile assembly -> one SPH/DONJON mixture",
        "sph_route": "OpenMC CE fine + OpenMC MG coarse (create_mg_mode), same boundaries",
    }
