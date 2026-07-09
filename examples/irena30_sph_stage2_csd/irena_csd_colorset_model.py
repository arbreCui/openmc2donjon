"""IRENA CSD-absorber colorset CE/MG model for OpenMC-side SPH (Stage 2).

Three-model SPH route, absorber-colorset stage: an explicit seven-assembly
colorset (center CSD control assembly + six INT fuel neighbors, DRAGON case
``csd_int``) where per-assembly homogenization has a real absorber defect
for SPH to correct.

The CE geometry is reused verbatim from the IRENA workspace's colorset
comparison infrastructure (``colorset_rebuild_20260527/ce_compare``):
``make_explicit7_geometry`` places seven top-level assembly cells with
shared transmission planes, white outer edges, and reflective z — those
seven cells are the MGXS cell domains directly. The MG coarse model is
produced by ``mgxs.Library.create_mg_mode()`` (seven homogeneous hexes,
same boundaries).

Local inputs (not shipped):

- ``IRENA_CE_COMPARE_DIR`` (default
  ``/Users/wen/dragon-5.1/Dragon/irena_core/colorset_rebuild_20260527/ce_compare``)
- CE nuclear data via ``OPENMC_CROSS_SECTIONS``
"""

from __future__ import annotations

import importlib
import math
import os
import re
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

CASE_NAME = "irena30_sph_stage2_csd"
# DRAGON colorset case: csd_int (CSD absorber center), pnl_ext (Pb
# reflector center), dsdf_int, int_ext, ext_int, refl_ext.
COLORSET_CASE = os.environ.get("IRENA_SPH2_CASE", "csd_int")
DOMAIN_MODE = "hex_colorset"
DOMAIN_TYPE = "cell"
N_ASSEMBLIES = 7
ENERGY_MESH_ID = "ecco_33"
ENERGY_GROUP_STRUCTURE = "ECCO-33"
HANDOFF_SCATTER_FORMAT = "legendre"
HANDOFF_LEGENDRE_ORDER = 3
MG_MACRO_SCATTER_FORMAT = "histogram"
MG_MACRO_HISTOGRAM_BINS = 16
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
VOLUME_FLUX_TALLY_NAME = "irena30_sph_stage2_volume_flux"
AXIAL_HALF_HEIGHT_CM = 50.0

_CELL_NAME_RE = re.compile(
    rf"^{COLORSET_CASE}_explicit7_(\d+)_(CSD|INT|EXT|PNL|DSDF|REFL)$"
)


@dataclass(frozen=True)
class RunSettings:
    batches: int = 60
    inactive: int = 20
    particles: int = 20_000
    seed: int = 31


def default_ce_compare_dir() -> Path:
    return Path(
        os.environ.get(
            "IRENA_CE_COMPARE_DIR",
            "/Users/wen/dragon-5.1/Dragon/irena_core/colorset_rebuild_20260527/ce_compare",
        )
    ).resolve()


def default_case_dir() -> Path:
    return Path(os.environ.get("OPENMC2DONJON_IRENA_SPH2_DIR", Path(__file__).parent)).resolve()


def _load_ce_compare_modules():
    """Import the colorset infrastructure with its own cross-imports intact."""
    root = default_ce_compare_dir()
    if not (root / "openmc_explicit7_probe.py").is_file():
        raise FileNotFoundError(f"IRENA ce_compare directory not found: {root}")
    inserted = str(root) not in sys.path
    if inserted:
        sys.path.insert(0, str(root))
    try:
        colorset_common = importlib.import_module("colorset_common")
        openmc_colorset = importlib.import_module("openmc_colorset")
        explicit7 = importlib.import_module("openmc_explicit7_probe")
    finally:
        if inserted:
            sys.path.remove(str(root))
    return colorset_common, openmc_colorset, explicit7


def domain_name(index: int, kind: str) -> str:
    return f"{kind}_C" if index == 0 else f"{kind}_N{index}"


def assembly_volume_cm3(colorset_common) -> float:
    edge = float(colorset_common.lattice_box_edges()[-1])
    hex_area = 3.0 * math.sqrt(3.0) / 2.0 * edge**2
    return hex_area * 2.0 * AXIAL_HALF_HEIGHT_CM


def energy_bounds_ev() -> list[float]:
    return load_energy_mesh(ENERGY_MESH_ID).boundaries_descending[::-1].tolist()


def colorset_cells(geometry: openmc.Geometry) -> list[tuple[int, str, openmc.Cell]]:
    """Return the 7 assembly cells as (position, kind, cell), center first."""
    entries: list[tuple[int, str, openmc.Cell]] = []
    for cell in geometry.get_all_cells().values():
        match = _CELL_NAME_RE.match(cell.name or "")
        if match:
            entries.append((int(match.group(1)), match.group(2), cell))
    entries.sort(key=lambda item: item[0])
    if len(entries) != N_ASSEMBLIES:
        raise RuntimeError(f"expected {N_ASSEMBLIES} colorset cells, found {len(entries)}")
    return entries


def build_model_parts():
    colorset_common, openmc_colorset, explicit7 = _load_ce_compare_modules()
    materials, mats = openmc_colorset.make_materials()
    geometry = explicit7.make_explicit7_geometry(COLORSET_CASE, mats)
    volume = assembly_volume_cm3(colorset_common)
    for _pos, _kind, cell in colorset_cells(geometry):
        cell.volume = volume
    return materials, geometry, openmc_colorset


def build_settings(
    run_settings: RunSettings | None = None,
    *,
    energy_mode: str = "continuous-energy",
) -> openmc.Settings:
    run_settings = run_settings or RunSettings()
    _colorset_common, openmc_colorset, _explicit7 = _load_ce_compare_modules()
    settings = openmc_colorset.make_settings(
        run_settings.batches, run_settings.inactive, run_settings.particles
    )
    settings.energy_mode = energy_mode
    settings.seed = run_settings.seed
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    if energy_mode != "continuous-energy":
        settings.temperature = {}
    return settings


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    entries = colorset_cells(geometry)
    cells = [cell for _pos, _kind, cell in entries]
    if any(cell.volume is None for cell in cells):
        colorset_common, _openmc_colorset, _explicit7 = _load_ce_compare_modules()
        volume = assembly_volume_cm3(colorset_common)
        for cell in cells:
            if cell.volume is None:
                cell.volume = volume
    return cells


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


def build_volume_flux_tally(geometry: openmc.Geometry) -> openmc.Tally:
    cell_ids = [int(cell.id) for _pos, _kind, cell in colorset_cells(geometry)]
    tally = openmc.Tally(name=VOLUME_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter(cell_ids, filter_id=9_201),
        openmc.EnergyFilter(energy_bounds_ev(), filter_id=9_202),
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
    tallies.append(build_volume_flux_tally(geometry))
    return tallies


def build_mg_tallies(geometry: openmc.Geometry) -> openmc.Tallies:
    return openmc.Tallies([build_volume_flux_tally(geometry)])


def export_ce_xml(case_dir: Path, run_settings: RunSettings | None = None) -> None:
    case_dir = Path(case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    materials, geometry, _openmc_colorset = build_model_parts()
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
            print(f"IRENA SPH stage2 (csd_int) keff = {keff}")


def extract_volume_flux_with_std_dev(statepoint_path: Path) -> tuple[np.ndarray, np.ndarray]:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=VOLUME_FLUX_TALLY_NAME)
        values = np.asarray(tally.get_values(scores=["flux"], value="mean"), dtype=float)
        std_dev = np.asarray(tally.get_values(scores=["flux"], value="std_dev"), dtype=float)
    shape = {"mixture_count": N_ASSEMBLIES, "energy_groups": len(energy_bounds_ev()) - 1}
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


def domain_names(library: mgxs.Library) -> dict[int, str]:
    names: dict[int, str] = {}
    for domain in library.domains:
        match = _CELL_NAME_RE.match(domain.name or "")
        if not match:
            raise RuntimeError(f"unexpected colorset cell name: {domain.name!r}")
        names[int(domain.id)] = domain_name(int(match.group(1)), match.group(2))
    return names


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "colorset_case": COLORSET_CASE,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "output_region_count": N_ASSEMBLIES,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_group_count": len(energy_bounds_ev()) - 1,
        "legendre_order": HANDOFF_LEGENDRE_ORDER,
        "handoff_scatter_format": HANDOFF_SCATTER_FORMAT,
        "mg_macro_scatter_format": MG_MACRO_SCATTER_FORMAT,
        "mg_macro_histogram_bins": MG_MACRO_HISTOGRAM_BINS,
        "geometry_kind": "hexagonal",
        "boundary_conditions": "radial white, axial reflective (explicit7 colorset)",
        "spatial_mapping": "one colorset assembly -> one SPH/DONJON mixture (CSD_C, INT_N1..N6)",
        "sph_route": "OpenMC CE fine + OpenMC MG coarse (create_mg_mode), same boundaries",
    }
