"""CLI for exporting pickled OpenMC MGXS libraries to the HDF5 contract."""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from . import __version__
from .export_openmc_mgxs import export_openmc_mgxs_library


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon-export",
        description=(
            "Export a pickled OpenMC mgxs.Library-like object to the "
            "openmc2donjon HDF5 input contract."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument("library_pickle", help="pickle containing an OpenMC mgxs.Library")
    parser.add_argument("-o", "--output", required=True, help="output HDF5 path")
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="fail if the output HDF5 already exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
