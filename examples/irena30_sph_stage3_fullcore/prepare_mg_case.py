"""Prepare the assembly-scale homogenized OpenMC MG full-core Stage 3 run.

Loads the continuous-energy full-core statepoint into the same MGXS library
used by ``export_recipe.py``, asks OpenMC to create the MG-mode model (each
of the 91 hex cells filled with its per-position homogenized macro
material), and writes the complete 91-position MG core case. Optionally
applies an SPH sidecar from the previous iteration to the OpenMC-native MGXS
file — the sidecar carries 91 factor vectors (uniform in the production
global route, or position-dependent in local research mode), matched to the
91 ``setN`` macro materials by order.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ce_core_model import (
    MG_MACRO_HISTOGRAM_BINS,
    MG_MACRO_SCATTER_FORMAT,
    RunSettings,
    build_library,
    build_mg_tallies,
    build_settings,
    load_statepoint,
)
from openmc2donjon.sph_apply import (
    apply_sph_to_openmc_mgxs_hdf5,
    write_summary as write_sph_apply_summary,
)


def blacken_zero_flux_groups(mgxs_path: Path) -> int:
    """Make zero-XS groups purely absorbing in the OpenMC-native MGXS file.

    Zero-flux groups of the fast-spectrum tally leave total == 0 rows in the
    macro library.  A Monte Carlo particle scattered into such a group would
    stream collisionless forever, so give those groups a unit black-absorber
    cross section instead.  No particle population ever reaches them (their
    in-scatter rows are also zero), so the physics is unchanged.
    """
    import h5py
    import numpy as np

    patched = 0
    with h5py.File(mgxs_path, "r+") as h5:
        for _name, xsdata in h5.items():
            if not isinstance(xsdata, h5py.Group):
                continue
            for _temp, tables in xsdata.items():
                if not isinstance(tables, h5py.Group) or "total" not in tables:
                    continue
                total = tables["total"][:]
                zero = np.where(total == 0.0)[0]
                if not len(zero):
                    continue
                total[zero] = 1.0
                tables["total"][...] = total
                absorption = tables["absorption"][:]
                absorption[zero] = 1.0
                tables["absorption"][...] = absorption
                patched += len(zero)
    return patched


def strip_material_cell_translations(geometry) -> int:
    """Remove translations left on cells whose fill became a macro material.

    ``create_mg_mode`` keeps the CE cells' translations, but a translation is
    only meaningful for universe/lattice fills; OpenMC rejects it on a
    material-filled cell.
    """
    stripped = 0
    for cell in geometry.get_all_cells().values():
        if cell.translation is not None and not hasattr(cell.fill, "get_all_cells"):
            # The public setter refuses None; clear the private attribute.
            cell._translation = None
            stripped += 1
    return stripped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ce-case-dir", type=Path, required=True)
    parser.add_argument("--ce-statepoint", type=Path, required=True)
    parser.add_argument("--mg-case-dir", type=Path, required=True)
    parser.add_argument("--batches", type=int, default=RunSettings.batches)
    parser.add_argument("--inactive", type=int, default=RunSettings.inactive)
    parser.add_argument("--particles", type=int, default=RunSettings.particles)
    parser.add_argument("--seed", type=int, default=RunSettings.seed + 1)
    parser.add_argument("--mgxs-name", default="mgxs.h5")
    parser.add_argument("--sph-source", type=Path, default=None)
    parser.add_argument("--raw-mgxs-name", default="mgxs_unapplied.h5")
    parser.add_argument("--sph-apply-summary-json", type=Path, default=None)
    parser.add_argument("--summary-json", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.ce_statepoint.exists():
        raise SystemExit(f"CE statepoint does not exist: {args.ce_statepoint}")
    if args.sph_source is not None and args.raw_mgxs_name == args.mgxs_name:
        raise SystemExit("--raw-mgxs-name must differ from --mgxs-name when --sph-source is used")

    mg_dir = args.mg_case_dir.resolve()
    mg_dir.mkdir(parents=True, exist_ok=True)
    library = build_library(
        case_dir=args.ce_case_dir,
        scatter_format=MG_MACRO_SCATTER_FORMAT,
        histogram_bins=MG_MACRO_HISTOGRAM_BINS,
    )
    load_statepoint(library, args.ce_statepoint)

    mgxs_file, materials, geometry = library.create_mg_mode()
    stripped = strip_material_cell_translations(geometry)
    if stripped:
        print(f"stripped translations from {stripped} macro-filled cells")
    mgxs_path = (mg_dir / args.mgxs_name).resolve()
    raw_mgxs_path = (mg_dir / args.raw_mgxs_name).resolve() if args.sph_source else mgxs_path
    materials.cross_sections = str(mgxs_path)
    settings = build_settings(
        RunSettings(
            batches=args.batches,
            inactive=args.inactive,
            particles=args.particles,
            seed=args.seed,
        ),
        energy_mode="multi-group",
    )
    tallies = build_mg_tallies(geometry)

    materials.export_to_xml(mg_dir / "materials.xml")
    geometry.export_to_xml(mg_dir / "geometry.xml")
    settings.export_to_xml(mg_dir / "settings.xml")
    tallies.export_to_xml(mg_dir / "tallies.xml")
    mgxs_file.export_to_hdf5(str(raw_mgxs_path))
    sph_apply_report = None
    if args.sph_source is not None:
        sph_apply_report = apply_sph_to_openmc_mgxs_hdf5(
            raw_mgxs_path,
            sph_source=args.sph_source,
            output_h5=mgxs_path,
            force=True,
        )
        if args.sph_apply_summary_json is not None:
            write_sph_apply_summary(args.sph_apply_summary_json, sph_apply_report)
    blackened = blacken_zero_flux_groups(mgxs_path)
    if blackened:
        print(f"blackened {blackened} zero-XS (group) bins in {mgxs_path.name}")

    print(f"wrote IRENA SPH Stage 3 MG case: {mg_dir}")
    print(f"MG cross sections: {mgxs_path}")
    print(f"statepoint target: {mg_dir / f'statepoint.{args.batches}.h5'}")
    if args.summary_json is not None:
        payload = {
            "schema": "openmc2donjon.irena30-sph-stage3-mg-macro.v1",
            "scatter_format": MG_MACRO_SCATTER_FORMAT,
            "histogram_bins": MG_MACRO_HISTOGRAM_BINS,
            "mgxs": str(mgxs_path),
            "raw_mgxs": str(raw_mgxs_path) if args.sph_source is not None else None,
            "sph_source": None if args.sph_source is None else str(args.sph_source),
            "sph_applied": args.sph_source is not None,
            "mg_case_dir": str(mg_dir),
        }
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
