"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .adf_augment import augment_hdf5_with_adf, parse_faces
from .adf_sidecar import create_flux_ratio_adf_sidecar, create_unity_adf_sidecar
from .bundle import ArtifactSpec, bundle_artifacts, parse_extra_artifact
from .doctor import run_doctor
from .homogeneous_face_flux import create_homogeneous_face_flux
from .low_order_driver import check_low_order_driver, create_low_order_driver
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_diff import diff_hdf5_files
from .mgxs_inspect import inspect_files
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .openmc_surface_flux import (
    DEFAULT_TALLY_NAME as DEFAULT_SURFACE_FLUX_TALLY_NAME,
    export_openmc_surface_flux,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description=(
            "Convert an OpenMC MGXS HDF5 dump to DONJON ASCII LCM objects. "
            "Use 'openmc2donjon inspect <input_h5>' to inspect an HDF5 handoff, "
            "'openmc2donjon diff <reference_h5> <candidate_h5>' to compare two "
            "handoffs, 'openmc2donjon export-surface-flux <statepoint> ...' to "
            "export OpenMC face fluxes, 'openmc2donjon make-low-order-driver "
            "<input_h5> ...' to canonicalize a low-order driver handoff, "
            "'openmc2donjon check-low-order-driver <input_h5> <driver_h5>' to "
            "validate the low-order handoff, "
            "'openmc2donjon make-homogeneous-face-flux <input_h5> ...' to "
            "reconstruct homogeneous face fluxes, 'openmc2donjon "
            "make-adf-sidecar <input_h5> ...' to create an ADF "
            "sidecar, 'openmc2donjon augment-adf <input_h5> ...' to inject "
            "computed discontinuity factors, "
            "'openmc2donjon bundle --output-dir DIR ...' to collect "
            "production artifacts, 'openmc2donjon doctor' for environment checks, or "
            "'openmc2donjon check <input_h5>' for input-contract preflight."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    parser.add_argument("input_h5", help="OpenMC MGXS library HDF5 file")
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
        "--root-name",
        default=DEFAULT_ROOT_NAME,
        help=f"top-level LCM directory name (default: {DEFAULT_ROOT_NAME})",
    )
    parser.add_argument(
        "--comment",
        default=None,
        help="COMMENT block text (default: derived from input filename)",
    )
    parser.add_argument(
        "--burnup",
        type=float,
        default=None,
        help=(
            "write a single-point BURN parameter axis with this value; useful "
            "for D2P/PMAXS workflows that require PARKEY metadata"
        ),
    )
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help=(
            "write this constant H-FACTOR when the input HDF5 does not provide "
            "one; intended for D2P plumbing smokes, not production physics"
        ),
    )
    parser.add_argument(
        "--mixture",
        action="append",
        default=None,
        help=(
            "write only the named mixture; repeat to keep several mixtures. "
            "D2P/PMAXS fuel smokes typically require a single-mixture MCO"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run HDF5 input-contract preflight before conversion",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="with --check, require ADF data for every mixture",
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
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
    )
    return parser


def build_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon check",
        description="Validate OpenMC MGXS HDF5 files against the openmc2donjon input contract.",
    )
    parser.add_argument("input_h5", type=Path, nargs="+", help="MGXS HDF5 input file")
    parser.add_argument(
        "--format",
        choices=("multicompo", "macrolib", "any"),
        default="any",
        help="expected converter output format for --output name checks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional intended converter output path; checks production extension",
    )
    parser.add_argument(
        "--require-adf",
        action="store_true",
        help="require ADF data for every mixture",
    )
    parser.add_argument(
        "--expected-adf-faces",
        default=None,
        help="comma-separated ADF face names expected on every ADF-bearing mixture",
    )
    parser.add_argument(
        "--require-transport-dataset",
        action="store_true",
        help="require an explicit transport_total dataset, not only P1-derived STRD",
    )
    parser.add_argument(
        "--require-volume",
        action="store_true",
        help="require a positive volume attribute on every mixture",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable summary JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the preflight report",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def build_inspect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon inspect",
        description="Inspect OpenMC MGXS HDF5 files without converting them.",
    )
    parser.add_argument("input_h5", type=Path, nargs="+", help="MGXS HDF5 input file")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="number of mixtures to list per file (default: 20)",
    )
    parser.add_argument(
        "--all-mixtures",
        action="store_true",
        help="list every mixture instead of applying --limit",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable inspection JSON",
    )
    return parser


def build_diff_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon diff",
        description="Compare two OpenMC MGXS HDF5 handoff files.",
    )
    parser.add_argument("reference_h5", type=Path, help="reference MGXS HDF5 file")
    parser.add_argument("candidate_h5", type=Path, help="candidate MGXS HDF5 file")
    parser.add_argument(
        "--rtol",
        type=float,
        default=0.0,
        help="relative tolerance for numeric datasets and numeric attributes (default: 0)",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=0.0,
        help="absolute tolerance for numeric datasets and numeric attributes (default: 0)",
    )
    parser.add_argument(
        "--ignore-attrs",
        action="store_true",
        help="compare HDF5 object tree and datasets only, ignoring all attributes",
    )
    parser.add_argument(
        "--ignore-attr",
        action="append",
        default=[],
        help="ignore an attribute name wherever it appears; repeat as needed",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable diff JSON",
    )
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=20,
        help="maximum number of differences to print (default: 20)",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the diff report",
    )
    return parser


def build_doctor_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon doctor",
        description="Check the local openmc2donjon runtime environment.",
    )
    parser.add_argument(
        "--recipe",
        type=Path,
        default=None,
        help="optional OpenMC export recipe to dry-run as part of the check",
    )
    parser.add_argument(
        "--statepoint",
        type=Path,
        default=None,
        help="optional statepoint path passed to the recipe dry-run",
    )
    parser.add_argument(
        "--load-statepoint",
        action="store_true",
        help="with --recipe and --statepoint, load the statepoint during recipe dry-run",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable doctor JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the doctor report",
    )
    return parser


def build_bundle_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon bundle",
        description="Collect production handoff artifacts into a manifest-backed directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory that will receive copied artifacts and manifest.json",
    )
    parser.add_argument(
        "--mgxs",
        type=Path,
        default=None,
        help="MGXS HDF5 handoff to include",
    )
    parser.add_argument(
        "--mcompo",
        type=Path,
        default=None,
        help="L_MULTICOMPO ASCII output to include",
    )
    parser.add_argument(
        "--macrolib",
        type=Path,
        default=None,
        help="L_MACROLIB ASCII output to include",
    )
    parser.add_argument(
        "--run-summary",
        type=Path,
        default=None,
        help="one-step conversion summary JSON to include",
    )
    parser.add_argument(
        "--check-summary",
        type=Path,
        default=None,
        help="input-contract preflight summary JSON to include",
    )
    parser.add_argument(
        "--inspect-summary",
        type=Path,
        default=None,
        help="MGXS inspect summary JSON to include",
    )
    parser.add_argument(
        "--doctor-summary",
        type=Path,
        default=None,
        help="doctor summary JSON to include",
    )
    parser.add_argument(
        "--diff-summary",
        type=Path,
        default=None,
        help="HDF5 diff summary JSON to include",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="additional artifact to include; repeat as needed",
    )
    parser.add_argument(
        "--manifest-name",
        default="manifest.json",
        help="manifest filename inside --output-dir (default: manifest.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing bundled files and manifest",
    )
    return parser


def build_augment_adf_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon augment-adf",
        description="Inject computed ADF/DF values into an MGXS HDF5 handoff.",
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file to augment")
    parser.add_argument(
        "--adf-source",
        type=Path,
        required=True,
        help="HDF5 sidecar containing ADF values",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="augmented MGXS HDF5 output path",
    )
    parser.add_argument(
        "--faces",
        default=None,
        help="comma-separated expected face names, for example FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
    )
    parser.add_argument(
        "--adf-kind",
        default=None,
        help="override root adf_kind provenance attribute",
    )
    parser.add_argument(
        "--adf-real",
        choices=("true", "false"),
        default=None,
        help="override root adf_real provenance attribute",
    )
    parser.add_argument(
        "--adf-source-label",
        default=None,
        help="override root adf_source provenance attribute",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable ADF augmentation summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the augmented output HDF5 if it already exists",
    )
    return parser


def build_make_adf_sidecar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-adf-sidecar",
        description=(
            "Create an ADF/DF sidecar HDF5 from an MGXS handoff. The initial "
            "mode is unity/identity ADF for workflow integration; replace it "
            "with physics ADF values for production neutronics."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="ADF sidecar HDF5 output path",
    )
    parser.add_argument(
        "--mode",
        choices=("unity", "flux-ratio"),
        default="unity",
        help=(
            "sidecar generation mode: unity for identity values, flux-ratio "
            "for heterogeneous/homogeneous face-flux ratios (default: unity)"
        ),
    )
    parser.add_argument(
        "--faces",
        default="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
        help="comma-separated face names to write (default: Cartesian four faces)",
    )
    parser.add_argument(
        "--value",
        type=float,
        default=1.0,
        help="constant ADF value for --mode unity (default: 1.0)",
    )
    parser.add_argument(
        "--surface-flux",
        "--heterogeneous-face-flux",
        dest="surface_flux",
        default=None,
        help=(
            "for --mode flux-ratio, HDF5 file or FILE::DATASET containing "
            "heterogeneous face flux values"
        ),
    )
    parser.add_argument(
        "--homogeneous-face-flux",
        default=None,
        help=(
            "for --mode flux-ratio, HDF5 file or FILE::DATASET containing "
            "homogeneous face flux values"
        ),
    )
    parser.add_argument(
        "--invalid-fill",
        type=float,
        default=None,
        help="for --mode flux-ratio, positive value used to fill invalid ADF bins",
    )
    parser.add_argument(
        "--clip-min",
        type=float,
        default=None,
        help="for --mode flux-ratio, lower bound applied after invalid-bin filling",
    )
    parser.add_argument(
        "--clip-max",
        type=float,
        default=None,
        help="for --mode flux-ratio, upper bound applied after invalid-bin filling",
    )
    parser.add_argument(
        "--adf-kind",
        default="flux-ratio",
        help="for --mode flux-ratio, root adf_kind provenance attribute",
    )
    parser.add_argument(
        "--adf-real",
        choices=("true", "false"),
        default="true",
        help="for --mode flux-ratio, root adf_real provenance attribute",
    )
    parser.add_argument(
        "--adf-source-label",
        default=None,
        help="for --mode flux-ratio, root adf_source provenance attribute",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable ADF sidecar summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the sidecar HDF5 if it already exists",
    )
    return parser


def build_export_surface_flux_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon export-surface-flux",
        description=(
            "Export an OpenMC MeshSurfaceFilter + MuSurfaceFilter current tally "
            "from a statepoint into the face-flux HDF5 layout consumed by "
            "make-adf-sidecar --mode flux-ratio."
        ),
    )
    parser.add_argument("statepoint", type=Path, help="OpenMC statepoint containing the tally")
    parser.add_argument("-o", "--output", type=Path, required=True, help="surface-flux HDF5 output")
    parser.add_argument(
        "--mgxs",
        type=Path,
        default=None,
        help="MGXS HDF5 handoff used for energy bounds and mixture names",
    )
    parser.add_argument(
        "--tally-name",
        default=DEFAULT_SURFACE_FLUX_TALLY_NAME,
        help=f"OpenMC tally name (default: {DEFAULT_SURFACE_FLUX_TALLY_NAME})",
    )
    parser.add_argument(
        "--mesh-shape",
        default=None,
        help="mesh shape as Y,X; defaults to 1,N when mixture names are available",
    )
    parser.add_argument(
        "--mixture-names",
        default=None,
        help="comma-separated mixture names in row-major mesh order when --mgxs is not enough",
    )
    parser.add_argument(
        "--energy-bounds",
        default=None,
        help="comma-separated ascending energy bounds in eV when --mgxs is not supplied",
    )
    parser.add_argument(
        "--mu-edges",
        required=True,
        help="comma-separated MuSurfaceFilter bin edges used by the tally",
    )
    parser.add_argument(
        "--face-area",
        type=float,
        default=1.0,
        help="area used in surface_flux=sum(current_mu/mu_midpoint)/face_area",
    )
    parser.add_argument(
        "--faces",
        default="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
        help="comma-separated output face names",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable surface-flux export summary JSON",
    )
    parser.add_argument("--force", action="store_true", help="overwrite output if it exists")
    return parser


def build_make_homogeneous_face_flux_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-homogeneous-face-flux",
        description=(
            "Reconstruct homogeneous face fluxes from MGXS transport data, "
            "volume-average flux, and outward net current density. The output "
            "is consumed by make-adf-sidecar --mode flux-ratio."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 handoff with transport_total")
    parser.add_argument("-o", "--output", type=Path, required=True, help="homogeneous face-flux HDF5")
    parser.add_argument(
        "--volume-flux",
        required=True,
        help="HDF5 file or FILE::DATASET containing volume-average flux",
    )
    parser.add_argument(
        "--net-current",
        required=True,
        help="HDF5 file or FILE::DATASET containing net current density",
    )
    parser.add_argument(
        "--net-current-sign-convention",
        default=None,
        choices=("auto", "positive-outward", "positive-inward"),
        help=(
            "raw net-current sign convention; default auto reads HDF5 "
            "sign_convention metadata or assumes positive-outward"
        ),
    )
    parser.add_argument(
        "--faces",
        default="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
        help="comma-separated face names",
    )
    parser.add_argument(
        "--face-widths",
        default="1.0",
        help="one width for all faces or comma-separated widths matching --faces",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable homogeneous face-flux summary JSON",
    )
    parser.add_argument("--force", action="store_true", help="overwrite output if it exists")
    return parser


def build_make_low_order_driver_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-low-order-driver",
        description=(
            "Canonicalize external low-order driver volume flux and outward "
            "net current density into the HDF5 layout consumed by "
            "make-homogeneous-face-flux."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 handoff used for metadata")
    parser.add_argument("-o", "--output", type=Path, required=True, help="low-order driver HDF5")
    parser.add_argument(
        "--volume-flux",
        required=True,
        help="HDF5 file or FILE::DATASET containing volume-average flux",
    )
    parser.add_argument(
        "--net-current",
        required=True,
        help="HDF5 file or FILE::DATASET containing net current density",
    )
    parser.add_argument(
        "--net-current-sign-convention",
        default=None,
        choices=("auto", "positive-outward", "positive-inward"),
        help=(
            "raw net-current sign convention; default auto reads HDF5 "
            "sign_convention metadata or assumes positive-outward"
        ),
    )
    parser.add_argument(
        "--faces",
        default="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
        help="comma-separated face names",
    )
    parser.add_argument(
        "--source-label",
        default="external low-order driver",
        help="provenance label stored in the output HDF5",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable low-order driver summary JSON",
    )
    parser.add_argument("--force", action="store_true", help="overwrite output if it exists")
    return parser


def build_check_low_order_driver_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon check-low-order-driver",
        description=(
            "Validate a canonical low-order driver HDF5 handoff against MGXS "
            "mixture, group, face, and current sign-convention metadata."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 handoff used for metadata")
    parser.add_argument("driver_h5", type=Path, help="canonical low-order driver HDF5")
    parser.add_argument(
        "--faces",
        default=None,
        help="comma-separated face names expected in the driver",
    )
    parser.add_argument(
        "--face-widths",
        default=None,
        help=(
            "optional width check: one width for all faces or comma-separated "
            "widths matching --faces/driver faces; verifies reconstructed "
            "homogeneous face flux is positive"
        ),
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable low-order driver contract summary JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the contract report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and raw_argv[0] == "export-surface-flux":
        return _export_surface_flux_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "make-low-order-driver":
        return _make_low_order_driver_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "check-low-order-driver":
        return _check_low_order_driver_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "make-homogeneous-face-flux":
        return _make_homogeneous_face_flux_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "make-adf-sidecar":
        return _make_adf_sidecar_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "augment-adf":
        return _augment_adf_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "bundle":
        return _bundle_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "doctor":
        return _doctor_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "diff":
        return _diff_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "inspect":
        return _inspect_main(raw_argv[1:])
    if raw_argv and raw_argv[0] == "check":
        return _check_main(raw_argv[1:])

    args = build_parser().parse_args(raw_argv)
    input_path = Path(args.input_h5)
    if args.output:
        output_path = Path(args.output)
    elif args.format == "macrolib":
        output_path = Path("out.macrolib.txt")
    else:
        output_path = Path("out.mcompo.txt")

    if args.check:
        ok = run_preflight(
            [input_path],
            output_format=args.format,
            output_path=output_path,
            require_adf=args.require_adf,
            expected_adf_faces=args.expected_adf_faces,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            summary_json=args.check_summary_json,
        )
        if not ok:
            return 1

    if args.format == "macrolib":
        convert_mgxs_hdf5_to_macrolib(
            input_path,
            output_path,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    else:
        convert_mgxs_hdf5(
            input_path,
            output_path,
            root_name=args.root_name,
            comment=args.comment,
            burnup=args.burnup,
            h_factor_default=args.h_factor_default,
            mixture_names=args.mixture,
        )
    return 0


def _check_main(argv: list[str]) -> int:
    args = build_check_parser().parse_args(argv)
    ok = run_preflight(
        args.input_h5,
        output_format=args.format,
        output_path=args.output,
        require_adf=args.require_adf,
        expected_adf_faces=args.expected_adf_faces,
        require_transport_dataset=args.require_transport_dataset,
        require_volume=args.require_volume,
        summary_json=args.summary_json,
    )
    return 0 if ok or args.no_fail else 1


def _inspect_main(argv: list[str]) -> int:
    args = build_inspect_parser().parse_args(argv)
    reports = inspect_files(
        args.input_h5,
        limit=args.limit,
        all_mixtures=args.all_mixtures,
        summary_json=args.summary_json,
    )
    return 0 if all(report.ok for report in reports) else 1


def _diff_main(argv: list[str]) -> int:
    args = build_diff_parser().parse_args(argv)
    report = diff_hdf5_files(
        args.reference_h5,
        args.candidate_h5,
        rtol=args.rtol,
        atol=args.atol,
        compare_attrs=not args.ignore_attrs,
        ignored_attrs=tuple(args.ignore_attr),
        summary_json=args.summary_json,
        max_diffs=args.max_diffs,
    )
    return 0 if report.ok or args.no_fail else 1


def _doctor_main(argv: list[str]) -> int:
    parser = build_doctor_parser()
    args = parser.parse_args(argv)
    if args.statepoint is not None and args.recipe is None:
        parser.error("--statepoint can only be used with --recipe")
    if args.load_statepoint and args.recipe is None:
        parser.error("--load-statepoint can only be used with --recipe")
    if args.load_statepoint and args.statepoint is None:
        parser.error("--load-statepoint requires --statepoint")
    report = run_doctor(
        recipe=args.recipe,
        statepoint=args.statepoint,
        load_statepoint=args.load_statepoint,
        summary_json=args.summary_json,
    )
    return 0 if report.ok or args.no_fail else 1


def _bundle_main(argv: list[str]) -> int:
    parser = build_bundle_parser()
    args = parser.parse_args(argv)
    artifacts = _bundle_artifacts_from_args(args, parser)
    try:
        bundle_artifacts(
            output_dir=args.output_dir,
            artifacts=artifacts,
            manifest_name=args.manifest_name,
            force=args.force,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon bundle: error: {exc}\n")
    return 0


def _augment_adf_main(argv: list[str]) -> int:
    parser = build_augment_adf_parser()
    args = parser.parse_args(argv)
    try:
        faces = parse_faces(args.faces)
        augment_hdf5_with_adf(
            args.input_h5,
            adf_source=args.adf_source,
            output_h5=args.output,
            expected_faces=faces,
            force=args.force,
            adf_kind=args.adf_kind,
            adf_real=args.adf_real,
            adf_source_label=args.adf_source_label,
            summary_json=args.summary_json,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon augment-adf: error: {exc}\n")
    return 0


def _make_adf_sidecar_main(argv: list[str]) -> int:
    parser = build_make_adf_sidecar_parser()
    args = parser.parse_args(argv)
    try:
        faces = parse_faces(args.faces)
        if args.mode == "unity":
            create_unity_adf_sidecar(
                args.input_h5,
                args.output,
                faces=faces,
                value=args.value,
                force=args.force,
                summary_json=args.summary_json,
            )
        elif args.mode == "flux-ratio":
            if args.surface_flux is None:
                parser.error("--mode flux-ratio requires --surface-flux")
            if args.homogeneous_face_flux is None:
                parser.error("--mode flux-ratio requires --homogeneous-face-flux")
            create_flux_ratio_adf_sidecar(
                args.input_h5,
                args.output,
                surface_flux=args.surface_flux,
                homogeneous_face_flux=args.homogeneous_face_flux,
                faces=faces,
                force=args.force,
                summary_json=args.summary_json,
                invalid_fill=args.invalid_fill,
                clip_min=args.clip_min,
                clip_max=args.clip_max,
                adf_kind=args.adf_kind,
                adf_real=args.adf_real == "true",
                adf_source_label=args.adf_source_label,
            )
        else:
            parser.error(f"unsupported --mode: {args.mode}")
    except Exception as exc:
        parser.exit(1, f"openmc2donjon make-adf-sidecar: error: {exc}\n")
    return 0


def _export_surface_flux_main(argv: list[str]) -> int:
    parser = build_export_surface_flux_parser()
    args = parser.parse_args(argv)
    try:
        export_openmc_surface_flux(
            args.statepoint,
            args.output,
            mgxs_h5=args.mgxs,
            tally_name=args.tally_name,
            mesh_shape=_parse_mesh_shape(args.mesh_shape),
            mu_edges=_parse_float_tuple(args.mu_edges, "--mu-edges"),
            face_area=args.face_area,
            face_names=parse_faces(args.faces),
            mixture_names=_parse_optional_str_tuple(args.mixture_names),
            energy_bounds=_parse_optional_float_tuple(args.energy_bounds, "--energy-bounds"),
            force=args.force,
            summary_json=args.summary_json,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon export-surface-flux: error: {exc}\n")
    return 0


def _make_low_order_driver_main(argv: list[str]) -> int:
    parser = build_make_low_order_driver_parser()
    args = parser.parse_args(argv)
    try:
        create_low_order_driver(
            args.input_h5,
            args.output,
            volume_flux=args.volume_flux,
            net_current=args.net_current,
            faces=parse_faces(args.faces),
            net_current_sign_convention=args.net_current_sign_convention,
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon make-low-order-driver: error: {exc}\n")
    return 0


def _check_low_order_driver_main(argv: list[str]) -> int:
    parser = build_check_low_order_driver_parser()
    args = parser.parse_args(argv)
    try:
        report = check_low_order_driver(
            args.input_h5,
            args.driver_h5,
            faces=None if args.faces is None else parse_faces(args.faces),
            face_widths=(
                None
                if args.face_widths is None
                else _parse_float_tuple(args.face_widths, "--face-widths")
            ),
            summary_json=args.summary_json,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon check-low-order-driver: error: {exc}\n")
    return 0 if report.ok or args.no_fail else 1


def _make_homogeneous_face_flux_main(argv: list[str]) -> int:
    parser = build_make_homogeneous_face_flux_parser()
    args = parser.parse_args(argv)
    try:
        create_homogeneous_face_flux(
            args.input_h5,
            args.output,
            volume_flux=args.volume_flux,
            net_current=args.net_current,
            faces=parse_faces(args.faces),
            face_widths=_parse_float_tuple(args.face_widths, "--face-widths"),
            net_current_sign_convention=args.net_current_sign_convention,
            force=args.force,
            summary_json=args.summary_json,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon make-homogeneous-face-flux: error: {exc}\n")
    return 0


def _parse_mesh_shape(raw: str | None) -> tuple[int, int] | None:
    if raw is None:
        return None
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError("--mesh-shape must be Y,X")
    try:
        mesh_shape = (int(parts[0]), int(parts[1]))
    except ValueError as exc:
        raise ValueError("--mesh-shape must contain integers") from exc
    if mesh_shape[0] <= 0 or mesh_shape[1] <= 0:
        raise ValueError("--mesh-shape entries must be positive")
    return mesh_shape


def _parse_float_tuple(raw: str, option: str) -> tuple[float, ...]:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        raise ValueError(f"{option} must list at least one value")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise ValueError(f"{option} must contain numeric values") from exc


def _parse_optional_float_tuple(raw: str | None, option: str) -> tuple[float, ...] | None:
    if raw is None:
        return None
    return _parse_float_tuple(raw, option)


def _parse_optional_str_tuple(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values:
        raise ValueError("--mixture-names must list at least one name")
    return values


def _bundle_artifacts_from_args(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> list[ArtifactSpec]:
    artifacts: list[ArtifactSpec] = []
    for label, path in (
        ("mgxs", args.mgxs),
        ("mcompo", args.mcompo),
        ("macrolib", args.macrolib),
        ("run-summary", args.run_summary),
        ("check-summary", args.check_summary),
        ("inspect-summary", args.inspect_summary),
        ("doctor-summary", args.doctor_summary),
        ("diff-summary", args.diff_summary),
    ):
        if path is not None:
            artifacts.append(ArtifactSpec(label=label, source=path))
    for raw in args.extra:
        try:
            artifacts.append(parse_extra_artifact(raw))
        except ValueError as exc:
            parser.error(f"--extra {raw!r}: {exc}")
    if not artifacts:
        parser.error("at least one artifact option is required")
    return artifacts


if __name__ == "__main__":
    raise SystemExit(main())
