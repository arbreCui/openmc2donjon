"""Strict IRENA-30 full-core CE reference, pooled on 21 physical D3 orbits.

This is the fine-model input for the full-core native-SPH route.  All 91
physical assembly positions are present as heterogeneous OpenMC assembly
universes.  The 21 MGXS domains are *not* averages made after transport.
Instead, every global D3 orbit owns one reusable wrapper universe containing
one reusable cell-domain.  Each physical position in that orbit fills its
top-level hex with that same wrapper universe.  OpenMC therefore accumulates
the CellFilter and MGXS scores over all instances of the orbit cell while it
tracks the fine model.

The D3 orbit declaration is benchmark-specific data in ``global_orbits.py``.
The fine assembly universes and CE material recipes are loaded from the local
IRENA ``ce_compare`` workspace.  They are an input dependency and are not
silently replaced by homogeneous material cells.

Physics contract
----------------

* 91 explicit heterogeneous assembly positions;
* radial vacuum on the 66 physical outer faces, axial reflection;
* 21 transport-pooled cell domains with exact multiplicity-weighted volume;
* ANL-24C-20MeV, Legendre P0+P1, consistent nu-scatter matrix;
* orbit-integrated volume flux (with standard deviation), energy-coverage
  scores, 91 uncollapsed position-power bins, and an unfiltered global neutron
  balance including OpenMC leakage;
* no zero-flux fill, blackening, cross-section floor, clipping, ADF, or
  eigenvalue/global-factor fit.

No OpenMC solve is performed by this module.  ``export_ce_xml`` only writes
the XML inputs.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import numpy as np
import openmc
import openmc.mgxs as mgxs

from openmc2donjon.energy_groups import load_energy_mesh
from openmc2donjon.openmc_volume_flux import (
    reverse_openmc_energy_filter_flux,
    write_openmc_volume_flux_hdf5,
)


CASE_NAME = "irena30_strict_d3_orbit_ce_reference"
DOMAIN_MODE = "global_d3_orbit_cell"
DOMAIN_TYPE = "cell"
N_HEXES = 91
N_ORBITS = 21
N_BOUNDARY_FACES = 66
PITCH_CM = 17.5
SIDE_CM = PITCH_CM / math.sqrt(3.0)
AXIAL_HEIGHT_CM = 10.0

ENERGY_MESH_ID = "anl_24c_20mev"
ENERGY_MESH = load_energy_mesh(ENERGY_MESH_ID)
ENERGY_GROUP_STRUCTURE = ENERGY_MESH.name
HANDOFF_SCATTER_FORMAT = "legendre"
HANDOFF_LEGENDRE_ORDER = 1
MGXS_TYPES = [
    "total",
    "absorption",
    "fission",
    "kappa-fission",
    "nu-fission",
    "chi",
    "scatter matrix",
    "nu-scatter matrix",
    "consistent scatter matrix",
    "consistent nu-scatter matrix",
    "multiplicity matrix",
    "transport",
]

VOLUME_FLUX_TALLY_NAME = "irena30_fullcore_d3_orbit_volume_flux"
POSITION_POWER_TALLY_NAME = "irena30_fullcore_91_position_power"
POSITION_POWER_SCORES = ("kappa-fission", "fission")
ENERGY_COVERAGE_TALLY_NAME = "irena30_fullcore_d3_orbit_energy_coverage"
ENERGY_COVERAGE_SCORES = (
    "absorption",
    "fission",
    "kappa-fission",
    "nu-fission",
)
GLOBAL_BALANCE_TALLY_NAME = "irena30_fullcore_d3_global_balance"
GLOBAL_BALANCE_SCORES = (
    "absorption",
    "nu-fission",
    "(n,2n)",
    "(n,3n)",
    "(n,4n)",
)
FULL_ENERGY_MIN_EV = 1.0e-5
FULL_ENERGY_MAX_EV = 2.0e7

_ORBIT_DOMAIN_CELL_RE = re.compile(
    r"^irena_d3_orbit_(\d{2})_(INT|EXT|CSD|DSDF|PNL)_domain$"
)
_POSITION_CELL_RE = re.compile(
    r"^irena_position_r(\d+)p(\d{2})_(INT|EXT|CSD|DSDF|PNL)_o(\d{2})$"
)
_WRAPPER_UNIVERSE_RE = re.compile(
    r"^irena_d3_orbit_(\d{2})_(INT|EXT|CSD|DSDF|PNL)_wrapper$"
)


def _load_local_module(name: str, filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    module_name = f"_openmc2donjon_{name}_{abs(hash(path.resolve()))}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ORBITS = _load_local_module("irena30_global_orbits", "global_orbits.py")
if len(ORBITS.ORBITS) != N_ORBITS or len(ORBITS.POSITION_ORDER) != N_HEXES:
    raise RuntimeError("strict IRENA reference requires exactly 21 D3 orbits / 91 positions")


@dataclass(frozen=True)
class RunSettings:
    batches: int = 160
    inactive: int = 40
    particles: int = 100_000
    seed: int = 71


@dataclass(frozen=True)
class CorePosition:
    ring: int
    position: int
    x_cm: float
    y_cm: float
    material: str
    orbit_number: int


def default_ce_compare_dir() -> Path:
    value = os.environ.get("IRENA_CE_COMPARE_DIR")
    if not value:
        raise RuntimeError(
            "IRENA_CE_COMPARE_DIR must point to the external IRENA "
            "ce_compare input directory"
        )
    return Path(value).expanduser().resolve()


def default_case_dir() -> Path:
    return Path(
        os.environ.get("OPENMC2DONJON_IRENA_ORBIT_CE_DIR", Path(__file__).parent)
    ).expanduser().resolve()


def _load_ce_compare_modules() -> tuple[ModuleType, ModuleType]:
    """Load the authoritative fine-assembly constructors without copying them."""

    root = default_ce_compare_dir()
    if not (root / "openmc_colorset.py").is_file():
        raise FileNotFoundError(f"IRENA ce_compare directory not found: {root}")
    inserted = str(root) not in sys.path
    if inserted:
        sys.path.insert(0, str(root))
    try:
        colorset_common = _import_exact_ce_compare_module(root, "colorset_common")
        # ``openmc_colorset`` imports ``colorset_common`` by its short name.
        # Import and validate the latter first so a polluted long-lived Python
        # process cannot silently bind the assembly builder to unrelated data.
        openmc_colorset = _import_exact_ce_compare_module(root, "openmc_colorset")
    finally:
        if inserted:
            sys.path.remove(str(root))
    return colorset_common, openmc_colorset


def _import_exact_ce_compare_module(root: Path, name: str) -> ModuleType:
    expected = (root / f"{name}.py").resolve()
    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    actual = None if source is None else Path(source).resolve()
    if actual != expected:
        raise ImportError(
            f"refusing cached {name!r} from {actual}; strict IRENA input requires "
            f"the declared source {expected}"
        )
    return module


def node_volume_cm3() -> float:
    return math.sqrt(3.0) / 2.0 * PITCH_CM**2 * AXIAL_HEIGHT_CM


def orbit_volume_cm3(orbit: Any) -> float:
    return float(orbit.multiplicity) * node_volume_cm3()


def _ring_centers_y_orientation(ring: int) -> tuple[tuple[float, float], ...]:
    """Return centers in the same per-ring order as DRAGON HEXZ / IRENA."""

    if ring == 0:
        return ((0.0, 0.0),)
    centers: list[tuple[float, float]] = []
    for side in range(6):
        start_angle = math.radians(90.0 + 60.0 * side)
        x0 = ring * PITCH_CM * math.cos(start_angle)
        y0 = ring * PITCH_CM * math.sin(start_angle)
        step_angle = math.radians(90.0 + 60.0 * (side + 2))
        dx = PITCH_CM * math.cos(step_angle)
        dy = PITCH_CM * math.sin(step_angle)
        for offset in range(ring):
            centers.append((x0 + offset * dx, y0 + offset * dy))
    return tuple(centers)


def core_layout() -> tuple[CorePosition, ...]:
    entries: list[CorePosition] = []
    centers_by_ring = {
        ring: _ring_centers_y_orientation(ring)
        for ring in range(len(ORBITS.RING_POSITION_COUNTS))
    }
    for ring, position in ORBITS.POSITION_ORDER:
        orbit = ORBITS.orbit_for_position(ring, position)
        x_cm, y_cm = centers_by_ring[ring][position]
        entries.append(
            CorePosition(
                ring=ring,
                position=position,
                x_cm=x_cm,
                y_cm=y_cm,
                material=orbit.material,
                orbit_number=orbit.number,
            )
        )
    if len(entries) != N_HEXES:
        raise RuntimeError(f"expected {N_HEXES} core positions, found {len(entries)}")
    return tuple(entries)


def _hex_vertices(center: tuple[float, float]) -> tuple[tuple[float, float], ...]:
    cx, cy = center
    apothem = SIDE_CM * math.sqrt(3.0) / 2.0
    return (
        (cx + SIDE_CM, cy),
        (cx + 0.5 * SIDE_CM, cy + apothem),
        (cx - 0.5 * SIDE_CM, cy + apothem),
        (cx - SIDE_CM, cy),
        (cx - 0.5 * SIDE_CM, cy - apothem),
        (cx + 0.5 * SIDE_CM, cy - apothem),
    )


def _edge_key(
    first: tuple[float, float], second: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    rounded = (
        (round(first[0], 7), round(first[1], 7)),
        (round(second[0], 7), round(second[1], 7)),
    )
    return tuple(sorted(rounded))  # type: ignore[return-value]


def orbit_domain_cell_name(orbit: Any) -> str:
    return f"irena_d3_orbit_{orbit.number:02d}_{orbit.material}_domain"


def orbit_wrapper_universe_name(orbit: Any) -> str:
    return f"irena_d3_orbit_{orbit.number:02d}_{orbit.material}_wrapper"


def exported_orbit_name(orbit: Any) -> str:
    return f"{orbit.id}_{orbit.material}"


def position_cell_name(position: CorePosition) -> str:
    return (
        f"irena_position_r{position.ring}p{position.position:02d}_"
        f"{position.material}_o{position.orbit_number:02d}"
    )


def build_orbit_wrappers(
    assembly_universes: dict[str, openmc.Universe],
) -> tuple[dict[int, openmc.Universe], dict[int, openmc.Cell]]:
    """Create exactly one reusable wrapper universe/cell per global orbit."""

    wrappers: dict[int, openmc.Universe] = {}
    domain_cells: dict[int, openmc.Cell] = {}
    for orbit in ORBITS.ORBITS:
        if orbit.material not in assembly_universes:
            raise KeyError(f"fine assembly universe missing for {orbit.material}")
        domain_cell = openmc.Cell(
            name=orbit_domain_cell_name(orbit),
            fill=assembly_universes[orbit.material],
        )
        # This is the physical volume represented by every occurrence of the
        # same cell id.  OpenMC's cell-domain MGXS normalization therefore
        # uses the full orbit volume, not a one-node or post-averaged volume.
        domain_cell.volume = orbit_volume_cm3(orbit)
        wrapper = openmc.Universe(
            name=orbit_wrapper_universe_name(orbit), cells=[domain_cell]
        )
        wrappers[orbit.number] = wrapper
        domain_cells[orbit.number] = domain_cell
    return wrappers, domain_cells


def build_core_geometry(mats: dict[str, openmc.Material]) -> openmc.Geometry:
    """Build 91 explicit fine hexes filled by 21 shared orbit wrappers."""

    _colorset_common, openmc_colorset = _load_ce_compare_modules()
    assembly_universes = openmc_colorset.make_assembly_universes(mats)
    wrappers, _domain_cells = build_orbit_wrappers(assembly_universes)

    layout = core_layout()
    vertices_by_position = [
        _hex_vertices((position.x_cm, position.y_cm)) for position in layout
    ]
    edge_counts: dict[tuple, int] = {}
    for vertices in vertices_by_position:
        for first, second in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            key = _edge_key(first, second)
            edge_counts[key] = edge_counts.get(key, 0) + 1
    n_boundary = sum(count == 1 for count in edge_counts.values())
    if n_boundary != N_BOUNDARY_FACES:
        raise RuntimeError(
            f"expected {N_BOUNDARY_FACES} radial boundary faces, found {n_boundary}"
        )

    surfaces: dict[tuple, openmc.Plane] = {}
    for vertices in vertices_by_position:
        for first, second in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            key = _edge_key(first, second)
            if key in surfaces:
                continue
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            a, b = dy, -dx
            d = a * first[0] + b * first[1]
            boundary = "vacuum" if edge_counts[key] == 1 else "transmission"
            surfaces[key] = openmc.Plane(
                a=a,
                b=b,
                d=d,
                boundary_type=boundary,
                name=f"irena_core_face_{len(surfaces) + 1:03d}",
            )

    z_lo = openmc.ZPlane(
        z0=0.0, boundary_type="reflective", name="irena_core_axial_lower"
    )
    z_hi = openmc.ZPlane(
        z0=AXIAL_HEIGHT_CM,
        boundary_type="reflective",
        name="irena_core_axial_upper",
    )
    position_cells: list[openmc.Cell] = []
    for position, vertices in zip(layout, vertices_by_position, strict=True):
        region = +z_lo & -z_hi
        for first, second in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            surface = surfaces[_edge_key(first, second)]
            signed_distance = (
                surface.a * position.x_cm
                + surface.b * position.y_cm
                - surface.d
            )
            region &= -surface if signed_distance < 0.0 else +surface
        cell = openmc.Cell(
            name=position_cell_name(position),
            fill=wrappers[position.orbit_number],
            region=region,
        )
        cell.translation = (position.x_cm, position.y_cm, 0.0)
        position_cells.append(cell)

    geometry = openmc.Geometry(position_cells)
    validate_orbit_geometry(geometry)
    return geometry


def build_model_parts() -> tuple[openmc.Materials, openmc.Geometry]:
    _colorset_common, openmc_colorset = _load_ce_compare_modules()
    materials, mats = openmc_colorset.make_materials()
    return materials, build_core_geometry(mats)


def core_position_cells(
    geometry: openmc.Geometry,
) -> list[tuple[int, int, str, int, openmc.Cell]]:
    entries: list[tuple[int, int, str, int, openmc.Cell]] = []
    for cell in geometry.get_all_cells().values():
        match = _POSITION_CELL_RE.match(cell.name or "")
        if match:
            entries.append(
                (
                    int(match.group(1)),
                    int(match.group(2)),
                    match.group(3),
                    int(match.group(4)),
                    cell,
                )
            )
    entries.sort(key=lambda item: (item[0], item[1]))
    if len(entries) != N_HEXES:
        raise RuntimeError(f"expected {N_HEXES} position cells, found {len(entries)}")
    return entries


def orbit_domain_cells(geometry: openmc.Geometry) -> list[tuple[Any, openmc.Cell]]:
    by_number: dict[int, openmc.Cell] = {}
    for cell in geometry.get_all_cells().values():
        match = _ORBIT_DOMAIN_CELL_RE.match(cell.name or "")
        if match:
            number = int(match.group(1))
            orbit = ORBITS.BY_NUMBER.get(number)
            if orbit is None or orbit.material != match.group(2):
                raise RuntimeError(f"invalid orbit domain cell name: {cell.name!r}")
            by_number[number] = cell
    if set(by_number) != set(range(1, N_ORBITS + 1)):
        raise RuntimeError(
            f"expected orbit cell ids 1..{N_ORBITS}, found {sorted(by_number)}"
        )
    return [
        (ORBITS.BY_NUMBER[number], by_number[number])
        for number in sorted(by_number)
    ]


def validate_orbit_geometry(geometry: openmc.Geometry) -> None:
    """Reject any geometry that no longer implements transport-time pooling."""

    position_entries = core_position_cells(geometry)
    domain_entries = orbit_domain_cells(geometry)
    counts = {orbit.number: 0 for orbit, _cell in domain_entries}
    for _ring, _position, material, orbit_number, cell in position_entries:
        orbit = ORBITS.BY_NUMBER[orbit_number]
        if material != orbit.material:
            raise RuntimeError("position material differs from its declared D3 orbit")
        # Universe names are not serialized by OpenMC geometry.xml.  Identify
        # the wrapper by its one direct orbit-domain cell so validation works
        # both on an in-memory model and on a recipe reconstructed from XML.
        direct_cells = list(getattr(cell.fill, "cells", {}).values())
        direct_domain_numbers = []
        for direct_cell in direct_cells:
            match = _ORBIT_DOMAIN_CELL_RE.match(direct_cell.name or "")
            if match:
                direct_domain_numbers.append(int(match.group(1)))
        if direct_domain_numbers != [orbit_number]:
            raise RuntimeError(
                f"position does not reuse orbit {orbit_number} wrapper: "
                f"direct domains={direct_domain_numbers}"
            )
        counts[orbit_number] += 1
    expected = {orbit.number: orbit.multiplicity for orbit in ORBITS.ORBITS}
    if counts != expected:
        raise RuntimeError(f"orbit wrapper instance counts differ: {counts} != {expected}")
    for orbit, cell in domain_entries:
        expected_volume = orbit_volume_cm3(orbit)
        if cell.volume is None or not math.isclose(
            float(cell.volume), expected_volume, rel_tol=1.0e-13
        ):
            raise RuntimeError(
                f"orbit {orbit.id} volume {cell.volume!r} != {expected_volume}"
            )


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
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    # Use one local bounding box per physical fuel assembly.  The boxes are a
    # little larger than each hex, but OpenMC's fissionable constraint rejects
    # every proposal in sodium, structure, neighbouring non-fuel hexes, or the
    # exterior void.  Thus no source particle can be born outside a real fuel
    # material, and the non-convex full-core envelope is never approximated as
    # a source region.
    apothem = SIDE_CM * math.sqrt(3.0) / 2.0
    fuel_sources = []
    for position in core_layout():
        if position.material not in {"INT", "EXT"}:
            continue
        fuel_sources.append(
            openmc.IndependentSource(
                space=openmc.stats.Box(
                    (
                        position.x_cm - SIDE_CM,
                        position.y_cm - apothem,
                        0.05,
                    ),
                    (
                        position.x_cm + SIDE_CM,
                        position.y_cm + apothem,
                        AXIAL_HEIGHT_CM - 0.05,
                    ),
                ),
                angle=openmc.stats.Isotropic(),
                energy=openmc.stats.Watt(),
                constraints={"fissionable": True},
                strength=1.0,
            )
        )
    if len(fuel_sources) != 52:
        raise RuntimeError(
            f"expected 52 physical INT/EXT source boxes, found {len(fuel_sources)}"
        )
    settings.source = fuel_sources
    if energy_mode == "continuous-energy":
        settings.temperature = {"method": "interpolation", "tolerance": 1000}
    else:
        settings.temperature = {}
    return settings


def energy_bounds_ev() -> list[float]:
    return ENERGY_MESH.boundaries_descending[::-1].tolist()


def energy_coverage_segments() -> tuple[list[str], list[float]]:
    """Use the same retained/tail coverage contract as validated Stage 2."""

    lower, upper = energy_bounds_ev()[0], energy_bounds_ev()[-1]
    if not (FULL_ENERGY_MIN_EV <= lower < upper <= FULL_ENERGY_MAX_EV):
        raise ValueError(
            f"energy mesh {ENERGY_MESH_ID!r} lies outside the CE coverage domain"
        )
    labels: list[str] = []
    bounds = [FULL_ENERGY_MIN_EV]
    if lower > FULL_ENERGY_MIN_EV:
        labels.append("low_tail")
        bounds.append(lower)
    labels.append("retained")
    bounds.append(upper)
    if upper < FULL_ENERGY_MAX_EV:
        labels.append("high_tail")
        bounds.append(FULL_ENERGY_MAX_EV)
    return labels, bounds


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    validate_orbit_geometry(geometry)
    return [cell for _orbit, cell in orbit_domain_cells(geometry)]


def build_library(
    geometry: openmc.Geometry | None = None,
    *,
    case_dir: Path | None = None,
) -> mgxs.Library:
    if geometry is None:
        case_dir = Path(case_dir or default_case_dir()).resolve()
        materials = openmc.Materials.from_xml(str(case_dir / "materials.xml"))
        geometry = openmc.Geometry.from_xml(
            str(case_dir / "geometry.xml"), materials=materials
        )

    library = mgxs.Library(geometry)
    library.energy_groups = mgxs.EnergyGroups(energy_bounds_ev())
    library.energy_group_structure = ENERGY_GROUP_STRUCTURE
    library.mgxs_types = list(MGXS_TYPES)
    library.domain_type = DOMAIN_TYPE
    library.domains = selected_domains(geometry)
    library.by_nuclide = False
    library.correction = None
    library.scatter_format = HANDOFF_SCATTER_FORMAT
    library.legendre_order = HANDOFF_LEGENDRE_ORDER
    library.build_library()
    return library


def build_volume_flux_tally(geometry: openmc.Geometry) -> openmc.Tally:
    cell_ids = [int(cell.id) for _orbit, cell in orbit_domain_cells(geometry)]
    tally = openmc.Tally(name=VOLUME_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter(cell_ids, filter_id=9_401),
        openmc.EnergyFilter(energy_bounds_ev(), filter_id=9_402),
    ]
    tally.scores = ["flux"]
    return tally


def build_energy_coverage_tally(geometry: openmc.Geometry) -> openmc.Tally:
    cell_ids = [int(cell.id) for _orbit, cell in orbit_domain_cells(geometry)]
    _labels, bounds = energy_coverage_segments()
    tally = openmc.Tally(name=ENERGY_COVERAGE_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter(cell_ids, filter_id=9_403),
        openmc.EnergyFilter(bounds, filter_id=9_404),
    ]
    tally.scores = list(ENERGY_COVERAGE_SCORES)
    return tally


def build_position_power_tally(geometry: openmc.Geometry) -> openmc.Tally:
    """Score every physical position independently in fixed HEXZ order.

    MGXS/flux pooling is intentionally performed on 21 D3 orbits, but final
    physical acceptance must still compare all 91 position powers.  This
    separate top-level CellFilter retains those 91 bins and is never collapsed
    to orbit means.
    """

    cell_ids = [int(cell.id) for *_metadata, cell in core_position_cells(geometry)]
    if len(cell_ids) != N_HEXES or len(set(cell_ids)) != N_HEXES:
        raise RuntimeError("position-power CellFilter requires 91 unique cells")
    tally = openmc.Tally(name=POSITION_POWER_TALLY_NAME)
    tally.filters = [openmc.CellFilter(cell_ids, filter_id=9_405)]
    tally.scores = list(POSITION_POWER_SCORES)
    tally.estimator = "tracklength"
    return tally


def build_global_balance_tally() -> openmc.Tally:
    tally = openmc.Tally(name=GLOBAL_BALANCE_TALLY_NAME)
    tally.estimator = "tracklength"
    tally.scores = list(GLOBAL_BALANCE_SCORES)
    return tally


def build_reference_tallies(geometry: openmc.Geometry) -> list[openmc.Tally]:
    return [
        build_volume_flux_tally(geometry),
        build_energy_coverage_tally(geometry),
        build_position_power_tally(geometry),
        build_global_balance_tally(),
    ]


def _add_library_tallies(library: mgxs.Library, tallies: openmc.Tallies) -> None:
    if hasattr(library, "add_to_tallies"):
        library.add_to_tallies(tallies, merge=True)
    else:  # OpenMC <= 0.14 compatibility
        library.add_to_tallies_file(tallies, merge=True)


def build_ce_tallies(geometry: openmc.Geometry) -> openmc.Tallies:
    library = build_library(geometry)
    tallies = openmc.Tallies()
    _add_library_tallies(library, tallies)
    for tally in build_reference_tallies(geometry):
        tallies.append(tally)
    return tallies


def export_ce_xml(case_dir: Path, run_settings: RunSettings | None = None) -> None:
    """Generate the strict CE input XML without running OpenMC."""

    case_dir = Path(case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    materials, geometry = build_model_parts()
    settings = build_settings(run_settings, energy_mode="continuous-energy")
    tallies = build_ce_tallies(geometry)
    materials.export_to_xml(case_dir / "materials.xml")
    geometry.export_to_xml(case_dir / "geometry.xml")
    settings.export_to_xml(case_dir / "settings.xml")
    tallies.export_to_xml(case_dir / "tallies.xml")


_REFERENCE_KEFF: float | None = None
_REFERENCE_KEFF_STD_DEV: float | None = None


def load_statepoint(library: mgxs.Library, statepoint_path: Path) -> None:
    global _REFERENCE_KEFF, _REFERENCE_KEFF_STD_DEV
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        library.load_from_statepoint(statepoint)
        keff = getattr(statepoint, "keff", None)
        if keff is not None:
            _REFERENCE_KEFF = float(keff.nominal_value)
            _REFERENCE_KEFF_STD_DEV = float(keff.std_dev)
            print(f"IRENA strict full-core D3-orbit CE keff = {keff}")


def domain_names(library: mgxs.Library) -> dict[int, str]:
    names: dict[int, str] = {}
    for orbit, domain in zip(ORBITS.ORBITS, library.domains, strict=True):
        match = _ORBIT_DOMAIN_CELL_RE.match(domain.name or "")
        if not match or int(match.group(1)) != orbit.number:
            raise RuntimeError(f"unexpected orbit domain order/name: {domain.name!r}")
        names[int(domain.id)] = exported_orbit_name(orbit)
    return names


def orbit_for_domain(domain: openmc.Cell) -> Any:
    match = _ORBIT_DOMAIN_CELL_RE.match(domain.name or "")
    if not match:
        raise RuntimeError(f"unexpected orbit domain cell name: {domain.name!r}")
    orbit = ORBITS.BY_NUMBER[int(match.group(1))]
    if orbit.material != match.group(2):
        raise RuntimeError(f"orbit material mismatch in {domain.name!r}")
    return orbit


def extract_volume_flux_with_std_dev(
    statepoint_path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=VOLUME_FLUX_TALLY_NAME)
        mean = np.asarray(
            tally.get_values(scores=["flux"], value="mean"), dtype=float
        )
        std_dev = np.asarray(
            tally.get_values(scores=["flux"], value="std_dev"), dtype=float
        )
    shape = {"mixture_count": N_ORBITS, "energy_groups": len(energy_bounds_ev()) - 1}
    return (
        reverse_openmc_energy_filter_flux(mean, **shape),
        reverse_openmc_energy_filter_flux(std_dev, **shape),
    )


def extract_energy_coverage(
    statepoint_path: Path,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...], tuple[float, ...]]:
    labels, bounds = energy_coverage_segments()
    shape = (N_ORBITS, len(labels), len(ENERGY_COVERAGE_SCORES))
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=ENERGY_COVERAGE_TALLY_NAME)
        mean = np.asarray(
            tally.get_values(scores=list(ENERGY_COVERAGE_SCORES), value="mean"),
            dtype=float,
        ).reshape(shape)
        std_dev = np.asarray(
            tally.get_values(
                scores=list(ENERGY_COVERAGE_SCORES), value="std_dev"
            ),
            dtype=float,
        ).reshape(shape)
    return mean, std_dev, tuple(labels), tuple(bounds)


def extract_position_power(
    statepoint_path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    shape = (N_HEXES, len(POSITION_POWER_SCORES))
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=POSITION_POWER_TALLY_NAME)
        mean = np.asarray(
            tally.get_values(scores=list(POSITION_POWER_SCORES), value="mean"),
            dtype=float,
        ).reshape(shape)
        std_dev = np.asarray(
            tally.get_values(
                scores=list(POSITION_POWER_SCORES), value="std_dev"
            ),
            dtype=float,
        ).reshape(shape)
    return mean, std_dev


def extract_reference_balance(statepoint_path: Path) -> dict[str, float | str]:
    """Apply the validated Stage-2 collision/finite neutron-balance formula."""

    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=GLOBAL_BALANCE_TALLY_NAME)
        means = {
            score: float(
                tally.get_values(scores=[score], value="mean").reshape(-1)[0]
            )
            for score in GLOBAL_BALANCE_SCORES
        }
        std_devs = {
            score: float(
                tally.get_values(scores=[score], value="std_dev").reshape(-1)[0]
            )
            for score in GLOBAL_BALANCE_SCORES
        }
        global_tallies = {
            (
                row["name"].decode("utf-8")
                if isinstance(row["name"], bytes)
                else str(row["name"])
            ): row
            for row in statepoint.global_tallies
        }
        if "leakage" not in global_tallies:
            raise RuntimeError("OpenMC statepoint has no global leakage tally")
        leakage = float(global_tallies["leakage"]["mean"])
        leakage_std = float(global_tallies["leakage"]["std_dev"])

    production = means["nu-fission"]
    production_std = std_devs["nu-fission"]
    excess_scatter = (
        means["(n,2n)"]
        + 2.0 * means["(n,3n)"]
        + 3.0 * means["(n,4n)"]
    )
    excess_scatter_std = (
        std_devs["(n,2n)"]
        + 2.0 * std_devs["(n,3n)"]
        + 3.0 * std_devs["(n,4n)"]
    )
    net_loss = means["absorption"] - excess_scatter
    net_loss_std = std_devs["absorption"] + excess_scatter_std
    if production <= 0.0 or net_loss <= 0.0:
        raise RuntimeError("global collision balance is not positive")
    collision_balance = production / net_loss
    collision_balance_std = (
        production_std / net_loss + production * net_loss_std / net_loss**2
    )
    finite_loss = net_loss + leakage
    finite_loss_std = net_loss_std + leakage_std
    if leakage < 0.0 or finite_loss <= 0.0:
        raise RuntimeError("global finite-domain balance is not positive")
    finite_balance = production / finite_loss
    finite_balance_std = (
        production_std / finite_loss
        + production * finite_loss_std / finite_loss**2
    )
    return {
        "reference_rate_balance_tally_keff": collision_balance,
        "reference_rate_balance_std_dev": collision_balance_std,
        "reference_rate_balance_kind": "collision_balance_kinf",
        "reference_collision_balance_kinf": collision_balance,
        "reference_collision_balance_std_dev": collision_balance_std,
        "reference_rate_balance_production": production,
        "reference_rate_balance_net_loss": net_loss,
        "reference_rate_balance_excess_scatter": excess_scatter,
        "reference_leakage": leakage,
        "reference_leakage_std_dev": leakage_std,
        "reference_finite_balance_keff": finite_balance,
        "reference_finite_balance_std_dev": finite_balance_std,
        "reference_rate_balance_uncertainty_method": (
            "conservative-l1-score-bound-no-covariance"
        ),
        "reference_rate_balance_loss_formula": (
            "absorption-(n,2n)-2*(n,3n)-3*(n,4n)"
        ),
        "reference_finite_balance_loss_formula": (
            "absorption-(n,2n)-2*(n,3n)-3*(n,4n)+leakage"
        ),
    }


def orbit_provenance() -> list[dict[str, Any]]:
    return [
        {
            "id": orbit.id,
            "number": orbit.number,
            "ring": orbit.ring,
            "representative": orbit.representative,
            "material": orbit.material,
            "multiplicity": orbit.multiplicity,
            "members": [
                {"ring": ring, "position": position}
                for ring, position in orbit.members
            ],
            "volume_cm3": orbit_volume_cm3(orbit),
        }
        for orbit in ORBITS.ORBITS
    ]


def _string_array(values: Iterable[str]) -> np.ndarray:
    import h5py

    return np.asarray(tuple(values), dtype=h5py.string_dtype(encoding="utf-8"))


def append_orbit_provenance_hdf5(
    output_path: Path,
    library: mgxs.Library,
    mixture_names: list[str],
) -> None:
    import h5py

    if len(mixture_names) != N_ORBITS:
        raise ValueError(f"expected {N_ORBITS} mixture names")
    domains = list(library.domains)
    if len(domains) != N_ORBITS:
        raise ValueError(f"expected {N_ORBITS} library domains")
    positions = core_layout()
    provenance_json = json.dumps(
        orbit_provenance(), sort_keys=True, separators=(",", ":")
    )
    with h5py.File(output_path, "r+") as h5:
        if "irena_orbit_provenance" in h5:
            del h5["irena_orbit_provenance"]
        group = h5.create_group("irena_orbit_provenance")
        group.attrs["schema"] = "openmc2donjon.irena30-d3-orbits.v1"
        group.attrs["symmetry"] = "D3 (120-degree rotation plus reflection)"
        group.attrs["pooling_stage"] = "OpenMC transport tally accumulation"
        group.attrs["post_hoc_cross_section_averaging"] = False
        group.attrs["volume_contract"] = (
            "orbit multiplicity * one physical hex-node volume"
        )
        group.create_dataset(
            "orbit_ids", data=_string_array(orbit.id for orbit in ORBITS.ORBITS)
        )
        group.create_dataset("orbit_numbers", data=np.arange(1, N_ORBITS + 1))
        group.create_dataset(
            "mixture_names", data=_string_array(mixture_names)
        )
        group.create_dataset(
            "domain_cell_ids", data=np.asarray([int(domain.id) for domain in domains])
        )
        group.create_dataset(
            "rings", data=np.asarray([orbit.ring for orbit in ORBITS.ORBITS])
        )
        group.create_dataset(
            "representatives",
            data=np.asarray([orbit.representative for orbit in ORBITS.ORBITS]),
        )
        group.create_dataset(
            "materials",
            data=_string_array(orbit.material for orbit in ORBITS.ORBITS),
        )
        group.create_dataset(
            "multiplicities",
            data=np.asarray([orbit.multiplicity for orbit in ORBITS.ORBITS]),
        )
        group.create_dataset(
            "volumes_cm3",
            data=np.asarray([orbit_volume_cm3(orbit) for orbit in ORBITS.ORBITS]),
        )
        group.create_dataset(
            "position_ring", data=np.asarray([entry.ring for entry in positions])
        )
        group.create_dataset(
            "position_index",
            data=np.asarray([entry.position for entry in positions]),
        )
        group.create_dataset(
            "position_material",
            data=_string_array(entry.material for entry in positions),
        )
        group.create_dataset(
            "position_to_orbit",
            data=np.asarray([entry.orbit_number for entry in positions]),
        )
        group.create_dataset(
            "position_xy_cm",
            data=np.asarray([(entry.x_cm, entry.y_cm) for entry in positions]),
        )
        group.create_dataset("orbit_json", data=_string_array([provenance_json]))
        h5.attrs["irena_d3_orbit_provenance_json"] = provenance_json
        h5.attrs["orbit_transport_pooling_verified"] = True
        h5.attrs["post_hoc_cross_section_averaging"] = False


def append_energy_coverage_hdf5(output_path: Path, statepoint_path: Path) -> None:
    import h5py

    mean, std_dev, labels, bounds = extract_energy_coverage(statepoint_path)
    global_mean = np.sum(mean, axis=0)
    # Correlations are unavailable in the statepoint; sum standard deviations
    # as a conservative L1 bound rather than claiming independent bins.
    global_std_l1 = np.sum(std_dev, axis=0)
    retained_index = labels.index("retained")
    totals = np.sum(global_mean, axis=0)
    outside = totals - global_mean[retained_index, :]
    outside_fraction = np.divide(
        outside,
        totals,
        out=np.full_like(outside, np.nan),
        where=totals > 0.0,
    )
    with h5py.File(output_path, "r+") as h5:
        if "openmc_energy_coverage" in h5:
            del h5["openmc_energy_coverage"]
        group = h5.create_group("openmc_energy_coverage")
        group.attrs["schema"] = "openmc2donjon.energy-coverage.v1"
        group.attrs["axes"] = "orbit,segment,score"
        group.attrs["global_std_dev_method"] = (
            "conservative-l1-bin-bound-no-covariance"
        )
        group.create_dataset("mean", data=mean)
        group.create_dataset("std_dev", data=std_dev)
        group.create_dataset("segment_names", data=_string_array(labels))
        group.create_dataset(
            "score_names", data=_string_array(ENERGY_COVERAGE_SCORES)
        )
        group.create_dataset("energy_bounds_ev", data=np.asarray(bounds))
        group.create_dataset("global_mean", data=global_mean)
        group.create_dataset("global_std_dev_l1_bound", data=global_std_l1)
        group.create_dataset("global_outside_fraction", data=outside_fraction)
        h5.attrs["reference_energy_coverage_tally"] = ENERGY_COVERAGE_TALLY_NAME
        h5.attrs["reference_energy_coverage_max_outside_fraction"] = float(
            np.nanmax(outside_fraction)
        )
        for score, fraction in zip(
            ENERGY_COVERAGE_SCORES, outside_fraction, strict=True
        ):
            safe_score = score.replace("-", "_")
            h5.attrs[f"reference_energy_coverage_{safe_score}_outside_fraction"] = (
                float(fraction)
            )


def append_position_power_hdf5(output_path: Path, statepoint_path: Path) -> None:
    """Attach uncollapsed 91-position power evidence and uncertainty."""

    import h5py

    mean, std_dev = extract_position_power(statepoint_path)
    kappa_index = POSITION_POWER_SCORES.index("kappa-fission")
    kappa_fission = mean[:, kappa_index]
    kappa_fission_std = std_dev[:, kappa_index]
    total = float(np.sum(kappa_fission))
    total_std_l1 = float(np.sum(kappa_fission_std))
    if not math.isfinite(total) or total <= 0.0:
        raise RuntimeError("91-position OpenMC kappa-fission power is not positive")
    normalized = kappa_fission / total
    # Statepoint bin covariances are unavailable.  This is a conservative L1
    # ratio bound, not an independence assumption or a fitted power tolerance.
    normalized_std_l1 = (
        kappa_fission_std / total
        + kappa_fission * total_std_l1 / total**2
    )
    positions = core_layout()
    with h5py.File(output_path, "r+") as h5:
        if "openmc_position_power" in h5:
            del h5["openmc_position_power"]
        group = h5.create_group("openmc_position_power")
        group.attrs["schema"] = "openmc2donjon.irena30-position-power.v1"
        group.attrs["axes"] = "position,score"
        group.attrs["position_order"] = "DRAGON HEXZ center then rings 1..5"
        group.attrs["normalization"] = "kappa-fission divided by 91-position sum"
        group.attrs["normalized_std_dev_method"] = (
            "conservative-l1-ratio-bound-no-covariance"
        )
        group.attrs["orbit_aggregation_used"] = False
        group.create_dataset("mean", data=mean)
        group.create_dataset("std_dev", data=std_dev)
        group.create_dataset(
            "score_names", data=_string_array(POSITION_POWER_SCORES)
        )
        group.create_dataset("kappa_fission", data=kappa_fission)
        group.create_dataset("kappa_fission_std_dev", data=kappa_fission_std)
        group.create_dataset("normalized_kappa_fission", data=normalized)
        group.create_dataset(
            "normalized_kappa_fission_std_dev_l1_bound",
            data=normalized_std_l1,
        )
        group.create_dataset(
            "position_names",
            data=_string_array(
                f"R{entry.ring}P{entry.position:02d}_{entry.material}"
                for entry in positions
            ),
        )
        group.create_dataset(
            "position_ring", data=np.asarray([entry.ring for entry in positions])
        )
        group.create_dataset(
            "position_index",
            data=np.asarray([entry.position for entry in positions]),
        )
        group.create_dataset(
            "position_material",
            data=_string_array(entry.material for entry in positions),
        )
        group.create_dataset(
            "position_orbit_number",
            data=np.asarray([entry.orbit_number for entry in positions]),
        )
        group.create_dataset(
            "position_orbit_id",
            data=_string_array(
                ORBITS.BY_NUMBER[entry.orbit_number].id for entry in positions
            ),
        )
        group.create_dataset(
            "position_xy_cm",
            data=np.asarray([(entry.x_cm, entry.y_cm) for entry in positions]),
        )
        h5.attrs["reference_position_power_tally"] = POSITION_POWER_TALLY_NAME
        h5.attrs["reference_position_power_count"] = N_HEXES
        h5.attrs["reference_position_power_orbit_aggregated"] = False


def append_reference_evidence_hdf5(
    output_path: Path,
    statepoint_path: Path,
) -> None:
    import h5py

    balance = extract_reference_balance(statepoint_path)
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        keff = statepoint.keff
        reference_keff = float(keff.nominal_value)
        reference_keff_std = float(keff.std_dev)
    with h5py.File(output_path, "r+") as h5:
        h5.attrs["reference_keff"] = reference_keff
        h5.attrs["reference_keff_std_dev"] = reference_keff_std
        h5.attrs["reference_keff_estimator"] = "OpenMC combined"
        for key, value in balance.items():
            h5.attrs[key] = value


def postprocess_hdf5(
    output_path: Path,
    statepoint_path: Path,
    library: mgxs.Library,
    mixture_names: list[str],
) -> None:
    """Attach strict CE flux, coverage, balance, leakage, and provenance."""

    flux, flux_std_dev = extract_volume_flux_with_std_dev(statepoint_path)
    write_openmc_volume_flux_hdf5(
        output_path,
        flux,
        mixture_names=mixture_names,
        std_dev=flux_std_dev,
    )
    append_energy_coverage_hdf5(output_path, statepoint_path)
    append_position_power_hdf5(output_path, statepoint_path)
    append_reference_evidence_hdf5(output_path, statepoint_path)
    append_orbit_provenance_hdf5(output_path, library, mixture_names)


def root_attrs() -> dict[str, object]:
    attrs: dict[str, object] = {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "output_region_count": N_ORBITS,
        "physical_position_count": N_HEXES,
        "global_d3_orbit_count": N_ORBITS,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_mesh_id": ENERGY_MESH_ID,
        "energy_group_count": len(energy_bounds_ev()) - 1,
        "energy_domain_min_ev": energy_bounds_ev()[0],
        "energy_domain_max_ev": energy_bounds_ev()[-1],
        "legendre_order": HANDOFF_LEGENDRE_ORDER,
        "handoff_scatter_format": HANDOFF_SCATTER_FORMAT,
        "donjon_scatter_contract": "consistent nu-scatter matrix",
        "geometry_kind": "explicit 91-position heterogeneous hexagonal full core",
        "hex_pitch_cm": PITCH_CM,
        "hex_side_cm": SIDE_CM,
        # Project/native-SPH validators use this generic provenance key.  It is
        # the same physical regular-hexagon side already recorded above, not a
        # fitted or independently chosen coarse-model dimension.
        "coarse_node_side_cm": SIDE_CM,
        "hex_axial_height_cm": AXIAL_HEIGHT_CM,
        "single_node_volume_cm3": node_volume_cm3(),
        "homogenization_volume_includes_node_catchall": True,
        "radial_boundary_face_count": N_BOUNDARY_FACES,
        "boundary_conditions": "radial vacuum; axial reflective",
        "orbit_symmetry": "D3 (120-degree rotation plus reflection)",
        "orbit_pooling": (
            "one reusable OpenMC wrapper cell/universe per D3 orbit; CellFilter "
            "and MGXS pooled during fine transport over all physical instances"
        ),
        "spatial_mapping": (
            "21 orbit mixtures expanded by the declared 91-position D3 map"
        ),
        "openmc_volume_flux_kind": "orbit-integrated track-length flux",
        "position_power_contract": (
            "91 independent top-level position bins in DRAGON HEXZ order; "
            "kappa-fission plus fission mean/std; never orbit-aggregated"
        ),
        "initial_source_contract": (
            "one local box per 52 physical INT/EXT assemblies; OpenMC "
            "fissionable constraint rejects structure/coolant/exterior proposals"
        ),
        "equivalence_model": "SPH only; ADF absent",
        "forbidden_transformations": (
            "zero-flux fill; blackening; cross-section floor; clipping; "
            "empirical/global keff multiplier; post-hoc XS averaging"
        ),
        "sph_route": (
            "OpenMC CE fine 91-position full core -> Converter 21-orbit reference "
            "MACROLIB -> DRAGON native full-core SPH -> DONJON"
        ),
    }
    if _REFERENCE_KEFF is not None:
        attrs["reference_keff"] = _REFERENCE_KEFF
        attrs["reference_keff_estimator"] = "OpenMC combined"
    if _REFERENCE_KEFF_STD_DEV is not None:
        attrs["reference_keff_std_dev"] = _REFERENCE_KEFF_STD_DEV
    return attrs
