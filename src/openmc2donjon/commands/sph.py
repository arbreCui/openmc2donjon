"""SPH sidecar and legacy DONJON-flux CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .base import (
    USER_FACING_EXCEPTIONS,
    CommandSpec,
    exit_with_command_error,
    parser_from_args,
)
from .acceptance import add_sph_loop_acceptance_args, sph_loop_acceptance_from_args
from ..donjon_flux import extract_donjon_volume_flux
from ..donjon_sph_config import write_donjon_sph_loop_config
from ..multicompo import DEFAULT_ROOT_NAME
from ..sph_augment import (
    augment_hdf5_with_sph,
    create_macrolib_sph_sidecar,
    create_table_sph_sidecar,
    create_unity_sph_sidecar,
)
from ..sph_iteration import FLUX_NORMALIZATIONS, create_sph_update_table
from ..sph_loop import run_sph_loop
from ..sph_loop_scaffold import create_sph_loop_scaffold, parse_scalar_flux_map
from ..sph_workflow import run_sph_iteration_workflow


def command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "make-sph-sidecar",
            build_make_sph_sidecar_parser,
            make_sph_sidecar_handler,
            "create an SPH sidecar",
        ),
        CommandSpec(
            "make-sph-update-table",
            build_make_sph_update_table_parser,
            make_sph_update_table_handler,
            "compute an OpenMC CE/MG SPH factor table",
        ),
        CommandSpec(
            "augment-sph",
            build_augment_sph_parser,
            augment_sph_handler,
            "inject SPH factors into an MGXS HDF5 handoff",
        ),
        CommandSpec(
            "extract-donjon-volume-flux",
            build_extract_donjon_volume_flux_parser,
            extract_donjon_volume_flux_handler,
            "legacy: extract DONJON L_FLUX scalar unknowns",
            hidden=True,
        ),
        CommandSpec(
            "run-sph-iteration",
            build_run_sph_iteration_parser,
            run_sph_iteration_handler,
            "legacy: run one DONJON-backed SPH iteration",
            hidden=True,
        ),
        CommandSpec(
            "run-sph-loop",
            build_run_sph_loop_parser,
            run_sph_loop_handler,
            "legacy: run a DONJON-backed fixed-OpenMC SPH loop",
            hidden=True,
        ),
        CommandSpec(
            "make-donjon-sph-loop-config",
            build_make_donjon_sph_loop_config_parser,
            make_donjon_sph_loop_config_handler,
            "legacy: write a generic DONJON-backed SPH loop config",
            hidden=True,
        ),
        CommandSpec(
            "make-sph-loop-scaffold",
            build_make_sph_loop_scaffold_parser,
            make_sph_loop_scaffold_handler,
            "legacy: write reference flux, flux map, and SPH loop config",
            hidden=True,
        ),
    )


def build_augment_sph_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon augment-sph",
        description="Inject SPH equivalence factors into an MGXS HDF5 handoff.",
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file to augment")
    parser.add_argument(
        "--sph-source",
        type=Path,
        required=True,
        help="HDF5 sidecar containing SPH vectors",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="augmented MGXS HDF5 output path",
    )
    parser.add_argument(
        "--sph-kind",
        default=None,
        help="override root sph_kind provenance attribute",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default=None,
        help="override root sph_real provenance attribute",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default=None,
        help=(
            "mark whether the XS payload has already been SPH-corrected; "
            "the converter records factors but does not apply them"
        ),
    )
    parser.add_argument(
        "--sph-source-label",
        default=None,
        help="override root sph_source provenance attribute",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH augmentation summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the augmented output HDF5 if it already exists",
    )
    return parser


def build_make_sph_sidecar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-sph-sidecar",
        description=(
            "Create an SPH sidecar HDF5 from an MGXS handoff. Production SPH "
            "factors should come from OpenMC CE reference versus OpenMC MG "
            "macro calculations using the same geometry. Unity SPH is useful "
            "for plumbing; table mode canonicalizes external SPH factors from "
            "CSV; macrolib mode remains available for legacy NSPH extraction."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="SPH sidecar HDF5 output path",
    )
    parser.add_argument(
        "--mode",
        choices=("unity", "macrolib", "table"),
        default="unity",
        help="sidecar source mode (default: unity)",
    )
    parser.add_argument(
        "--macrolib",
        type=Path,
        default=None,
        help="for --mode macrolib, L_MACROLIB ASCII file containing GROUP/*/NSPH",
    )
    parser.add_argument(
        "--table",
        type=Path,
        default=None,
        help=(
            "for --mode table, CSV with either long columns mixture,group,sph "
            "or wide columns mixture,g1,g2,..."
        ),
    )
    parser.add_argument(
        "--value",
        type=float,
        default=1.0,
        help="constant SPH value for --mode unity (default: 1.0)",
    )
    parser.add_argument(
        "--sph-kind",
        default=None,
        help="root sph_kind provenance attribute (default: unity or macrolib-nsph)",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default=None,
        help="root sph_real provenance attribute (default: false for unity, true for macrolib)",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default=None,
        help="root sph_applied provenance attribute (default: false)",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH sidecar summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the sidecar HDF5 if it already exists",
    )
    return parser


def build_make_sph_update_table_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-sph-update-table",
        description=(
            "Create an external SPH CSV table from OpenMC CE reference flux "
            "and OpenMC MG macro flux using a damped flux-ratio update. The "
            "two flux sources should use the same geometry and output regions."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument("-o", "--output", type=Path, required=True, help="SPH CSV table output path")
    parser.add_argument(
        "--reference-flux",
        required=True,
        help="OpenMC CE reference flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--low-order-flux",
        required=True,
        help="OpenMC MG macro flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--previous-sph",
        default=None,
        help="previous SPH CSV or HDF5 sidecar/source; defaults to unity",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=1.0,
        help="multiplicative update damping in 0..1 (default: 1.0)",
    )
    parser.add_argument(
        "--clip-min",
        type=float,
        default=None,
        help="minimum SPH value after update",
    )
    parser.add_argument(
        "--clip-max",
        type=float,
        default=None,
        help="maximum SPH value after update",
    )
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="none",
        help=(
            "scale low-order flux before forming the SPH ratio: none, total, "
            "power, or auto using group-wise H-FACTOR/kappa_fission "
            "(default: none)"
        ),
    )
    parser.add_argument(
        "--source-label",
        default="openmc-ce-mg-sph",
        help="provenance label recorded in the summary JSON",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable SPH iteration summary JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the SPH CSV output if it already exists",
    )
    return parser


def build_extract_donjon_volume_flux_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon extract-donjon-volume-flux",
        description=(
            "Extract DONJON L_FLUX scalar unknowns from a UTL dump into the "
            "canonical HDF5 volume-flux layout consumed by SPH iteration."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 handoff used for metadata")
    parser.add_argument(
        "--flux-dump",
        type=Path,
        required=True,
        help="DONJON result containing a UTL L_FLUX dump",
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="volume-flux HDF5")
    parser.add_argument(
        "--map-h5",
        type=Path,
        default=None,
        help=(
            "HDF5 map containing /scalar_flux_ids, or /kn plus /mixture_names; "
            "mutually exclusive with --scalar-flux-map"
        ),
    )
    parser.add_argument(
        "--scalar-flux-map",
        default=None,
        help=(
            "comma-separated one-based DONJON scalar flux IDs, for example "
            "fuel=1,moderator=2; mutually exclusive with --map-h5"
        ),
    )
    parser.add_argument(
        "--kn-column",
        type=int,
        default=1,
        help="one-based /kn column containing scalar flux IDs when --map-h5 uses /kn (default: 1)",
    )
    parser.add_argument(
        "--list-offset",
        type=int,
        default=0,
        help="number of unnamed real list vectors to skip before group 1 (default: 0)",
    )
    parser.add_argument(
        "--source-label",
        default="DONJON L_FLUX scalar unknown extraction",
        help="provenance label stored in output metadata",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write a machine-readable extraction summary JSON",
    )
    parser.add_argument("--force", action="store_true", help="overwrite output if it exists")
    return parser


def build_run_sph_iteration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon run-sph-iteration",
        description=(
            "Run one fixed-OpenMC SPH iteration from a DONJON L_FLUX dump: "
            "extract volume flux, compute the next SPH table, write a sidecar, "
            "inject it into MGXS, and convert the augmented handoff."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="immutable base MGXS HDF5 handoff")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="directory for generated flux, SPH, augmented MGXS, ASCII, and summary artifacts",
    )
    parser.add_argument(
        "--reference-flux",
        required=True,
        help="reference OpenMC flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--flux-dump",
        type=Path,
        required=True,
        help="DONJON result containing a UTL L_FLUX dump",
    )
    parser.add_argument(
        "--map-h5",
        type=Path,
        default=None,
        help=(
            "HDF5 map containing /scalar_flux_ids, or /kn plus /mixture_names; "
            "mutually exclusive with --scalar-flux-map"
        ),
    )
    parser.add_argument(
        "--scalar-flux-map",
        default=None,
        help="comma-separated one-based DONJON scalar flux IDs, for example fuel=1,mod=2",
    )
    parser.add_argument(
        "--kn-column",
        type=int,
        default=1,
        help="one-based /kn column containing scalar flux IDs when --map-h5 uses /kn (default: 1)",
    )
    parser.add_argument(
        "--list-offset",
        type=int,
        default=0,
        help="number of unnamed real list vectors to skip before group 1 (default: 0)",
    )
    parser.add_argument(
        "--previous-sph",
        default=None,
        help="previous SPH CSV or HDF5 sidecar/source; defaults to unity",
    )
    parser.add_argument(
        "--damping",
        type=float,
        default=1.0,
        help="multiplicative update damping in 0..1 (default: 1.0)",
    )
    parser.add_argument("--clip-min", type=float, default=None, help="minimum SPH value")
    parser.add_argument("--clip-max", type=float, default=None, help="maximum SPH value")
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="none",
        help=(
            "scale DONJON flux before forming the SPH ratio: none, total, "
            "power, or auto using group-wise H-FACTOR/kappa_fission "
            "(default: none)"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("macrolib", "multicompo"),
        default="macrolib",
        help="final DONJON ASCII output format (default: macrolib)",
    )
    parser.add_argument(
        "--root-name",
        default=DEFAULT_ROOT_NAME,
        help=f"top-level LCM directory name for --format multicompo (default: {DEFAULT_ROOT_NAME})",
    )
    parser.add_argument(
        "--h-factor-default",
        type=float,
        default=None,
        help="write this constant H-FACTOR when the input HDF5 does not provide one",
    )
    parser.add_argument(
        "--sph-kind",
        default="sph-iteration",
        help="root sph_kind provenance attribute for the sidecar and augmented HDF5",
    )
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default="true",
        help="root sph_real provenance attribute (default: true)",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default="false",
        help="root sph_applied provenance attribute (default: false)",
    )
    parser.add_argument(
        "--source-label",
        default="DONJON low-order SPH iteration workflow",
        help="provenance label stored in generated summaries and SPH metadata",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="workflow summary JSON path (default: OUTPUT_DIR/sph_iteration_workflow_summary.json)",
    )
    parser.add_argument("--force", action="store_true", help="overwrite generated artifacts")
    return parser


def build_run_sph_loop_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon run-sph-loop",
        description=(
            "Run a fixed-OpenMC SPH loop from a JSON config: write the initial "
            "ASCII handoff, call a user-supplied DONJON solve command each "
            "cycle, extract L_FLUX, update SPH, and write the next handoff."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="JSON loop config using schema openmc2donjon.sph-loop-config.v1",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="override output_dir from the config",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="override summary JSON path (default: OUTPUT_DIR/sph_loop_summary.json)",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=None,
        help="write a manifest-backed SPH loop delivery bundle in this directory",
    )
    parser.add_argument(
        "--bundle-manifest-name",
        default="manifest.json",
        help="SPH loop bundle manifest filename (default: manifest.json)",
    )
    parser.add_argument("--force", action="store_true", help="overwrite generated artifacts")
    return parser


def build_make_donjon_sph_loop_config_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-donjon-sph-loop-config",
        description=(
            "Write a run-sph-loop JSON config that uses the packaged DONJON "
            "deck runner.  Supply the fixed OpenMC MGXS HDF5, the case-specific "
            "DONJON solve template, and an HDF5 flux map containing DONJON "
            "scalar-flux IDs."
        ),
    )
    parser.add_argument("--output", type=Path, required=True, help="config JSON to write")
    parser.add_argument("--output-dir", type=Path, required=True, help="SPH loop run directory")
    parser.add_argument("--mgxs", type=Path, required=True, help="fixed OpenMC MGXS HDF5")
    parser.add_argument(
        "--solve-template",
        type=Path,
        required=True,
        help="case-specific DONJON solve deck template; must dump L_FLUX",
    )
    parser.add_argument(
        "--flux-map",
        type=Path,
        required=True,
        help=(
            "HDF5 with scalar_flux_ids metadata; also used as the default "
            "reference flux source via ::openmc_volume_flux"
        ),
    )
    parser.add_argument(
        "--reference-flux",
        default=None,
        help=(
            "reference flux source as file.h5 or file.h5::dataset "
            "(default: --flux-map::openmc_volume_flux)"
        ),
    )
    parser.add_argument(
        "--donjon-root",
        type=Path,
        default=Path("/Users/wen/dragon-5.1/Donjon"),
        help="DONJON installation root containing rdonjon",
    )
    parser.add_argument(
        "--apply-template",
        type=Path,
        default=None,
        help="DONJON DSPH/MAC apply template (default: packaged template)",
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--clip-min", type=float, default=0.5)
    parser.add_argument("--clip-max", type=float, default=3.0)
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="auto",
        help=(
            "scale DONJON flux before forming SPH ratios: auto, none, total, "
            "or power using group-wise H-FACTOR/kappa_fission (default: auto)"
        ),
    )
    parser.add_argument(
        "--sph-change-tolerance",
        type=float,
        default=None,
        help="optional early-stop tolerance on max relative SPH change",
    )
    parser.add_argument(
        "--flux-ratio-tolerance",
        type=float,
        default=None,
        help="optional early-stop tolerance on max |low_order/reference - 1|",
    )
    parser.add_argument(
        "--min-iterations",
        type=int,
        default=1,
        help="minimum SPH update cycles before convergence can stop the loop",
    )
    parser.add_argument(
        "--fail-on-nonconvergence",
        action="store_true",
        help=(
            "make run-sph-loop return an error if configured convergence "
            "targets are not met; independent of the acceptance preset"
        ),
    )
    add_sph_loop_acceptance_args(parser)
    parser.add_argument("--case-id-prefix", default="openmc2donjon_sph_loop")
    parser.add_argument("--stage-prefix", default="odj_sph_loop")
    parser.add_argument(
        "--case-dir",
        default="openmc2donjon/case_runs/openmc2donjon_sph_loop",
        help="DONJON data-relative directory where rendered decks are written",
    )
    parser.add_argument(
        "--format",
        choices=("macrolib", "multicompo"),
        default="macrolib",
        help="ASCII handoff format used between loop iterations",
    )
    parser.add_argument("--root-name", default=None, help="root name for multicompo output")
    parser.add_argument("--h-factor-default", type=float, default=None)
    parser.add_argument("--sph-kind", default="donjon-sph-loop")
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default="false",
        help="SPH provenance flag stored in generated sidecars",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default="false",
        help="SPH provenance flag stored in generated sidecars",
    )
    parser.add_argument("--source-label", default="Generic DONJON SPH loop")
    parser.add_argument("--postprocess-output", default="corrected.macrolib.txt")
    parser.add_argument(
        "--no-final-solve",
        action="store_true",
        help="do not run the final DONJON solve after the last SPH update",
    )
    return parser


def build_make_sph_loop_scaffold_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon make-sph-loop-scaffold",
        description=(
            "Write the OpenMC-side inputs needed by run-sph-loop: canonical "
            "OpenMC reference flux HDF5, DONJON scalar-flux map HDF5, and a "
            "DONJON-backed loop_config.json."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="OpenMC MGXS HDF5 handoff")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--reference-flux",
        required=True,
        help="OpenMC reference flux source as CSV, HDF5, or file.h5::dataset",
    )
    parser.add_argument(
        "--solve-template",
        type=Path,
        required=True,
        help="case-specific DONJON solve deck template; must dump L_FLUX",
    )
    parser.add_argument(
        "--scalar-flux-map",
        default=None,
        help="comma-separated DONJON scalar unknown ids, e.g. FUEL=1,MOD=2",
    )
    parser.add_argument(
        "--sequential-scalar-flux-map",
        action="store_true",
        help=(
            "write scalar_flux_ids=1..N in MGXS mixture order; suitable only "
            "for simple decks whose scalar unknowns follow that order"
        ),
    )
    parser.add_argument("--reference-output", type=Path, default=None)
    parser.add_argument("--flux-map-output", type=Path, default=None)
    parser.add_argument("--config-output", type=Path, default=None)
    parser.add_argument("--run-script-output", type=Path, default=None)
    parser.add_argument("--loop-output-dir", type=Path, default=None)
    parser.add_argument(
        "--donjon-root",
        type=Path,
        default=Path("/Users/wen/dragon-5.1/Donjon"),
        help="DONJON installation root containing rdonjon",
    )
    parser.add_argument(
        "--apply-template",
        type=Path,
        default=None,
        help="DONJON DSPH/MAC apply template (default: packaged template)",
    )
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--clip-min", type=float, default=0.5)
    parser.add_argument("--clip-max", type=float, default=3.0)
    parser.add_argument(
        "--flux-normalization",
        choices=FLUX_NORMALIZATIONS,
        default="auto",
        help=(
            "scale DONJON flux before forming SPH ratios: auto, none, total, "
            "or power using group-wise H-FACTOR/kappa_fission (default: auto)"
        ),
    )
    parser.add_argument(
        "--sph-change-tolerance",
        type=float,
        default=None,
        help="optional early-stop target on max relative SPH change",
    )
    parser.add_argument(
        "--flux-ratio-tolerance",
        type=float,
        default=None,
        help="optional early-stop target on max |low_order/reference - 1|",
    )
    parser.add_argument(
        "--min-iterations",
        type=int,
        default=1,
        help="minimum SPH update cycles before convergence can stop the loop",
    )
    parser.add_argument(
        "--fail-on-nonconvergence",
        action="store_true",
        help=(
            "make run-sph-loop return an error if configured convergence "
            "targets are not met; independent of the acceptance preset"
        ),
    )
    add_sph_loop_acceptance_args(parser)
    parser.add_argument("--case-id-prefix", default="openmc2donjon_sph_loop")
    parser.add_argument("--stage-prefix", default="odj_sph_loop")
    parser.add_argument(
        "--case-dir",
        default="openmc2donjon/case_runs/openmc2donjon_sph_loop",
        help="DONJON data-relative directory where rendered decks are written",
    )
    parser.add_argument(
        "--format",
        choices=("macrolib", "multicompo"),
        default="macrolib",
        help="ASCII handoff format used between loop iterations",
    )
    parser.add_argument("--root-name", default=None)
    parser.add_argument("--h-factor-default", type=float, default=None)
    parser.add_argument("--sph-kind", default="donjon-sph-loop")
    parser.add_argument(
        "--sph-real",
        choices=("true", "false"),
        default="false",
        help="SPH provenance flag stored in generated sidecars",
    )
    parser.add_argument(
        "--sph-applied",
        choices=("true", "false"),
        default="false",
        help="SPH provenance flag stored in generated sidecars",
    )
    parser.add_argument("--source-label", default="OpenMC SPH loop scaffold")
    parser.add_argument("--postprocess-output", default="corrected.macrolib.txt")
    parser.add_argument(
        "--no-final-solve",
        action="store_true",
        help="do not run the final DONJON solve after the last SPH update",
    )
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="overwrite generated artifacts")
    return parser


def augment_sph_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        augment_hdf5_with_sph(
            args.input_h5,
            sph_source=args.sph_source,
            output_h5=args.output,
            force=args.force,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real,
            sph_applied=args.sph_applied,
            sph_source_label=args.sph_source_label,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "augment-sph", exc)
    return 0


def make_sph_sidecar_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.mode == "unity":
            create_unity_sph_sidecar(
                args.input_h5,
                args.output,
                value=args.value,
                force=args.force,
                sph_kind=args.sph_kind or "unity",
                sph_real=False if args.sph_real is None else args.sph_real == "true",
                sph_applied=False if args.sph_applied is None else args.sph_applied == "true",
                summary_json=args.summary_json,
            )
        elif args.mode == "macrolib":
            if args.macrolib is None:
                parser.error("--mode macrolib requires --macrolib")
            create_macrolib_sph_sidecar(
                args.input_h5,
                args.output,
                macrolib_ascii=args.macrolib,
                force=args.force,
                sph_kind=args.sph_kind or "macrolib-nsph",
                sph_real=True if args.sph_real is None else args.sph_real == "true",
                sph_applied=False if args.sph_applied is None else args.sph_applied == "true",
                summary_json=args.summary_json,
            )
        elif args.mode == "table":
            if args.table is None:
                parser.error("--mode table requires --table")
            create_table_sph_sidecar(
                args.input_h5,
                args.output,
                table=args.table,
                force=args.force,
                sph_kind=args.sph_kind or "external-table",
                sph_real=True if args.sph_real is None else args.sph_real == "true",
                sph_applied=False if args.sph_applied is None else args.sph_applied == "true",
                summary_json=args.summary_json,
            )
        else:
            parser.error(f"unsupported --mode: {args.mode}")
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-sph-sidecar", exc)
    return 0


def make_sph_update_table_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        create_sph_update_table(
            args.input_h5,
            args.output,
            reference_flux=args.reference_flux,
            low_order_flux=args.low_order_flux,
            previous_sph=args.previous_sph,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-sph-update-table", exc)
    return 0


def extract_donjon_volume_flux_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.map_h5 is not None and args.scalar_flux_map is not None:
            parser.error("--map-h5 and --scalar-flux-map are mutually exclusive")
        scalar_flux_ids = (
            None if args.scalar_flux_map is None else parse_scalar_flux_map(args.scalar_flux_map)
        )
        extract_donjon_volume_flux(
            args.input_h5,
            args.flux_dump,
            args.output,
            map_h5=args.map_h5,
            scalar_flux_ids=scalar_flux_ids,
            scalar_flux_column=args.kn_column - 1,
            list_offset=args.list_offset,
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "extract-donjon-volume-flux", exc)
    return 0


def run_sph_iteration_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.map_h5 is not None and args.scalar_flux_map is not None:
            parser.error("--map-h5 and --scalar-flux-map are mutually exclusive")
        scalar_flux_ids = (
            None if args.scalar_flux_map is None else parse_scalar_flux_map(args.scalar_flux_map)
        )
        run_sph_iteration_workflow(
            args.input_h5,
            args.output_dir,
            reference_flux=args.reference_flux,
            flux_dump=args.flux_dump,
            map_h5=args.map_h5,
            scalar_flux_ids=scalar_flux_ids,
            scalar_flux_column=args.kn_column - 1,
            list_offset=args.list_offset,
            previous_sph=args.previous_sph,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            output_format=args.format,
            root_name=args.root_name,
            h_factor_default=args.h_factor_default,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real == "true",
            sph_applied=args.sph_applied == "true",
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "run-sph-iteration", exc)
    return 0


def run_sph_loop_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        run_sph_loop(
            args.config,
            output_dir=args.output_dir,
            force=args.force,
            summary_json=args.summary_json,
            bundle_dir=args.bundle_dir,
            bundle_manifest_name=args.bundle_manifest_name,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "run-sph-loop", exc)
    return 0


def make_donjon_sph_loop_config_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        path = write_donjon_sph_loop_config(
            args.output,
            input_h5=args.mgxs,
            output_dir=args.output_dir,
            solve_template=args.solve_template,
            apply_template=args.apply_template,
            flux_map=args.flux_map,
            reference_flux=args.reference_flux,
            output_format=args.format,
            final_solve=not args.no_final_solve,
            iterations=args.iterations,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            sph_change_tolerance=args.sph_change_tolerance,
            flux_ratio_tolerance=args.flux_ratio_tolerance,
            min_iterations=args.min_iterations,
            fail_on_nonconvergence=args.fail_on_nonconvergence,
            donjon_root=args.donjon_root,
            python_bin=args.python_bin,
            case_id_prefix=args.case_id_prefix,
            stage_prefix=args.stage_prefix,
            case_dir=args.case_dir,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real == "true",
            sph_applied=args.sph_applied == "true",
            source_label=args.source_label,
            postprocess_output=args.postprocess_output,
            root_name=args.root_name,
            h_factor_default=args.h_factor_default,
            acceptance=sph_loop_acceptance_from_args(args),
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-donjon-sph-loop-config", exc)
    print(f"DONJON SPH loop config: {path}")
    return 0


def make_sph_loop_scaffold_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        scalar_flux_ids = None
        if args.scalar_flux_map is not None:
            scalar_flux_ids = parse_scalar_flux_map(args.scalar_flux_map)
        create_sph_loop_scaffold(
            args.input_h5,
            args.output_dir,
            reference_flux=args.reference_flux,
            solve_template=args.solve_template,
            scalar_flux_ids=scalar_flux_ids,
            sequential_scalar_flux_map=args.sequential_scalar_flux_map,
            reference_output=args.reference_output,
            flux_map_output=args.flux_map_output,
            config_output=args.config_output,
            run_script_output=args.run_script_output,
            loop_output_dir=args.loop_output_dir,
            output_format=args.format,
            final_solve=not args.no_final_solve,
            iterations=args.iterations,
            damping=args.damping,
            clip_min=args.clip_min,
            clip_max=args.clip_max,
            flux_normalization=args.flux_normalization,
            sph_change_tolerance=args.sph_change_tolerance,
            flux_ratio_tolerance=args.flux_ratio_tolerance,
            min_iterations=args.min_iterations,
            fail_on_nonconvergence=args.fail_on_nonconvergence,
            donjon_root=args.donjon_root,
            apply_template=args.apply_template,
            python_bin=args.python_bin,
            case_id_prefix=args.case_id_prefix,
            stage_prefix=args.stage_prefix,
            case_dir=args.case_dir,
            sph_kind=args.sph_kind,
            sph_real=args.sph_real == "true",
            sph_applied=args.sph_applied == "true",
            source_label=args.source_label,
            postprocess_output=args.postprocess_output,
            root_name=args.root_name,
            h_factor_default=args.h_factor_default,
            acceptance=sph_loop_acceptance_from_args(args),
            force=args.force,
            summary_json=args.summary_json,
        )
    except USER_FACING_EXCEPTIONS as exc:
        exit_with_command_error(parser, "make-sph-loop-scaffold", exc)
    return 0
