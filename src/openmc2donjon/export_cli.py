"""CLI for exporting OpenMC MGXS libraries to the HDF5 contract."""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from . import __version__
from ._logging import add_cli_logging_arguments, configure_cli_logging_from_args, get_logger
from .export_openmc_mgxs import export_openmc_mgxs_library
from .openmc_statepoint import (
    StatepointLoadError,
    dry_run_openmc_statepoint_recipe,
    export_openmc_tallies_recipe,
    export_openmc_statepoint_recipe,
)
from .recipe_dry_run_report import (
    print_recipe_dry_run_summary,
    print_strict_dry_run_decision,
)


logger = get_logger("export_cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon-export",
        description=(
            "Export an OpenMC mgxs.Library-like object to the openmc2donjon "
            "HDF5 input contract, or write OpenMC tallies.xml from a Python "
            "recipe before running OpenMC."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    add_cli_logging_arguments(parser)
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
    parser.add_argument(
        "--write-tallies",
        type=Path,
        metavar="PATH",
        help=(
            "with --recipe, write OpenMC tallies.xml from the recipe MGXS library "
            "instead of exporting HDF5"
        ),
    )
    parser.add_argument(
        "--no-merge-tallies",
        action="store_true",
        help="with --write-tallies, pass merge=False when adding MGXS tallies",
    )
    parser.add_argument("-o", "--output", help="output HDF5 path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --recipe, inspect domains and metadata without writing HDF5",
    )
    parser.add_argument(
        "--strict-dry-run",
        action="store_true",
        help=(
            "with --dry-run, return non-zero if any production checklist item "
            "warns/fails or if recipe warnings are emitted"
        ),
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="fail if the output HDF5 already exists",
    )
    parser.add_argument(
        "--scatter-mgxs-type",
        default=None,
        help=(
            "explicit OpenMC MGXS type to export as DONJON scattering. "
            "Default accepts only ordinary 'scatter matrix'."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_cli_logging_from_args(args)
    if bool(args.recipe) == bool(args.library_pickle):
        parser.error("provide exactly one input: library_pickle or --recipe")
    if args.statepoint is not None and args.recipe is None:
        parser.error("--statepoint can only be used with --recipe")
    if args.no_load_statepoint and args.recipe is None:
        parser.error("--no-load-statepoint can only be used with --recipe")
    if args.write_tallies is not None and args.recipe is None:
        parser.error("--write-tallies can only be used with --recipe")
    if args.write_tallies is not None and args.dry_run:
        parser.error("--write-tallies cannot be combined with --dry-run")
    if args.no_merge_tallies and args.write_tallies is None:
        parser.error("--no-merge-tallies requires --write-tallies")
    if args.dry_run and args.recipe is None:
        parser.error("--dry-run can only be used with --recipe")
    if args.strict_dry_run and not args.dry_run:
        parser.error("--strict-dry-run requires --dry-run")
    if not args.dry_run and args.write_tallies is None and args.output is None:
        parser.error("-o/--output is required unless --dry-run is set")

    try:
        if args.recipe is not None:
            if args.write_tallies is not None:
                summary = export_openmc_tallies_recipe(
                    args.recipe,
                    args.write_tallies,
                    merge=not args.no_merge_tallies,
                    overwrite=not args.no_overwrite,
                )
                tally_count = (
                    "unknown" if summary.tally_count is None else str(summary.tally_count)
                )
                print(
                    f"wrote OpenMC tallies from recipe {summary.recipe_path} "
                    f"to {summary.output_path}"
                )
                print(
                    f"  tallies: {tally_count} "
                    f"extra_tallies={summary.extra_tally_count} "
                    f"merge={str(summary.merged).lower()}"
                )
                return 0
            if args.dry_run:
                summary = dry_run_openmc_statepoint_recipe(
                    args.recipe,
                    statepoint_path=args.statepoint,
                    load_statepoint=args.statepoint is not None and not args.no_load_statepoint,
                    output_path=args.output,
                    scatter_mgxs_type=args.scatter_mgxs_type,
                )
                print_recipe_dry_run_summary(summary)
                if args.strict_dry_run:
                    return 0 if print_strict_dry_run_decision(summary) else 1
                return 0
            if args.statepoint is None and not args.no_load_statepoint:
                parser.error("--recipe requires --statepoint unless --no-load-statepoint is set")
            recipe_summary = export_openmc_statepoint_recipe(
                args.recipe,
                args.output,
                statepoint_path=args.statepoint,
                load_statepoint=not args.no_load_statepoint,
                scatter_mgxs_type=args.scatter_mgxs_type,
                overwrite=not args.no_overwrite,
            )
            summary = recipe_summary.output
            print(
                f"exported {len(summary.domains)} domains, "
                f"{summary.energy_groups} groups, P{summary.legendre_order} "
                f"from recipe {recipe_summary.recipe_path} to {summary.output_path} "
                f"(std_dev {summary.std_dev_dataset_count}/"
                f"{summary.std_dev_expected_dataset_count})"
            )
            capabilities = recipe_summary.provenance.get("capabilities", {})
            print(
                "  OpenMC provenance: "
                f"{recipe_summary.provenance.get('status', 'incomplete')} "
                f"reference_bound={str(bool(capabilities.get('reference_bound'))).lower()} "
                "transport_reproducible="
                f"{str(bool(capabilities.get('transport_reproducible'))).lower()} "
                f"sha256={str(recipe_summary.provenance.get('digest_sha256'))[:12]}"
            )
            return 0
    except StatepointLoadError as exc:
        logger.error("%s: error: %s", parser.prog, exc)
        return 1

    with Path(args.library_pickle).open("rb") as fh:
        library = pickle.load(fh)
    summary = export_openmc_mgxs_library(
        library,
        args.output,
        scatter_mgxs_type=args.scatter_mgxs_type,
        overwrite=not args.no_overwrite,
    )
    print(
        f"exported {len(summary.domains)} domains, "
        f"{summary.energy_groups} groups, P{summary.legendre_order} "
        f"to {summary.output_path} "
        f"(std_dev {summary.std_dev_dataset_count}/{summary.std_dev_expected_dataset_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
