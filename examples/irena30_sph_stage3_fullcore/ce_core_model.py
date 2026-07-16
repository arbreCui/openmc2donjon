"""IRENA-30 91-hex full-core CE/MG model for OpenMC-side SPH (Stage 3).

Three-model SPH route, full-core stage: the complete 91-position IRENA-30
core (2D ARI ZREFL slab) built in continuous energy from the IRENA
workspace's colorset CE building blocks, homogenized per hex position.

1. CE fine model    : explicit-91-hex geometry (shared segment planes per
                      the ``openmc_explicit7_probe`` technique, vacuum on
                      the 66 outer faces, 10 cm axial slab with reflective
                      z) whose 91 top-level hex cells are filled with the
                      ``openmc_colorset`` CE assembly universes (INT/EXT/
                      CSD/DSDF/PNL).  Those 91 cells are the MGXS cell
                      domains directly — same names, positions and order
                      as the accepted MG benchmark
                      (``examples/irena30_zrefl_hex``).
2. MG full core     : ``mgxs.Library.create_mg_mode()`` -> the complete
   (homogenized)      91-position core, with each top-level position replaced
                      by one homogeneous hex node and the same boundaries
                      (= the DONJON full-core layout).
3. DONJON consumer  : HEXZ 91 SIDE 10.1036 NCR + SNT SN8 against the CE
                      truth k.

Geometry adaptation (documented in README.md): the colorset assembly
envelope edge is ~9.995 cm while the core hex cell edge is 10.1036 cm
(DRAGON SIDE, pitch 17.5 cm); the margin is filled with sodium by the
assembly universes' ``*_lattice_cell_catchall`` cells.

Local inputs (not shipped):

- ``IRENA_CE_COMPARE_DIR``: required path to the external ``ce_compare``
  input directory.
- ``IRENA30_DIR``: required path to the external IRENA workspace providing
  ``geometry_91hex.py``, the authoritative 91-hex ring/position layout.
- CE nuclear data via ``OPENMC_CROSS_SECTIONS``.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import openmc
import openmc.mgxs as mgxs

from openmc2donjon.energy_groups import load_energy_mesh

CASE_NAME = "irena30_sph_stage3_fullcore"
DOMAIN_MODE = "hex_cell"
DOMAIN_TYPE = "cell"
N_HEXES = 91
N_BOUNDARY_FACES = 66
ENERGY_MESH_ID = "ecco_33"
ENERGY_GROUP_STRUCTURE = "ECCO-33"
HANDOFF_SCATTER_FORMAT = "legendre"
HANDOFF_LEGENDRE_ORDER = 1
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
VOLUME_FLUX_TALLY_NAME = "irena30_sph_stage3_volume_flux"
AXIAL_HEIGHT_CM = 10.0

_CORE_CELL_RE = re.compile(r"^r(\d+)p(\d+)_L00_(INT|EXT|CSD|DSDF|PNL)$")


@dataclass(frozen=True)
class RunSettings:
    batches: int = 130
    inactive: int = 30
    particles: int = 50_000
    seed: int = 47


def _required_env_path(name: str, purpose: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must point to {purpose}")
    return Path(value).expanduser().resolve()


def default_ce_compare_dir() -> Path:
    return _required_env_path(
        "IRENA_CE_COMPARE_DIR",
        "the external IRENA ce_compare input directory",
    )


def default_irena_dir() -> Path:
    return _required_env_path(
        "IRENA30_DIR",
        "the external IRENA workspace containing geometry_91hex.py",
    )


def default_case_dir() -> Path:
    return Path(
        os.environ.get("OPENMC2DONJON_IRENA_SPH3_DIR", Path(__file__).parent)
    ).expanduser().resolve()


def _load_ce_compare_modules():
    """Import the colorset infrastructure with its own cross-imports intact."""
    root = default_ce_compare_dir()
    if not (root / "openmc_colorset.py").is_file():
        raise FileNotFoundError(f"IRENA ce_compare directory not found: {root}")
    inserted = str(root) not in sys.path
    if inserted:
        sys.path.insert(0, str(root))
    try:
        colorset_common = importlib.import_module("colorset_common")
        openmc_colorset = importlib.import_module("openmc_colorset")
    finally:
        if inserted:
            sys.path.remove(str(root))
    return colorset_common, openmc_colorset


def _load_geometry_module():
    """Import the IRENA workspace 91-hex layout module (layout authority)."""
    path = default_irena_dir() / "geometry_91hex.py"
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_geometry91", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA geometry module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def hex_cell_volume_cm3(pitch_cm: float) -> float:
    return math.sqrt(3.0) / 2.0 * pitch_cm**2 * AXIAL_HEIGHT_CM


def core_layout() -> tuple[float, list[tuple[int, int, float, float, str]]]:
    """Return (pitch_cm, [(ring, pos, x, y, label), ...]) in (ring, pos) order.

    Layout comes verbatim from ``geometry_91hex`` (28 INT + 3 DSDF ring 1 +
    6 CSD ring 3 pos 0,3,6,9,12,15 + 24 EXT + 30 PNL), the same source the
    accepted MG benchmark uses, so positions/labels/order are identical.
    """
    g91 = _load_geometry_module()
    pitch = float(g91.PITCH_CM)
    entries: list[tuple[int, int, float, float, str]] = []
    for ring in range(g91.N_RINGS):
        for pos, (x_c, y_c) in enumerate(g91._hex_centers_yorient(ring, pitch)):
            label = g91.RING_MIX_PATTERN[ring][pos]
            entries.append((ring, pos, x_c, y_c, label))
    if len(entries) != N_HEXES:
        raise RuntimeError(f"expected {N_HEXES} hex positions, found {len(entries)}")
    return pitch, entries


def _hex_vertices(edge: float, center: tuple[float, float]) -> list[tuple[float, float]]:
    """Flat-top hexagon vertices, CCW; same orientation as geometry_91hex
    (face normals at 30 + 60k degrees) and the colorset assembly prisms."""
    cx, cy = center
    apothem = edge * math.sqrt(3.0) / 2.0
    return [
        (cx + edge, cy),
        (cx + 0.5 * edge, cy + apothem),
        (cx - 0.5 * edge, cy + apothem),
        (cx - edge, cy),
        (cx - 0.5 * edge, cy - apothem),
        (cx + 0.5 * edge, cy - apothem),
    ]


def _edge_key(p1: tuple[float, float], p2: tuple[float, float]):
    q1 = (round(p1[0], 6), round(p1[1], 6))
    q2 = (round(p2[0], 6), round(p2[1], 6))
    return tuple(sorted((q1, q2)))


def build_core_geometry(mats: dict[str, openmc.Material]) -> openmc.Geometry:
    """Explicit-91-hex CE core geometry.

    Planes are shared per SEGMENT (vertex pair), the openmc_explicit7_probe
    technique: interior faces get one transmission plane referenced by both
    neighbours, outer faces get a vacuum plane referenced only by their own
    hex.  Sharing by infinite line would be wrong here — outer (vacuum)
    faces are co-linear with interior faces of hexes deeper in the array
    (see the geometry_91hex module docstring).
    """
    _colorset_common, openmc_colorset = _load_ce_compare_modules()
    universes = openmc_colorset.make_assembly_universes(mats)

    pitch, entries = core_layout()
    edge = pitch / math.sqrt(3.0)
    vertices_by_hex = [_hex_vertices(edge, (x_c, y_c)) for _r, _p, x_c, y_c, _l in entries]

    edge_count: dict[tuple, int] = {}
    for vertices in vertices_by_hex:
        for p1, p2 in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            key = _edge_key(p1, p2)
            edge_count[key] = edge_count.get(key, 0) + 1

    n_boundary = sum(1 for count in edge_count.values() if count == 1)
    if n_boundary != N_BOUNDARY_FACES:
        raise RuntimeError(
            f"explicit-91-hex: expected {N_BOUNDARY_FACES} boundary faces, got {n_boundary}; "
            "segment sharing / vertex rounding is broken"
        )

    surfaces: dict[tuple, openmc.Plane] = {}
    for vertices in vertices_by_hex:
        for p1, p2 in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            key = _edge_key(p1, p2)
            if key in surfaces:
                continue
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            a, b = dy, -dx
            d = a * p1[0] + b * p1[1]
            bc = "vacuum" if edge_count[key] == 1 else "transmission"
            surfaces[key] = openmc.Plane(a=a, b=b, d=d, boundary_type=bc)

    z_lo = openmc.ZPlane(z0=0.0, boundary_type="reflective")
    z_hi = openmc.ZPlane(z0=AXIAL_HEIGHT_CM, boundary_type="reflective")

    volume = hex_cell_volume_cm3(pitch)
    cells: list[openmc.Cell] = []
    for (ring, pos, x_c, y_c, label), vertices in zip(
        entries, vertices_by_hex, strict=True
    ):
        region = +z_lo & -z_hi
        for p1, p2 in zip(vertices, vertices[1:] + vertices[:1], strict=True):
            surface = surfaces[_edge_key(p1, p2)]
            value = surface.a * x_c + surface.b * y_c - surface.d
            region &= -surface if value < 0.0 else +surface
        cell = openmc.Cell(
            name=f"r{ring}p{pos}_L00_{label}",
            fill=universes[label],
            region=region,
        )
        cell.translation = (x_c, y_c, 0.0)
        cell.volume = volume
        cells.append(cell)
    return openmc.Geometry(cells)


def build_model_parts() -> tuple[openmc.Materials, openmc.Geometry]:
    _colorset_common, openmc_colorset = _load_ce_compare_modules()
    materials, mats = openmc_colorset.make_materials()
    geometry = build_core_geometry(mats)
    return materials, geometry


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
    settings.source = openmc.IndependentSource(
        space=openmc.stats.Box(
            (-50.0, -50.0, 0.5),
            (50.0, 50.0, AXIAL_HEIGHT_CM - 0.5),
        ),
        angle=openmc.stats.Isotropic(),
        energy=openmc.stats.Watt(),
        constraints={"fissionable": True},
    )
    if energy_mode == "continuous-energy":
        settings.temperature = {"method": "interpolation", "tolerance": 1000}
    return settings


def energy_bounds_ev() -> list[float]:
    return load_energy_mesh(ENERGY_MESH_ID).boundaries_descending[::-1].tolist()


def core_cells(geometry: openmc.Geometry) -> list[tuple[int, int, str, openmc.Cell]]:
    """Return the 91 hex cells as (ring, pos, label, cell), sorted in DRAGON
    HEXZ ring/position order (the accepted benchmark's domain order)."""
    entries: list[tuple[int, int, str, openmc.Cell]] = []
    for cell in geometry.get_all_cells().values():
        match = _CORE_CELL_RE.match(cell.name or "")
        if match:
            entries.append((int(match.group(1)), int(match.group(2)), match.group(3), cell))
    entries.sort(key=lambda item: (item[0], item[1]))
    if len(entries) != N_HEXES:
        raise RuntimeError(f"expected {N_HEXES} hex cells, found {len(entries)}")
    return entries


def domain_name(ring: int, pos: int, label: str) -> str:
    return f"R{ring}P{pos:02d}_{label}"


def selected_domains(geometry: openmc.Geometry) -> list[openmc.Cell]:
    entries = core_cells(geometry)
    cells = [cell for _ring, _pos, _label, cell in entries]
    volume = hex_cell_volume_cm3(17.5)
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
    cell_ids = [int(cell.id) for _ring, _pos, _label, cell in core_cells(geometry)]
    tally = openmc.Tally(name=VOLUME_FLUX_TALLY_NAME)
    tally.filters = [
        openmc.CellFilter(cell_ids, filter_id=9_301),
        openmc.EnergyFilter(energy_bounds_ev(), filter_id=9_302),
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
    materials, geometry = build_model_parts()
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
            print(f"IRENA SPH stage3 (fullcore CE) keff = {keff}")


def domain_names(library: mgxs.Library) -> dict[int, str]:
    names: dict[int, str] = {}
    for domain in library.domains:
        match = _CORE_CELL_RE.match(domain.name or "")
        if not match:
            raise RuntimeError(f"unexpected domain cell name: {domain.name!r}")
        names[int(domain.id)] = domain_name(int(match.group(1)), int(match.group(2)), match.group(3))
    return names


def extract_keff(statepoint_path: Path) -> tuple[float, float]:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        return float(statepoint.keff.nominal_value), float(statepoint.keff.std_dev)


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "output_region_count": N_HEXES,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "energy_group_count": len(energy_bounds_ev()) - 1,
        "legendre_order": HANDOFF_LEGENDRE_ORDER,
        "handoff_scatter_format": HANDOFF_SCATTER_FORMAT,
        "mg_macro_scatter_format": MG_MACRO_SCATTER_FORMAT,
        "mg_macro_histogram_bins": MG_MACRO_HISTOGRAM_BINS,
        "geometry_kind": "hexagonal",
        "hex_pitch_cm": 17.5,
        "hex_axial_height_cm": AXIAL_HEIGHT_CM,
        "boundary_conditions": "radial vacuum, axial reflective (2D ARI ZREFL)",
        "spatial_mapping": "one CE top-level core-position cell -> one SPH/DONJON mixture (91 positions)",
        "sph_route": (
            "OpenMC CE fine full core + OpenMC MG assembly-homogenized "
            "full core (create_mg_mode), same boundaries"
        ),
    }


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--particles", type=int, default=_env_int("IRENA_PARTICLES", RunSettings.particles))
    parser.add_argument("--batches", type=int, default=_env_int("IRENA_BATCHES", RunSettings.batches))
    parser.add_argument("--inactive", type=int, default=_env_int("IRENA_INACTIVE", RunSettings.inactive))
    parser.add_argument("--seed", type=int, default=_env_int("IRENA_SEED", RunSettings.seed))
    args = parser.parse_args(argv)
    export_ce_xml(
        args.case_dir,
        RunSettings(
            batches=args.batches,
            inactive=args.inactive,
            particles=args.particles,
            seed=args.seed,
        ),
    )
    print(f"wrote IRENA SPH Stage 3 full-core CE case: {args.case_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
