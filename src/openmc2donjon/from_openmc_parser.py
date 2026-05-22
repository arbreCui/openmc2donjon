"""Argument parser for the one-step OpenMC-to-DONJON CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .multicompo import DEFAULT_ROOT_NAME
from .openmc_surface_flux import DEFAULT_TALLY_NAME as DEFAULT_SURFACE_FLUX_TALLY_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon-from-openmc",
        description=(
            "Export an OpenMC MGXS recipe/statepoint to the HDF5 handoff and "
            "immediately convert it to DONJON ASCII."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        required=True,
        help="Python recipe defining build_library() for an OpenMC statepoint export",
    )
    parser.add_argument(
        "--statepoint",
        type=Path,
        help="OpenMC statepoint consumed by the recipe",
    )
    parser.add_argument(
        "--no-load-statepoint",
        action="store_true",
        help="export the recipe library without loading a statepoint first",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect the recipe and one-step conversion plan without writing files",
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
        "--format",
        choices=("multicompo", "macrolib"),
        default="multicompo",
        help="output object format (default: multicompo)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "output ASCII path (default: out.mcompo.txt for multicompo, "
            "out.macrolib.txt for macrolib)"
        ),
    )
    parser.add_argument(
        "--keep-hdf5",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the intermediate MGXS HDF5 to PATH instead of a temporary file",
    )
    parser.add_argument(
        "--scatter-mgxs-type",
        default=None,
        help=(
            "explicit OpenMC MGXS type to export as DONJON scattering. "
            "Default accepts only ordinary 'scatter matrix'."
        ),
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=(
            "write a standard production run directory with mgxs_library.h5, "
            "DONJON ASCII output, summary JSON, manifest.json, and bundle validation"
        ),
    )
    parser.add_argument(
        "--no-validate-bundle",
        action="store_true",
        help="with --run-dir, skip automatic manifest-backed bundle validation",
    )
    parser.add_argument(
        "--bundle-validation-summary-json",
        type=Path,
        default=None,
        help="with --run-dir, write bundle validation summary JSON here",
    )
    parser.add_argument(
        "--handoff-summary-json",
        type=Path,
        default=None,
        help="with --run-dir, write final handoff decision summary JSON here",
    )
    parser.add_argument(
        "--no-handoff-summary",
        action="store_true",
        help="with --run-dir, skip the final handoff decision summary JSON",
    )
    parser.add_argument(
        "--root-name",
        default=DEFAULT_ROOT_NAME,
        help=f"top-level LCM directory name for MULTICOMPO output (default: {DEFAULT_ROOT_NAME})",
    )
    parser.add_argument(
        "--comment",
        default=None,
        help="COMMENT block text for MULTICOMPO output",
    )
    parser.add_argument(
        "--burnup",
        type=float,
        default=None,
        help="write a single-point BURN parameter axis with this value",
    )
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help="write this constant H-FACTOR when the exported HDF5 does not provide one",
    )
    parser.add_argument(
        "--adf-source",
        type=Path,
        default=None,
        help="HDF5 sidecar containing computed ADF/DF values to inject before conversion",
    )
    parser.add_argument(
        "--adf-faces",
        default=None,
        help="comma-separated expected ADF face names in --adf-source",
    )
    parser.add_argument(
        "--adf-kind",
        default=None,
        help="override root adf_kind provenance attribute when injecting --adf-source",
    )
    parser.add_argument(
        "--adf-real",
        choices=("true", "false"),
        default=None,
        help="override root adf_real provenance attribute when injecting --adf-source",
    )
    parser.add_argument(
        "--adf-source-label",
        default=None,
        help="override root adf_source provenance attribute when injecting --adf-source",
    )
    parser.add_argument(
        "--sph-source",
        type=Path,
        default=None,
        help="HDF5 sidecar containing SPH/NSPH factors to inject before conversion",
    )
    parser.add_argument(
        "--sph-macrolib",
        type=Path,
        default=None,
        help=(
            "L_MACROLIB ASCII source containing GROUP/*/NSPH; with --run-dir, "
            "a canonical sph_sidecar.h5 is built and injected"
        ),
    )
    parser.add_argument(
        "--sph-kind",
        default=None,
        help="override root sph_kind provenance attribute when injecting SPH",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default=None,
        help="override root sph_real provenance attribute when injecting SPH",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default=None,
        help="override root sph_applied provenance attribute when injecting SPH",
    )
    parser.add_argument(
        "--sph-source-label",
        default=None,
        help="override root sph_source provenance attribute when injecting SPH",
    )
    parser.add_argument(
        "--build-flux-ratio-adf",
        action="store_true",
        help=(
            "inside --run-dir, build a flux-ratio ADF sidecar from heterogeneous "
            "surface flux and a low-order driver, inject it, and bundle all side artifacts"
        ),
    )
    parser.add_argument(
        "--adf-surface-flux",
        type=Path,
        default=None,
        help=(
            "with --build-flux-ratio-adf, existing heterogeneous face-flux HDF5 "
            "or FILE::DATASET; omit when using --export-surface-flux"
        ),
    )
    parser.add_argument(
        "--export-surface-flux",
        action="store_true",
        help=(
            "with --build-flux-ratio-adf, export heterogeneous face flux from "
            "the OpenMC statepoint before building the ADF sidecar"
        ),
    )
    parser.add_argument(
        "--surface-flux-tally-name",
        default=DEFAULT_SURFACE_FLUX_TALLY_NAME,
        help=(
            "with --export-surface-flux, OpenMC tally name "
            f"(default: {DEFAULT_SURFACE_FLUX_TALLY_NAME})"
        ),
    )
    parser.add_argument(
        "--surface-flux-mesh-shape",
        default=None,
        help="with --export-surface-flux, mesh shape as Y,X; defaults to 1,N",
    )
    parser.add_argument(
        "--surface-flux-mu-edges",
        default=None,
        help="with --export-surface-flux, comma-separated MuSurfaceFilter bin edges",
    )
    parser.add_argument(
        "--surface-flux-face-area",
        type=float,
        default=1.0,
        help="with --export-surface-flux, face area used in current-to-flux reconstruction",
    )
    parser.add_argument(
        "--low-order-raw-driver",
        default=None,
        help=(
            "with --build-flux-ratio-adf, raw low-order driver HDF5 bundle; "
            "omitted low-order flux/current datasets are auto-detected in this file"
        ),
    )
    parser.add_argument(
        "--homogeneous-face-flux",
        default=None,
        help=(
            "with --build-flux-ratio-adf, existing homogeneous face-flux HDF5 "
            "or FILE::DATASET denominator; skips low-order driver reconstruction"
        ),
    )
    parser.add_argument(
        "--low-order-volume-flux",
        default=None,
        help=(
            "with --build-flux-ratio-adf, HDF5 file or FILE::DATASET containing "
            "low-order volume-average flux"
        ),
    )
    parser.add_argument(
        "--low-order-net-current",
        default=None,
        help=(
            "with --build-flux-ratio-adf, HDF5 file or FILE::DATASET containing "
            "net current density"
        ),
    )
    parser.add_argument(
        "--low-order-net-current-sign-convention",
        default=None,
        choices=("auto", "positive-outward", "positive-inward"),
        help=(
            "with --build-flux-ratio-adf, raw low-order current sign; default "
            "auto reads HDF5 sign_convention metadata or assumes positive-outward"
        ),
    )
    parser.add_argument(
        "--low-order-source-label",
        default="external low-order driver",
        help="with --build-flux-ratio-adf, provenance label for the low-order driver handoff",
    )
    parser.add_argument(
        "--adf-face-widths",
        default="1.0",
        help=(
            "with --build-flux-ratio-adf, one width for all faces or comma-separated "
            "widths matching --adf-faces"
        ),
    )
    parser.add_argument(
        "--adf-invalid-fill",
        type=float,
        default=None,
        help="with --build-flux-ratio-adf, fill value for invalid flux-ratio ADF bins",
    )
    parser.add_argument(
        "--adf-clip-min",
        type=float,
        default=None,
        help="with --build-flux-ratio-adf, optional lower clip bound for ADF values",
    )
    parser.add_argument(
        "--adf-clip-max",
        type=float,
        default=None,
        help="with --build-flux-ratio-adf, optional upper clip bound for ADF values",
    )
    parser.add_argument(
        "--mixture",
        action="append",
        default=None,
        help="write only the named mixture; repeat to keep several mixtures",
    )
    parser.add_argument(
        "--no-overwrite-hdf5",
        action="store_true",
        help="fail if --keep-hdf5 already exists",
    )
    parser.add_argument(
        "--force-run-dir",
        action="store_true",
        help="with --run-dir, overwrite existing managed run-directory artifacts",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable conversion summary JSON",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run HDF5 input-contract preflight after export and before conversion",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="with --check, require ADF data for every mixture",
    )
    parser.add_argument(
        "--require-sph",
        action="store_true",
        help="with --check, require SPH data for every mixture",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="with --check, comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="with --check, require explicit transport_total datasets",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="with --check, require positive volume attributes",
    )
    parser.add_argument(
        "--scatter-row-balance-warn",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, warn if max |total - absorption - sum(P0 scatter out)| "
            "/ |total| exceeds REL"
        ),
    )
    parser.add_argument(
        "--scatter-row-balance-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, fail if max |total - absorption - sum(P0 scatter out)| "
            "/ |total| exceeds REL"
        ),
    )
    parser.add_argument(
        "--uncertainty-warn",
        type=float,
        default=0.05,
        metavar="REL",
        help=(
            "with --check, warn if any available *_std_dev / |mean| exceeds "
            "REL (default: 0.05)"
        ),
    )
    parser.add_argument(
        "--uncertainty-fail",
        type=float,
        default=None,
        metavar="REL",
        help="with --check, fail if any available *_std_dev / |mean| exceeds REL",
    )
    parser.add_argument(
        "--uncertainty-production-fail",
        type=float,
        default=None,
        metavar="REL",
        help=(
            "with --check, fail if production-critical uncertainty exceeds REL; "
            "this gates 1D XS and P0 scatter but leaves higher scatter moments "
            "warning-only"
        ),
    )
    parser.add_argument(
        "--uncertainty-mean-abs-floor",
        type=float,
        default=1.0e-12,
        metavar="ABS",
        help=(
            "with --check, skip relative uncertainty bins with |mean| <= ABS "
            "(default: 1e-12)"
        ),
    )
    parser.add_argument(
        "--no-uncertainty-check",
        action="store_true",
        help="with --check, disable *_std_dev relative uncertainty checks",
    )
    parser.add_argument(
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
    )
    parser.add_argument(
        "--adf-summary-json",
        type=Path,
        default=None,
        help="with --adf-source, write a machine-readable ADF injection summary JSON",
    )
    parser.add_argument(
        "--sph-summary-json",
        type=Path,
        default=None,
        help="with --sph-source/--sph-macrolib, write a machine-readable SPH injection summary JSON",
    )
    parser.add_argument(
        "--extra-artifact",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="with --run-dir, copy an additional artifact into manifest.json; repeatable",
    )
    return parser
