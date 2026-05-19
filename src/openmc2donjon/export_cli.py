"""CLI for exporting OpenMC MGXS libraries to the HDF5 contract."""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from . import __version__
from .export_openmc_mgxs import export_openmc_mgxs_library
from .openmc_statepoint import export_openmc_statepoint_recipe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon-export",
        description=(
            "Export an OpenMC mgxs.Library-like object to the openmc2donjon "
            "HDF5 input contract. Use either a pickled library or a Python "
            "recipe plus statepoint."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "library_pickle",
        nargs="?",
        help="pickle containing an already-loaded OpenMC mgxs.Library-like object",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        help="Python recipe defining build_library() for an OpenMC statepoint export",
    )
    parser.add_argument(
        "--statepoint",
        type=Path,
        help="OpenMC statepoint used with --recipe",
    )
    parser.add_argument(
        "--no-load-statepoint",
        action="store_true",
        help="with --recipe, export the library without loading a statepoint first",
    )
    parser.add_argument("-o", "--output", required=True, help="output HDF5 path")
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="fail if the output HDF5 already exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.recipe) == bool(args.library_pickle):
        parser.error("provide exactly one input: library_pickle or --recipe")
    if args.statepoint is not None and args.recipe is None:
        parser.error("--statepoint can only be used with --recipe")
    if args.no_load_statepoint and args.recipe is None:
        parser.error("--no-load-statepoint can only be used with --recipe")

    if args.recipe is not None:
        if args.statepoint is None and not args.no_load_statepoint:
            parser.error("--recipe requires --statepoint unless --no-load-statepoint is set")
        recipe_summary = export_openmc_statepoint_recipe(
            args.recipe,
            args.output,
            statepoint_path=args.statepoint,
            load_statepoint=not args.no_load_statepoint,
            overwrite=not args.no_overwrite,
        )
        summary = recipe_summary.output
        print(
            f"exported {len(summary.domains)} domains, "
            f"{summary.energy_groups} groups, P{summary.legendre_order} "
            f"from recipe {recipe_summary.recipe_path} to {summary.output_path}"
        )
        return 0

    with Path(args.library_pickle).open("rb") as fh:
        library = pickle.load(fh)
    summary = export_openmc_mgxs_library(
        library,
        args.output,
        overwrite=not args.no_overwrite,
    )
    print(
        f"exported {len(summary.domains)} domains, "
        f"{summary.energy_groups} groups, P{summary.legendre_order} "
        f"to {summary.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
