"""IRENA-30 91-hex ZREFL case for the openmc2donjon hex benchmark.

This example reuses the strict-91-hex OpenMC-MG geometry maintained in the
IRENA workspace (``geometry_91hex.py``) and adds per-position MGXS tallies:

1. build the 2D ARI ZREFL diagnostic (all CSD inserted, axial reflective,
   radial vacuum) in OpenMC multi-group mode from the IRENA 33-group
   macrolib;
2. tally MGXS on cell domains, one hex cell domain per DONJON mixture
   (91 mixtures, DRAGON HEXZ ring/position order);
3. run OpenMC to produce a statepoint;
4. export that statepoint with ``openmc2donjon-from-openmc``.

The OpenMC k-effective of the same run is the paired reference for the
downstream DONJON solve. Local inputs required (not shipped in this repo):

- ``IRENA30_DIR``      default /Users/wen/openmc-workspace/irena
- ``IRENA30_MACROLIB`` default $IRENA30_DIR/build/macrolib.h5
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import openmc
import openmc.mgxs as mgxs

CASE_NAME = "irena30_zrefl_hex"
DOMAIN_MODE = "hex_cell"
DOMAIN_TYPE = "cell"
LEGENDRE_ORDER = 1
ENERGY_GROUP_STRUCTURE = "IRENA30-MG33"
AXIAL_HEIGHT_CM = 10.0

MGXS_TYPES = [
    "total",
    "absorption",
    "fission",
    "nu-fission",
    "chi",
    "scatter matrix",
    "transport",
]

_CORE_CELL_RE = re.compile(r"^r(\d+)p(\d+)_L00_(INT|EXT|CSD|DSDF|PNL)$")


@dataclass(frozen=True)
class RunSettings:
    batches: int = 130
    inactive: int = 30
    particles: int = 50_000
    seed: int = 47


def default_irena_dir() -> Path:
    return Path(os.environ.get("IRENA30_DIR", "/Users/wen/openmc-workspace/irena")).resolve()


def default_macrolib() -> Path:
    default = default_irena_dir() / "build" / "macrolib.h5"
    return Path(os.environ.get("IRENA30_MACROLIB", default)).resolve()


def default_case_dir() -> Path:
    return Path(os.environ.get("OPENMC2DONJON_IRENA_ZREFL_DIR", Path(__file__).parent)).resolve()


def _load_geometry_module(irena_dir: Path):
    path = irena_dir / "geometry_91hex.py"
    spec = importlib.util.spec_from_file_location("_openmc2donjon_irena_geometry", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import IRENA geometry module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def hex_cell_volume_cm3(pitch_cm: float) -> float:
    return math.sqrt(3.0) / 2.0 * pitch_cm**2 * AXIAL_HEIGHT_CM


def core_cells(geometry: openmc.Geometry) -> list[tuple[int, int, str, openmc.Cell]]:
    """Return the 91 layer-0 hex cells as (ring, pos, label, cell), sorted in
    DRAGON HEXZ ring/position order (the order used by ``geometry_91hex``)."""
    entries: list[tuple[int, int, str, openmc.Cell]] = []
    for cell in geometry.get_all_cells().values():
        match = _CORE_CELL_RE.match(cell.name or "")
        if match:
            entries.append((int(match.group(1)), int(match.group(2)), match.group(3), cell))
    entries.sort(key=lambda item: (item[0], item[1]))
    if len(entries) != 91:
        raise RuntimeError(f"expected 91 hex cells, found {len(entries)}")
    return entries


def domain_name(ring: int, pos: int, label: str) -> str:
    return f"R{ring}P{pos:02d}_{label}"


def _energy_groups_from_macrolib(macrolib_path: Path) -> mgxs.EnergyGroups:
    import h5py

    with h5py.File(macrolib_path, "r") as h5:
        bounds = np.asarray(h5.attrs["group structure"], dtype=float)
    return mgxs.EnergyGroups(bounds)


def build_model(
    run_settings: RunSettings | None = None,
    *,
    macrolib_path: Path | None = None,
    irena_dir: Path | None = None,
) -> openmc.Model:
    run_settings = run_settings or RunSettings()
    irena_dir = Path(irena_dir or default_irena_dir())
    macrolib_path = Path(macrolib_path or default_macrolib())
    geometry_module = _load_geometry_module(irena_dir)

    geometry, materials = geometry_module.build_geometry(
        macrolib_path,
        rod_depth_cm=AXIAL_HEIGHT_CM,
        n_axial_layers=1,
        axial_height_cm=AXIAL_HEIGHT_CM,
        axial_bc="reflective",
    )
    pitch_cm = float(geometry_module.PITCH_CM)
    volume = hex_cell_volume_cm3(pitch_cm)
    for _ring, _pos, _label, cell in core_cells(geometry):
        cell.volume = volume

    material_list = openmc.Materials(list(materials.values()))
    material_list.cross_sections = str(macrolib_path)

    settings = openmc.Settings()
    settings.energy_mode = "multi-group"
    settings.run_mode = "eigenvalue"
    settings.batches = run_settings.batches
    settings.inactive = run_settings.inactive
    settings.particles = run_settings.particles
    settings.seed = run_settings.seed
    settings.output = {"tallies": False}
    settings.statepoint = {"batches": [run_settings.batches]}
    source = openmc.IndependentSource()
    source.space = openmc.stats.Box(
        lower_left=(-50.0, -50.0, 0.5),
        upper_right=(50.0, 50.0, AXIAL_HEIGHT_CM - 0.5),
        only_fissionable=True,
    )
    source.angle = openmc.stats.Isotropic()
    settings.source = source

    return openmc.Model(geometry=geometry, materials=material_list, settings=settings)


def build_library(
    geometry: openmc.Geometry | None = None,
    *,
    case_dir: Path | None = None,
    macrolib_path: Path | None = None,
) -> mgxs.Library:
    macrolib_path = Path(macrolib_path or default_macrolib())
    if geometry is None:
        case_dir = Path(case_dir or default_case_dir()).resolve()
        materials = openmc.Materials.from_xml(str(case_dir / "materials.xml"))
        geometry = openmc.Geometry.from_xml(str(case_dir / "geometry.xml"), materials=materials)

    pitch_volume = None
    library = mgxs.Library(geometry)
    library.energy_groups = _energy_groups_from_macrolib(macrolib_path)
    library.mgxs_types = MGXS_TYPES
    library.domain_type = DOMAIN_TYPE
    domains = []
    for _ring, _pos, _label, cell in core_cells(geometry):
        if cell.volume is None:
            if pitch_volume is None:
                pitch_volume = hex_cell_volume_cm3(17.5)
            cell.volume = pitch_volume
        domains.append(cell)
    library.domains = domains
    library.by_nuclide = False
    library.legendre_order = LEGENDRE_ORDER
    library.build_library()
    return library


def domain_names(library: mgxs.Library) -> dict[int, str]:
    names: dict[int, str] = {}
    for domain in library.domains:
        match = _CORE_CELL_RE.match(domain.name or "")
        if not match:
            raise RuntimeError(f"unexpected domain cell name: {domain.name!r}")
        names[int(domain.id)] = domain_name(int(match.group(1)), int(match.group(2)), match.group(3))
    return names


def load_statepoint(library: mgxs.Library, statepoint_path: Path) -> None:
    with openmc.StatePoint(str(statepoint_path)) as statepoint:
        library.load_from_statepoint(statepoint)
        keff = getattr(statepoint, "keff", None)
        if keff is not None:
            print(f"IRENA-30 ZREFL OpenMC keff = {keff}")


def root_attrs() -> dict[str, object]:
    return {
        "case": CASE_NAME,
        "domain_mode": DOMAIN_MODE,
        "domain_type": DOMAIN_TYPE,
        "energy_group_structure": ENERGY_GROUP_STRUCTURE,
        "legendre_order": LEGENDRE_ORDER,
        "geometry_kind": "hexagonal",
        "spatial_mapping": "one OpenMC hex cell domain -> one DONJON mixture",
        "hex_pitch_cm": 17.5,
        "hex_axial_height_cm": AXIAL_HEIGHT_CM,
        "boundary_conditions": "radial vacuum, axial reflective (2D ARI ZREFL)",
    }


def export_openmc_xml(case_dir: Path, run_settings: RunSettings | None = None) -> None:
    case_dir = Path(case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    model = build_model(run_settings)
    library = build_library(model.geometry)
    tallies = openmc.Tallies()
    if hasattr(library, "add_to_tallies"):
        library.add_to_tallies(tallies, merge=True)
    else:
        library.add_to_tallies_file(tallies, merge=True)
    model.materials.export_to_xml(case_dir / "materials.xml")
    model.geometry.export_to_xml(case_dir / "geometry.xml")
    model.settings.export_to_xml(case_dir / "settings.xml")
    tallies.export_to_xml(case_dir / "tallies.xml")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--particles", type=int, default=RunSettings.particles)
    parser.add_argument("--batches", type=int, default=RunSettings.batches)
    parser.add_argument("--inactive", type=int, default=RunSettings.inactive)
    parser.add_argument("--seed", type=int, default=RunSettings.seed)
    args = parser.parse_args()
    export_openmc_xml(
        args.case_dir,
        RunSettings(
            batches=args.batches,
            inactive=args.inactive,
            particles=args.particles,
            seed=args.seed,
        ),
    )
    print(f"wrote OpenMC XML case to {args.case_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
