"""Prepare the OpenMC multi-group macro run for the CE/MG SPH colorset.

The script loads the continuous-energy statepoint into the same MGXS library
used by ``export_recipe.py``, asks OpenMC to create an MG-mode model, and
writes a second OpenMC case directory with the same geometry/cell domains.
Run OpenMC in that directory to obtain the MG macro flux used by
``make-openmc-sph-sidecar``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import openmc

from colorset_model import (
    RunSettings,
    build_library,
    build_mg_tallies,
    build_settings,
    load_statepoint,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ce-case-dir",
        type=Path,
        required=True,
        help="directory containing the CE materials/geometry XML files",
    )
    parser.add_argument(
        "--ce-statepoint",
        type=Path,
        required=True,
        help="continuous-energy statepoint used to generate MG macro XS",
    )
    parser.add_argument(
        "--mg-case-dir",
        type=Path,
        required=True,
        help="directory where MG-mode OpenMC XML and mgxs.h5 are written",
    )
    parser.add_argument("--batches", type=int, default=RunSettings.batches)
    parser.add_argument("--inactive", type=int, default=RunSettings.inactive)
    parser.add_argument("--particles", type=int, default=RunSettings.particles)
    parser.add_argument("--seed", type=int, default=RunSettings.seed + 1)
    parser.add_argument(
        "--mgxs-name",
        default="mgxs.h5",
        help="MG cross-section HDF5 filename inside --mg-case-dir",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.ce_statepoint.exists():
        raise SystemExit(f"CE statepoint does not exist: {args.ce_statepoint}")
    if args.batches <= 0 or args.inactive < 0 or args.inactive >= args.batches:
        raise SystemExit("--batches must be positive and greater than --inactive")
    if args.particles <= 0:
        raise SystemExit("--particles must be positive")

    mg_dir = args.mg_case_dir.resolve()
    mg_dir.mkdir(parents=True, exist_ok=True)
    library = build_library(case_dir=args.ce_case_dir)
    load_statepoint(library, args.ce_statepoint)

    mgxs_file, materials, geometry = library.create_mg_mode()
    mgxs_path = (mg_dir / args.mgxs_name).resolve()
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
    tallies = build_mg_tallies()

    materials.export_to_xml(mg_dir / "materials.xml")
    geometry.export_to_xml(mg_dir / "geometry.xml")
    settings.export_to_xml(mg_dir / "settings.xml")
    tallies.export_to_xml(mg_dir / "tallies.xml")
    mgxs_file.export_to_hdf5(mgxs_path)

    print(f"wrote OpenMC MG colorset XML: {mg_dir}")
    print(f"MG cross sections: {mgxs_path}")
    print(f"statepoint target: {mg_dir / f'statepoint.{args.batches}.h5'}")
    print(f"energy_mode: {settings.energy_mode}")
    print(f"materials cross_sections: {materials.cross_sections}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
