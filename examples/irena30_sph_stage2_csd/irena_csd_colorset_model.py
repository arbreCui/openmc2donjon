"""IRENA local-signature CE/MG model for native DRAGON SPH.

The model accepts a declared center and six ordered neighbors.  ``OUT`` slots
are physical voids at the IRENA radial boundary; all remaining patch edges are
artificial specular-reflective boundaries matching the DRAGON SNT ``ALBE 1``
operator.  The legacy uniform-neighbor colorset names are
still accepted for comparison, but production qualification uses the exact
benchmark-specific signatures declared by ``irena30_native_fullcore``.

The assembly universes are reused from the IRENA workspace's colorset
comparison infrastructure. Seven top-level node cells are placed with shared
    transmission planes, specular-reflective outer edges, and reflective z. Their side length is
declared by ``IRENA_SPH2_NODE_SIDE_CM``. For a full-core handoff it must equal
the downstream node side (10.1036 cm in the IRENA template), so the assembly
universe's outer catch-all sodium is included in the homogenization volume.

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

CASE_NAME = "irena30_native_colorset"
# DRAGON colorset case: csd_int (CSD absorber center), pnl_ext (Pb
# reflector center), dsdf_int, int_ext, ext_int, refl_ext.
COLORSET_CASE = os.environ.get("IRENA_SPH2_CASE", "csd_int")
LEGACY_CASES = {
    "int_ext": ("INT", ("EXT",) * 6),
    "ext_int": ("EXT", ("INT",) * 6),
    "refl_ext": ("REFL", ("EXT",) * 6),
    "csd_int": ("CSD", ("INT",) * 6),
    "dsdf_int": ("DSDF", ("INT",) * 6),
    "pnl_ext": ("PNL", ("EXT",) * 6),
}
_CENTER_KIND_ENV = os.environ.get("IRENA_SPH2_CENTER_KIND")
_NEIGHBOR_KINDS_ENV = os.environ.get("IRENA_SPH2_NEIGHBOR_KINDS")
if (_CENTER_KIND_ENV is None) != (_NEIGHBOR_KINDS_ENV is None):
    raise ValueError(
        "IRENA_SPH2_CENTER_KIND and IRENA_SPH2_NEIGHBOR_KINDS must be set together"
    )
if _CENTER_KIND_ENV is None:
    if COLORSET_CASE not in LEGACY_CASES:
        raise ValueError(
            f"unknown legacy colorset {COLORSET_CASE!r}; declare center and neighbors"
        )
    CENTER_KIND, NEIGHBOR_KINDS = LEGACY_CASES[COLORSET_CASE]
else:
    CENTER_KIND = _CENTER_KIND_ENV.strip().upper()
    NEIGHBOR_KINDS = tuple(
        item.strip().upper() for item in _NEIGHBOR_KINDS_ENV.split(",")
    )
if len(NEIGHBOR_KINDS) != 6:
    raise ValueError("IRENA_SPH2_NEIGHBOR_KINDS must contain exactly six entries")
_VALID_KINDS = frozenset({"CSD", "INT", "EXT", "PNL", "DSDF", "REFL", "OUT"})
if CENTER_KIND not in _VALID_KINDS - {"OUT"} or any(
    kind not in _VALID_KINDS for kind in NEIGHBOR_KINDS
):
    raise ValueError("IRENA local signature contains an unsupported material kind")
DECLARED_KINDS = (CENTER_KIND, *NEIGHBOR_KINDS)
DOMAIN_MODE = "hex_colorset"
DOMAIN_TYPE = "cell"
N_ASSEMBLIES = sum(kind != "OUT" for kind in DECLARED_KINDS)
ENERGY_MESH_ID = os.environ.get("IRENA_SPH2_ENERGY_MESH_ID", "ecco_33")
ENERGY_MESH = load_energy_mesh(ENERGY_MESH_ID)
ENERGY_GROUP_STRUCTURE = ENERGY_MESH.name
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
    "consistent scatter matrix",
    "consistent nu-scatter matrix",
    "multiplicity matrix",
    "transport",
]
VOLUME_FLUX_TALLY_NAME = "irena30_sph_stage2_volume_flux"
ENERGY_COVERAGE_TALLY_NAME = "irena30_sph_stage2_energy_coverage"
ENERGY_COVERAGE_SCORES = (
    "absorption",
    "fission",
    "kappa-fission",
    "nu-fission",
)
GLOBAL_BALANCE_TALLY_NAME = "irena30_sph_stage2_global_balance"
GLOBAL_BALANCE_SCORES = (
    "absorption",
    "nu-fission",
    "(n,2n)",
    "(n,3n)",
    "(n,4n)",
)
FULL_ENERGY_MIN_EV = 1.0e-5
FULL_ENERGY_MAX_EV = 2.0e7
AXIAL_HALF_HEIGHT_CM = 50.0
NODE_SIDE_CM = (
    None
    if not os.environ.get("IRENA_SPH2_NODE_SIDE_CM")
    else float(os.environ["IRENA_SPH2_NODE_SIDE_CM"])
)

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


def declared_node_side_cm(colorset_common) -> float:
    side = (
        float(colorset_common.lattice_box_edges()[-1])
        if NODE_SIDE_CM is None
        else NODE_SIDE_CM
    )
    if not math.isfinite(side) or side <= 0.0:
        raise ValueError("IRENA_SPH2_NODE_SIDE_CM must be positive and finite")
    return side


def assembly_volume_cm3(colorset_common) -> float:
    edge = declared_node_side_cm(colorset_common)
    hex_area = 3.0 * math.sqrt(3.0) / 2.0 * edge**2
    return hex_area * 2.0 * AXIAL_HALF_HEIGHT_CM


def energy_bounds_ev() -> list[float]:
    return ENERGY_MESH.boundaries_descending[::-1].tolist()


def energy_coverage_segments() -> tuple[list[str], list[float]]:
    """Return the non-empty CE coverage segments and their energy bounds."""

    lower, upper = energy_bounds_ev()[0], energy_bounds_ev()[-1]
    if not (FULL_ENERGY_MIN_EV <= lower < upper <= FULL_ENERGY_MAX_EV):
        raise ValueError(
            f"energy mesh {ENERGY_MESH_ID!r} lies outside the declared CE coverage "
            f"domain {FULL_ENERGY_MIN_EV:g}..{FULL_ENERGY_MAX_EV:g} eV"
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


def energy_coverage_bounds_ev() -> list[float]:
    """Return strictly increasing bounds for the active coverage segments."""

    _labels, bounds = energy_coverage_segments()
    return bounds


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
    geometry = make_explicit7_node_geometry(
        colorset_common,
        openmc_colorset,
        explicit7,
        mats,
    )
    volume = assembly_volume_cm3(colorset_common)
    for _pos, _kind, cell in colorset_cells(geometry):
        cell.volume = volume
    return materials, geometry, openmc_colorset


def make_explicit7_node_geometry(
    colorset_common,
    openmc_colorset,
    explicit7,
    mats: dict[str, openmc.Material],
) -> openmc.Geometry:
    """Build the fine colorset on the declared downstream node envelope."""

    universes = openmc_colorset.make_assembly_universes(mats)
    side = declared_node_side_cm(colorset_common)
    centers = explicit7.centers(side)
    vertices_by_center = [explicit7.hex_vertices(side, center) for center in centers]
    edge_count: dict[tuple, int] = {}
    edge_owners: dict[tuple, list[int]] = {}
    declared_edge_owners: dict[tuple, list[int]] = {}
    for index, vertices in enumerate(vertices_by_center):
        for first, second in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            key = explicit7.edge_key(first, second)
            declared_edge_owners.setdefault(key, []).append(index)
            if DECLARED_KINDS[index] == "OUT":
                continue
            edge_count[key] = edge_count.get(key, 0) + 1
            edge_owners.setdefault(key, []).append(index)
    surfaces: dict[tuple, openmc.Surface] = {}
    for index, vertices in enumerate(vertices_by_center):
        if DECLARED_KINDS[index] == "OUT":
            continue
        for first, second in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            key = explicit7.edge_key(first, second)
            if key in surfaces:
                continue
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            a, b = dy, -dx
            d = a * first[0] + b * first[1]
            if edge_count[key] > 1:
                boundary = "transmission"
            elif any(
                DECLARED_KINDS[owner] == "OUT"
                for owner in declared_edge_owners.get(key, ())
            ):
                # Every active-to-OUT face is a physical radial-vacuum face.
                # This includes faces belonging to an active neighbour as
                # well as faces belonging to the center.  Testing only for
                # center index 0 silently turned some physical leakage faces
                # into artificial white boundaries in sparse signatures.
                boundary = "vacuum"
            else:
                # SNT applies ALBE 1 by reflecting the discrete direction.
                # OpenMC ``white`` is diffuse reflection and is therefore a
                # different boundary operator for heterogeneous signatures.
                boundary = "reflective"
            surfaces[key] = openmc.Plane(a=a, b=b, d=d, boundary_type=boundary)
    z_lo = openmc.ZPlane(z0=-AXIAL_HALF_HEIGHT_CM, boundary_type="reflective")
    z_hi = openmc.ZPlane(z0=AXIAL_HALF_HEIGHT_CM, boundary_type="reflective")
    cells: list[openmc.Cell] = []
    for index, (center, vertices) in enumerate(
        zip(centers, vertices_by_center, strict=True)
    ):
        kind = DECLARED_KINDS[index]
        if kind == "OUT":
            continue
        region = +z_lo & -z_hi
        for first, second in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            surface = surfaces[explicit7.edge_key(first, second)]
            value = surface.a * center[0] + surface.b * center[1] - surface.d
            region &= -surface if value < 0.0 else +surface
        cell = openmc.Cell(
            name=f"{COLORSET_CASE}_explicit7_{index}_{kind}",
            fill=universes[kind],
            region=region,
        )
        cell.translation = (center[0], center[1], 0.0)
        cells.append(cell)
    return openmc.Geometry(cells)


def build_settings(
    run_settings: RunSettings | None = None,
    *,
    energy_mode: str = "continuous-energy",
) -> openmc.Settings:
    run_settings = run_settings or RunSettings()
    colorset_common, openmc_colorset, explicit7 = _load_ce_compare_modules()
    settings = openmc_colorset.make_settings(
        run_settings.batches, run_settings.inactive, run_settings.particles
    )
    settings.energy_mode = energy_mode
    settings.seed = run_settings.seed
    side = declared_node_side_cm(colorset_common)
    apothem = side * math.sqrt(3.0) / 2.0
    fuel_sources = []
    for kind, (x, y) in zip(
        DECLARED_KINDS,
        explicit7.centers(side),
        strict=True,
    ):
        if kind not in {"INT", "EXT"}:
            continue
        fuel_sources.append(
            openmc.IndependentSource(
                space=openmc.stats.Box(
                    (x - side, y - apothem, -49.0),
                    (x + side, y + apothem, 49.0),
                ),
                energy=openmc.stats.Watt(),
                constraints={"fissionable": True},
                strength=1.0,
            )
        )
    if not fuel_sources:
        raise ValueError("IRENA local signature must contain at least one INT/EXT fuel node")
    settings.source = fuel_sources
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


def build_energy_coverage_tally(geometry: openmc.Geometry) -> openmc.Tally:
    """Measure reaction-rate weight below, inside, and above the MG energy domain."""

    cell_ids = [int(cell.id) for _pos, _kind, cell in colorset_cells(geometry)]
    tally = openmc.Tally(name=ENERGY_COVERAGE_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter(cell_ids, filter_id=9_203),
        openmc.EnergyFilter(energy_coverage_bounds_ev(), filter_id=9_204),
    ]
    tally.scores = list(ENERGY_COVERAGE_SCORES)
    return tally


def build_global_balance_tally() -> openmc.Tally:
    """Measure full-model production and loss without a spatial/energy filter.

    This tally is deliberately separate from the MGXS tallies.  Its unfiltered
    track-length scores let the physical-closure gate distinguish an energy
    truncation from incomplete spatial coverage or an export-order defect.
    """

    tally = openmc.Tally(name=GLOBAL_BALANCE_TALLY_NAME)
    tally.estimator = "tracklength"
    # The multiplying-scatter correction is tallied by its physical reaction
    # channels instead of subtracting two large, strongly correlated
    # ``nu-scatter`` and ``scatter`` estimates.  Up to the 20 MeV handoff
    # ceiling, the loaded ENDF/B-VIII.1 materials contain (n,2n), (n,3n),
    # and (n,4n) neutron-multiplication channels.  Their excess-neutron
    # weights are respectively 1, 2, and 3 in the neutron balance.
    tally.scores = list(GLOBAL_BALANCE_SCORES)
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
    tallies.append(build_energy_coverage_tally(geometry))
    tallies.append(build_global_balance_tally())
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
            print(f"IRENA SPH stage2 ({COLORSET_CASE}) keff = {keff}")


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
    append_reference_balance_hdf5(output_path, statepoint_path)


def extract_reference_balance(statepoint_path: Path) -> dict[str, float | str]:
    """Return collision and finite-domain neutron-balance evidence.

    OpenMC does not persist the covariance between tally scores.  The
    uncertainty is therefore propagated with the triangle inequality.  This
    is a conservative statistical bound, not a fitted tolerance or an
    eigenvalue correction.
    """

    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        tally = statepoint.get_tally(name=GLOBAL_BALANCE_TALLY_NAME)
        means = {
            score: float(tally.get_values(scores=[score], value="mean").reshape(-1)[0])
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
    # Both subtraction and the ratio use a no-covariance triangle bound.
    net_loss_std = std_devs["absorption"] + excess_scatter_std
    if production <= 0.0 or net_loss <= 0.0:
        raise RuntimeError("global neutron-balance tally is not positive")
    collision_balance_kinf = production / net_loss
    collision_balance_std = (
        production_std / net_loss
        + production * net_loss_std / net_loss**2
    )
    finite_loss = net_loss + leakage
    finite_loss_std = net_loss_std + leakage_std
    if finite_loss <= 0.0 or leakage < 0.0:
        raise RuntimeError("global finite-domain neutron balance is not positive")
    finite_balance_keff = production / finite_loss
    finite_balance_std = (
        production_std / finite_loss
        + production * finite_loss_std / finite_loss**2
    )
    return {
        # Legacy aliases remain readable by older summaries, but their kind
        # is now explicit: this is K-infinity from collision terms only.
        "reference_rate_balance_tally_keff": collision_balance_kinf,
        "reference_rate_balance_std_dev": collision_balance_std,
        "reference_rate_balance_kind": "collision_balance_kinf",
        "reference_collision_balance_kinf": collision_balance_kinf,
        "reference_collision_balance_std_dev": collision_balance_std,
        "reference_rate_balance_production": production,
        "reference_rate_balance_net_loss": net_loss,
        "reference_rate_balance_excess_scatter": excess_scatter,
        "reference_leakage": leakage,
        "reference_leakage_std_dev": leakage_std,
        "reference_finite_balance_keff": finite_balance_keff,
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


def append_reference_balance_hdf5(
    output_path: Path,
    statepoint_path: Path,
) -> None:
    """Attach direct OpenMC balance evidence used by the acceptance gate."""

    import h5py

    payload = extract_reference_balance(statepoint_path)
    with h5py.File(output_path, "r+") as h5:
        for key, value in payload.items():
            h5.attrs[key] = value


def domain_names(library: mgxs.Library) -> dict[int, str]:
    names: dict[int, str] = {}
    for domain in library.domains:
        match = _CELL_NAME_RE.match(domain.name or "")
        if not match:
            raise RuntimeError(f"unexpected colorset cell name: {domain.name!r}")
        names[int(domain.id)] = domain_name(int(match.group(1)), match.group(2))
    return names


def root_attrs() -> dict[str, object]:
    attrs: dict[str, object] = {
        "case": CASE_NAME,
        "colorset_case": COLORSET_CASE,
        "center_kind": CENTER_KIND,
        "neighbor_kinds": ",".join(NEIGHBOR_KINDS),
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "output_region_count": N_ASSEMBLIES,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_mesh_id": ENERGY_MESH_ID,
        "energy_group_count": len(energy_bounds_ev()) - 1,
        "energy_domain_min_ev": energy_bounds_ev()[0],
        "energy_domain_max_ev": energy_bounds_ev()[-1],
        "legendre_order": HANDOFF_LEGENDRE_ORDER,
        "handoff_scatter_format": HANDOFF_SCATTER_FORMAT,
        "mg_macro_scatter_format": MG_MACRO_SCATTER_FORMAT,
        "mg_macro_histogram_bins": MG_MACRO_HISTOGRAM_BINS,
        "donjon_scatter_contract": "consistent nu-scatter matrix",
        "geometry_kind": "hexagonal",
        "coarse_node_side_cm": declared_node_side_cm(
            _load_ce_compare_modules()[0]
        ),
        "homogenization_volume_includes_node_catchall": True,
        "boundary_conditions": (
            "active-to-OUT vacuum; artificial patch faces specular-reflective; "
            "active shared faces transmission; axial reflective"
            if "OUT" in NEIGHBOR_KINDS
            else "artificial radial patch faces specular-reflective; active shared faces transmission; axial reflective"
        ),
        "spatial_mapping": (
            "ordered center-plus-six-neighbor local signature; OUT slots are physical void"
        ),
        "sph_route": "OpenMC CE fine -> Converter reference MACROLIB -> DRAGON native SPH",
    }
    if _REFERENCE_KEFF is not None:
        attrs["reference_keff"] = _REFERENCE_KEFF
        attrs["reference_keff_estimator"] = "OpenMC combined"
    if _REFERENCE_KEFF_STD_DEV is not None:
        attrs["reference_keff_std_dev"] = _REFERENCE_KEFF_STD_DEV
    return attrs
