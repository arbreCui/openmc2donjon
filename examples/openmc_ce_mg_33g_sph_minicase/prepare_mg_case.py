"""Prepare the OpenMC multi-group macro run for the CE/MG SPH colorset.

The script loads the continuous-energy statepoint into the same MGXS library
used by ``export_recipe.py``, asks OpenMC to create an MG-mode model, and
writes a second OpenMC case directory with the same geometry/cell domains.
Run OpenMC in that directory to obtain the MG macro flux used by
``make-openmc-sph-sidecar``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from colorset_model import (
    MG_MACRO_HISTOGRAM_BINS,
    MG_MACRO_LEGENDRE_ORDER,
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
    parser.add_argument(
        "--sph-source",
        type=Path,
        default=None,
        help=(
            "optional SPH sidecar from the previous CE/MG iteration; when "
            "provided, write a corrected OpenMC-native MGXS file for this MG run"
        ),
    )
    parser.add_argument(
        "--raw-mgxs-name",
        default="mgxs_unapplied.h5",
        help=(
            "raw OpenMC-native MGXS filename used before SPH application "
            "(default: mgxs_unapplied.h5; only used with --sph-source)"
        ),
    )
    parser.add_argument(
        "--sph-apply-summary-json",
        type=Path,
        default=None,
        help="optional JSON summary for the OpenMC-native SPH application",
    )
    parser.add_argument(
        "--scatter-format",
        choices=("histogram", "legendre"),
        default=MG_MACRO_SCATTER_FORMAT,
        help=(
            "scatter-angle treatment for the OpenMC MG macro solve "
            "(default: histogram, i.e. Hn)"
        ),
    )
    parser.add_argument(
        "--histogram-bins",
        type=int,
        default=MG_MACRO_HISTOGRAM_BINS,
        help="number of Hn angular histogram bins when --scatter-format=histogram",
    )
    parser.add_argument(
        "--legendre-order",
        type=int,
        default=MG_MACRO_LEGENDRE_ORDER,
        help="Legendre order when --scatter-format=legendre",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="optional JSON file recording the MG macro scatter treatment",
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
    if args.histogram_bins <= 0:
        raise SystemExit("--histogram-bins must be positive")
    if args.legendre_order < 0:
        raise SystemExit("--legendre-order must be non-negative")
    if args.sph_source is not None and args.raw_mgxs_name == args.mgxs_name:
        raise SystemExit("--raw-mgxs-name must differ from --mgxs-name when --sph-source is used")

    mg_dir = args.mg_case_dir.resolve()
    mg_dir.mkdir(parents=True, exist_ok=True)
    library = build_library(
        case_dir=args.ce_case_dir,
        scatter_format=args.scatter_format,
        histogram_bins=args.histogram_bins,
        legendre_order=args.legendre_order,
    )
    load_statepoint(library, args.ce_statepoint)

    mgxs_file, materials, geometry = library.create_mg_mode()
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
    tallies = build_mg_tallies()

    materials.export_to_xml(mg_dir / "materials.xml")
    geometry.export_to_xml(mg_dir / "geometry.xml")
    settings.export_to_xml(mg_dir / "settings.xml")
    tallies.export_to_xml(mg_dir / "tallies.xml")
    mgxs_file.export_to_hdf5(raw_mgxs_path)
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

    print(f"wrote OpenMC MG colorset XML: {mg_dir}")
    print(f"MG cross sections: {mgxs_path}")
    if sph_apply_report is not None:
        print(f"raw MG cross sections: {raw_mgxs_path}")
        print(f"SPH-applied MGXS source: {args.sph_source}")
    print(f"statepoint target: {mg_dir / f'statepoint.{args.batches}.h5'}")
    print(f"energy_mode: {settings.energy_mode}")
    if args.scatter_format == "histogram":
        print(f"scatter treatment: H{args.histogram_bins}")
    else:
        print(f"scatter treatment: P{args.legendre_order}")
    print(f"materials cross_sections: {materials.cross_sections}")
    if args.summary_json is not None:
        payload = {
            "schema": "openmc2donjon.openmc-ce-mg-sph-mg-macro.v1",
            "scatter_format": args.scatter_format,
            "histogram_bins": args.histogram_bins
            if args.scatter_format == "histogram"
            else None,
            "legendre_order": args.legendre_order
            if args.scatter_format == "legendre"
            else None,
            "mgxs": str(mgxs_path),
            "raw_mgxs": str(raw_mgxs_path) if args.sph_source is not None else None,
            "sph_source": None if args.sph_source is None else str(args.sph_source),
            "sph_applied": args.sph_source is not None,
            "mg_case_dir": str(mg_dir),
        }
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
