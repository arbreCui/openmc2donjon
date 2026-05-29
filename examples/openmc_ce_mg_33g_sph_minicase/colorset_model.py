"""OpenMC CE/MG colorsets used for OpenMC-side SPH.

The same spatial cell domains are used in the continuous-energy reference
calculation and in the OpenMC multi-group macro calculation.  Each cell domain
becomes one SPH/output region.

The default variant keeps the original three-region smoke:

``CS_FUEL`` -> ``CS_MOD`` -> ``CS_ABS``

Set ``OPENMC2DONJON_COLORSET_VARIANT=two_region`` to exercise the
minimal Alain/Siggi-style colorset with two output regions and therefore two
SPH factors per energy group.

Set ``OPENMC2DONJON_COLORSET_VARIANT=five_region_2d`` to exercise a larger
two-dimensional colorset with five output regions.  Both variants use the same
workflow: OpenMC CE reference, OpenMC MG macro solve on the same geometry, then
OpenMC-side ``SPH(region, group)`` factors for the converter.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import numpy as np
import openmc
import openmc.mgxs as mgxs

from openmc2donjon.energy_groups import load_energy_mesh
from openmc2donjon.openmc_volume_flux import (
    reverse_openmc_energy_filter_flux,
    write_openmc_volume_flux_hdf5,
)


CASE_NAME = "openmc_ce_mg_33g_sph_minicase"
DOMAIN_MODE = "colorset"
DOMAIN_TYPE = "cell"
FUEL_CELL_ID = 201
MODERATOR_CELL_ID = 202
ABSORBER_CELL_ID = 203
REFLECTOR_CELL_ID = 204
SECOND_FUEL_CELL_ID = 205
DEFAULT_COLORSET_VARIANT = "three_region"
ENERGY_MESH_ID = "ecco_33"
ENERGY_GROUP_STRUCTURE = "ECCO-33"
HANDOFF_SCATTER_FORMAT = "legendre"
HANDOFF_LEGENDRE_ORDER = 3
MG_MACRO_SCATTER_FORMAT = "histogram"
MG_MACRO_HISTOGRAM_BINS = 16
MG_MACRO_LEGENDRE_ORDER = HANDOFF_LEGENDRE_ORDER
LEGENDRE_ORDER = HANDOFF_LEGENDRE_ORDER
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
VOLUME_FLUX_TALLY_NAME = "openmc_ce_mg_sph_volume_flux"


@dataclass(frozen=True)
class RunSettings:
    batches: int = 20
    inactive: int = 5
    particles: int = 1_000
    seed: int = 31


@dataclass(frozen=True)
class RegionSpec:
    cell_id: int
    name: str
    material: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @property
    def volume(self) -> float:
        return (self.x_max - self.x_min) * (self.y_max - self.y_min) * 4.0


COLORSET_VARIANT = os.environ.get(
    "OPENMC2DONJON_COLORSET_VARIANT",
    DEFAULT_COLORSET_VARIANT,
).strip()
REGION_SPECS_BY_VARIANT = {
    "two_region": (
        RegionSpec(FUEL_CELL_ID, "CS_FUEL", "colorset fuel", -3.0, 0.0, -2.0, 2.0),
        RegionSpec(MODERATOR_CELL_ID, "CS_MOD", "colorset moderator", 0.0, 3.0, -2.0, 2.0),
    ),
    "three_region": (
        RegionSpec(FUEL_CELL_ID, "CS_FUEL", "colorset fuel", -3.0, -1.0, -2.0, 2.0),
        RegionSpec(MODERATOR_CELL_ID, "CS_MOD", "colorset moderator", -1.0, 1.0, -2.0, 2.0),
        RegionSpec(ABSORBER_CELL_ID, "CS_ABS", "colorset absorber", 1.0, 3.0, -2.0, 2.0),
    ),
    "five_region_2d": (
        RegionSpec(FUEL_CELL_ID, "CS_FUEL_L", "colorset fuel", -3.0, -1.0, -2.0, 2.0),
        RegionSpec(MODERATOR_CELL_ID, "CS_MOD", "colorset moderator", -1.0, 1.0, -2.0, 0.0),
        RegionSpec(SECOND_FUEL_CELL_ID, "CS_FUEL_U", "colorset fuel", -1.0, 1.0, 0.0, 2.0),
        RegionSpec(ABSORBER_CELL_ID, "CS_ABS", "colorset absorber", 1.0, 3.0, -2.0, 0.0),
        RegionSpec(REFLECTOR_CELL_ID, "CS_REF", "colorset reflector", 1.0, 3.0, 0.0, 2.0),
    ),
}
if COLORSET_VARIANT not in REGION_SPECS_BY_VARIANT:
    allowed = ", ".join(sorted(REGION_SPECS_BY_VARIANT))
    raise ValueError(
        "OPENMC2DONJON_COLORSET_VARIANT must be one of "
        f"{allowed}; got {COLORSET_VARIANT!r}"
    )
REGION_SPECS = REGION_SPECS_BY_VARIANT[COLORSET_VARIANT]
DOMAIN_IDS = tuple(spec.cell_id for spec in REGION_SPECS)
DOMAIN_NAME_BY_ID = {spec.cell_id: spec.name for spec in REGION_SPECS}
DOMAIN_VOLUME_BY_ID = {spec.cell_id: spec.volume for spec in REGION_SPECS}


def energy_bounds_ev() -> list[float]:
    """Return ECCO-33 boundaries in OpenMC ascending-energy order."""

    return load_energy_mesh(ENERGY_MESH_ID).boundaries_descending[::-1].tolist()


def default_case_dir() -> Path:
    return Path(
        os.environ.get("OPENMC2DONJON_COLORSET_DIR", Path(__file__).parent)
    ).resolve()


def build_materials() -> openmc.Materials:
    fuel = openmc.Material(material_id=1, name="colorset fuel")
    fuel.set_density("g/cm3", 10.4)
    fuel.add_nuclide("U235", 4.8e-2)
    fuel.add_nuclide("U238", 2.10e-2)
    fuel.add_nuclide("O16", 1.38e-1)

    moderator = openmc.Material(material_id=2, name="colorset moderator")
    moderator.set_density("g/cm3", 1.0)
    moderator.add_nuclide("H1", 6.66e-2)
    moderator.add_nuclide("O16", 3.33e-2)

    absorber = openmc.Material(material_id=3, name="colorset absorber")
    absorber.set_density("g/cm3", 1.1)
    absorber.add_nuclide("H1", 6.0e-2)
    absorber.add_nuclide("O16", 3.0e-2)
    absorber.add_nuclide("B10", 8.0e-4)
    absorber.add_nuclide("B11", 3.2e-3)

    reflector = openmc.Material(material_id=4, name="colorset reflector")
    reflector.set_density("g/cm3", 0.72)
    reflector.add_nuclide("H1", 4.8e-2)
    reflector.add_nuclide("O16", 2.4e-2)

    materials = openmc.Materials([fuel, moderator, absorber, reflector])
    cross_sections = openmc.config.get("cross_sections")
    if cross_sections:
        materials.cross_sections = str(cross_sections)
    return materials


def build_geometry(materials: openmc.Materials | None = None) -> openmc.Geometry:
    materials = materials or build_materials()
    by_name = {material.name: material for material in materials}

    x_values = sorted({spec.x_min for spec in REGION_SPECS} | {spec.x_max for spec in REGION_SPECS})
    y_values = sorted({spec.y_min for spec in REGION_SPECS} | {spec.y_max for spec in REGION_SPECS})
    x_min, x_max = x_values[0], x_values[-1]
    y_min, y_max = y_values[0], y_values[-1]
    x_surfaces = {
        value: openmc.XPlane(
            surface_id=10 + index,
            x0=value,
            boundary_type="reflective" if value in (x_min, x_max) else "transmission",
        )
        for index, value in enumerate(x_values)
    }
    y_surfaces = {
        value: openmc.YPlane(
            surface_id=100 + index,
            y0=value,
            boundary_type="reflective" if value in (y_min, y_max) else "transmission",
        )
        for index, value in enumerate(y_values)
    }
    z0 = openmc.ZPlane(surface_id=200, z0=-2.0, boundary_type="reflective")
    z1 = openmc.ZPlane(surface_id=201, z0=2.0, boundary_type="reflective")

    cells: list[openmc.Cell] = []
    for spec in REGION_SPECS:
        cell = openmc.Cell(cell_id=spec.cell_id, name=spec.name)
        cell.fill = by_name[spec.material]
        cell.region = (
            +x_surfaces[spec.x_min]
            & -x_surfaces[spec.x_max]
            & +y_surfaces[spec.y_min]
            & -y_surfaces[spec.y_max]
            & +z0
            & -z1
        )
        cell.volume = DOMAIN_VOLUME_BY_ID[spec.cell_id]
        cells.append(cell)
    root = openmc.Universe(universe_id=1, name="colorset root")
    root.add_cells(cells)
    return openmc.Geometry(root)


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
    settings.source = openmc.IndependentSource(
        space=openmc.stats.Box((-2.9, -1.9, -1.9), (2.9, 1.9, 1.9)),
        constraints={"fissionable": True},
    )
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    return settings


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    cells = geometry.get_all_cells()
    selected = [cells[cell_id] for cell_id in DOMAIN_IDS]
    for cell in selected:
        cell.volume = DOMAIN_VOLUME_BY_ID[int(cell.id)]
    return selected


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
        openmc.CellFilter(list(DOMAIN_IDS), filter_id=9_001),
        openmc.EnergyFilter(energy_bounds_ev(), filter_id=9_002),
    ]
    tally.scores = ["flux"]
    return tally


def build_ce_tallies(
    geometry: openmc.Geometry,
    *,
    mg_macro_scatter_format: str = MG_MACRO_SCATTER_FORMAT,
    mg_macro_histogram_bins: int = MG_MACRO_HISTOGRAM_BINS,
    mg_macro_legendre_order: int = MG_MACRO_LEGENDRE_ORDER,
) -> openmc.Tallies:
    library = build_library(geometry)
    tallies = openmc.Tallies()
    if hasattr(library, "add_to_tallies"):
        library.add_to_tallies(tallies, merge=True)
    else:
        library.add_to_tallies_file(tallies, merge=True)
    if not _same_scatter_treatment(
        HANDOFF_SCATTER_FORMAT,
        HANDOFF_LEGENDRE_ORDER,
        MG_MACRO_HISTOGRAM_BINS,
        mg_macro_scatter_format,
        mg_macro_legendre_order,
        mg_macro_histogram_bins,
    ):
        mg_macro_library = build_library(
            geometry,
            scatter_format=mg_macro_scatter_format,
            legendre_order=mg_macro_legendre_order,
            histogram_bins=mg_macro_histogram_bins,
        )
        if hasattr(mg_macro_library, "add_to_tallies"):
            mg_macro_library.add_to_tallies(tallies, merge=True)
        else:
            mg_macro_library.add_to_tallies_file(tallies, merge=True)
    tallies.append(build_volume_flux_tally())
    return tallies


def _same_scatter_treatment(
    left_format: str,
    left_legendre_order: int,
    left_histogram_bins: int,
    right_format: str,
    right_legendre_order: int,
    right_histogram_bins: int,
) -> bool:
    if left_format != right_format:
        return False
    if left_format == "legendre":
        return left_legendre_order == right_legendre_order
    if left_format == "histogram":
        return left_histogram_bins == right_histogram_bins
    return False


def build_mg_tallies() -> openmc.Tallies:
    return openmc.Tallies([build_volume_flux_tally()])


def export_ce_xml(
    case_dir: Path,
    *,
    run_settings: RunSettings | None = None,
    mg_macro_scatter_format: str = MG_MACRO_SCATTER_FORMAT,
    mg_macro_histogram_bins: int = MG_MACRO_HISTOGRAM_BINS,
    mg_macro_legendre_order: int = MG_MACRO_LEGENDRE_ORDER,
) -> None:
    case_dir = Path(case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    materials = build_materials()
    geometry = build_geometry(materials)
    settings = build_settings(run_settings, energy_mode="continuous-energy")
    tallies = build_ce_tallies(
        geometry,
        mg_macro_scatter_format=mg_macro_scatter_format,
        mg_macro_histogram_bins=mg_macro_histogram_bins,
        mg_macro_legendre_order=mg_macro_legendre_order,
    )

    materials.export_to_xml(case_dir / "materials.xml")
    geometry.export_to_xml(case_dir / "geometry.xml")
    settings.export_to_xml(case_dir / "settings.xml")
    tallies.export_to_xml(case_dir / "tallies.xml")


def load_statepoint(library: mgxs.Library, statepoint_path: Path) -> None:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        library.load_from_statepoint(statepoint)
        keff = getattr(statepoint, "keff", None)
        if keff is not None:
            print(f"OpenMC colorset keff = {keff}")


def extract_volume_flux_with_std_dev(
    statepoint_path: Path,
) -> tuple[np.ndarray, np.ndarray]:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=VOLUME_FLUX_TALLY_NAME)
        values = np.asarray(tally.get_values(scores=["flux"], value="mean"), dtype=float)
        std_dev = np.asarray(
            tally.get_values(scores=["flux"], value="std_dev"),
            dtype=float,
        )
    shape = {
        "mixture_count": len(DOMAIN_IDS),
        "energy_groups": len(energy_bounds_ev()) - 1,
    }
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
    return dict(DOMAIN_NAME_BY_ID)


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "colorset_variant": COLORSET_VARIANT,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "output_region_count": len(DOMAIN_IDS),
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_group_count": len(energy_bounds_ev()) - 1,
        "legendre_order": HANDOFF_LEGENDRE_ORDER,
        "handoff_scatter_format": HANDOFF_SCATTER_FORMAT,
        "mg_macro_scatter_format": MG_MACRO_SCATTER_FORMAT,
        "mg_macro_histogram_bins": MG_MACRO_HISTOGRAM_BINS,
        "spatial_mapping": "one OpenMC CE/MG cell domain -> one SPH/DONJON mixture",
        "sph_route": "OpenMC CE reference + OpenMC MG same geometry",
    }
