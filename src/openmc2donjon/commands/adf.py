"""ADF, face-flux, and low-order-driver CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from .base import (
    USER_FACING_EXCEPTIONS,
    CommandSpec,
    exit_with_command_error,
    parser_from_args,
)
from ..adf_augment import augment_hdf5_with_adf, parse_faces
from ..adf_sidecar import create_flux_ratio_adf_sidecar, create_unity_adf_sidecar
from ..face_flux_check import check_face_flux
from ..homogeneous_face_flux import create_homogeneous_face_flux
from ..low_order_driver import check_low_order_driver, create_low_order_driver
from ..openmc_surface_flux import (
    DEFAULT_TALLY_NAME as DEFAULT_SURFACE_FLUX_TALLY_NAME,
    export_openmc_surface_flux,
)


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "export-surface-flux",
            build_export_surface_flux_parser,
            export_surface_flux_handler,
            "export OpenMC surface flux from a statepoint",
        ),
        CommandSpec(
            "check-face-flux",
            build_check_face_flux_parser,
            check_face_flux_handler,
            "validate heterogeneous/homogeneous face-flux inputs",
        ),
        CommandSpec(
            "make-low-order-driver",
            build_make_low_order_driver_parser,
            make_low_order_driver_handler,
            "canonicalize low-order flux/current inputs",
        ),
        CommandSpec(
            "check-low-order-driver",
            build_check_low_order_driver_parser,
            check_low_order_driver_handler,
            "validate a low-order driver handoff",
        ),
        CommandSpec(
            "make-homogeneous-face-flux",
            build_make_homogeneous_face_flux_parser,
            make_homogeneous_face_flux_handler,
            "reconstruct homogeneous face fluxes",
        ),
        CommandSpec(
            "make-adf-sidecar",
            build_make_adf_sidecar_parser,
            make_adf_sidecar_handler,
            "create an ADF/DF sidecar",
        ),
        CommandSpec(
            "augment-adf",
            build_augment_adf_parser,
            augment_adf_handler,
            "inject ADF/DF values into an MGXS HDF5 handoff",
        ),
    )


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


def build_check_face_flux_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon check-face-flux",
        description=(
            "Validate heterogeneous and homogeneous face-flux HDF5 inputs "
            "before building a flux-ratio ADF sidecar."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 handoff used for metadata")
    parser.add_argument(
        "--surface-flux",
        required=True,
        help="heterogeneous face-flux HDF5 file or FILE::DATASET",
    )
    parser.add_argument(
        "--homogeneous-face-flux",
        required=True,
        help="homogeneous face-flux HDF5 file or FILE::DATASET denominator",
    )
    parser.add_argument(
        "--faces",
        default="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
        help="comma-separated expected face names",
    )
    parser.add_argument(
        "--invalid-fill",
        type=float,
        default=None,
        help="explicit fill value for invalid flux-ratio bins",
    )
    parser.add_argument(
        "--clip-min",
        type=float,
        default=None,
        help="optional lower clip bound for ratio values",
    )
    parser.add_argument(
        "--clip-max",
        type=float,
        default=None,
        help="optional upper clip bound for ratio values",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable face-flux contract summary JSON",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="always return zero after printing the contract report",
    )
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
            "Canonicalize external low-order driver volume flux and "
            "net current density into the HDF5 layout consumed by "
            "make-homogeneous-face-flux."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 handoff used for metadata")
    parser.add_argument("-o", "--output", type=Path, required=True, help="low-order driver HDF5")
    parser.add_argument(
        "--raw-driver",
        default=None,
        help=(
            "raw low-order driver HDF5 bundle; when set, --volume-flux and "
            "--net-current default to auto-detected datasets in this file"
        ),
    )
    parser.add_argument(
        "--volume-flux",
        default=None,
        help="HDF5 file or FILE::DATASET containing volume-average flux",
    )
    parser.add_argument(
        "--net-current",
        default=None,
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


def augment_adf_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
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
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "augment-adf", exc)
    return 0


def make_adf_sidecar_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
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
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-adf-sidecar", exc)
    return 0


def export_surface_flux_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
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
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "export-surface-flux", exc)
    return 0


def check_face_flux_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        report = check_face_flux(
            args.input_h5,
            surface_flux=args.surface_flux,
            homogeneous_face_flux=args.homogeneous_face_flux,
            faces=parse_faces(args.faces),
            invalid_fill=args.invalid_fill,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "check-face-flux", exc)
    return 0 if report.ok or args.no_fail else 1


def make_low_order_driver_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        create_low_order_driver(
            args.input_h5,
            args.output,
            raw_driver=args.raw_driver,
            volume_flux=args.volume_flux,
            net_current=args.net_current,
            faces=parse_faces(args.faces),
            net_current_sign_convention=args.net_current_sign_convention,
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-low-order-driver", exc)
    return 0


def check_low_order_driver_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
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
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "check-low-order-driver", exc)
    return 0 if report.ok or args.no_fail else 1


def make_homogeneous_face_flux_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
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
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-homogeneous-face-flux", exc)
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
