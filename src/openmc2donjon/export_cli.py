"""CLI for exporting OpenMC MGXS libraries to the HDF5 contract."""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from . import __version__
from .export_openmc_mgxs import export_openmc_mgxs_library
from .openmc_statepoint import RecipeDryRunSummary, export_openmc_statepoint_recipe
from .openmc_statepoint import dry_run_openmc_statepoint_recipe


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
    parser.add_argument("-o", "--output", help="output HDF5 path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --recipe, inspect domains and metadata without writing HDF5",
    )
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
    if args.dry_run and args.recipe is None:
        parser.error("--dry-run can only be used with --recipe")
    if not args.dry_run and args.output is None:
        parser.error("-o/--output is required unless --dry-run is set")

    if args.recipe is not None:
        if args.dry_run:
            summary = dry_run_openmc_statepoint_recipe(
                args.recipe,
                statepoint_path=args.statepoint,
                load_statepoint=args.statepoint is not None and not args.no_load_statepoint,
                output_path=args.output,
            )
            _print_dry_run_summary(summary)
            return 0
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


def _print_dry_run_summary(summary: RecipeDryRunSummary) -> None:
    print("recipe dry-run OK")
    print(f"  recipe: {summary.recipe_path}")
    if summary.statepoint_path is None:
        print("  statepoint: none")
    else:
        loaded = "loaded" if summary.statepoint_loaded else "not loaded"
        print(f"  statepoint: {summary.statepoint_path} ({loaded})")
    if summary.output_path is None:
        print("  output: dry run; no HDF5 written")
    else:
        print(f"  output: {summary.output_path} (not written)")
    print(f"  energy_groups: {summary.energy_groups}")
    print(f"  legendre_order: {summary.legendre_order}")
    print(f"  domain_type: {summary.domain_type or 'unknown'}")
    print(f"  mgxs_types: {_render_list(summary.mgxs_types)}")
    print(f"  mixtures: {len(summary.domains)}")
    print(f"  root_attrs: {_render_list(summary.root_attr_keys)}")
    if summary.warnings:
        print("  warnings:")
        for warning in summary.warnings:
            print(f"    - {warning}")
    print("  first_mixtures:")
    for index, domain in enumerate(summary.domains[:20], start=1):
        details = [
            f"source={domain.source_label}",
            f"type={domain.source_type}",
            f"volume={domain.volume:g}",
        ]
        if domain.xs_kwargs:
            details.append(f"xs_kwargs={dict(domain.xs_kwargs)}")
        if domain.attr_keys:
            details.append(f"attrs={list(domain.attr_keys)}")
        print(f"    {index:4d} {domain.name} ({', '.join(details)})")
    remaining = len(summary.domains) - 20
    if remaining > 0:
        print(f"    ... {remaining} more mixtures")


def _render_list(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


if __name__ == "__main__":
    raise SystemExit(main())
