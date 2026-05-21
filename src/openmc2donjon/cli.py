"""Command line entry point for OpenMC MGXS to DONJON ASCII conversion."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .commands import adf, diagnostics
from .commands.base import CommandSpec, parser_from_args
from .donjon_flux import extract_donjon_volume_flux
from .donjon_sph_config import write_donjon_sph_loop_config
from .macrolib import convert_mgxs_hdf5_to_macrolib
from .mgxs_input_contract import run_preflight
from .multicompo import DEFAULT_ROOT_NAME, convert_mgxs_hdf5
from .sph_augment import (
    augment_hdf5_with_sph,
    create_macrolib_sph_sidecar,
    create_table_sph_sidecar,
    create_unity_sph_sidecar,
)
from .sph_iteration import create_sph_update_table
from .sph_loop import run_sph_loop
from .sph_workflow import run_sph_iteration_workflow


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
            "'openmc2donjon check-face-flux <input_h5> ...' to validate "
            "flux-ratio ADF face-flux inputs, "
            "'openmc2donjon make-homogeneous-face-flux <input_h5> ...' to "
            "reconstruct homogeneous face fluxes, 'openmc2donjon "
            "make-adf-sidecar <input_h5> ...' to create an ADF "
            "sidecar, 'openmc2donjon augment-adf <input_h5> ...' to inject "
            "computed discontinuity factors, 'openmc2donjon make-sph-sidecar "
            "<input_h5> ...', 'openmc2donjon make-sph-update-table "
            "<input_h5> ...', and 'openmc2donjon augment-sph <input_h5> ...' "
            "to iterate and carry SPH equivalence factors, "
            "'openmc2donjon extract-donjon-volume-flux <input_h5> ...' to "
            "adapt DONJON L_FLUX dumps into canonical low-order volume flux, "
            "'openmc2donjon run-sph-iteration <input_h5> ...' to run one "
            "fixed-OpenMC SPH iteration handoff, "
            "'openmc2donjon run-sph-loop --config loop.json' to iterate "
            "DONJON solves and SPH handoffs, "
            "'openmc2donjon make-donjon-sph-loop-config ...' to write a "
            "generic DONJON-backed loop config, "
            "'openmc2donjon bundle --output-dir DIR ...' to collect "
            "production artifacts, 'openmc2donjon validate-bundle manifest.json' "
            "to validate a bundle, 'openmc2donjon doctor' for environment checks, or "
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
        "--require-sph",
        action="store_true",
        help="with --check, require SPH data for every calculation",
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
        "--check-summary-json",
        type=Path,
        default=None,
        help="with --check, write a machine-readable preflight summary JSON",
    )
    return parser


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
            "Create an SPH sidecar HDF5 from an MGXS handoff. Unity SPH is "
            "useful for plumbing; macrolib mode extracts DONJON/DRAGON NSPH "
            "factors from an L_MACROLIB ASCII dump; table mode canonicalizes "
            "external SPH factors from CSV."
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
            "Create the next external SPH CSV table from reference and "
            "low-order volume fluxes using "
            "next_sph = previous_sph * (reference_flux / low_order_flux) ** damping."
        ),
    )
    parser.add_argument("input_h5", type=Path, help="MGXS HDF5 file used for mixture/group metadata")
    parser.add_argument("-o", "--output", type=Path, required=True, help="SPH CSV table output path")
    parser.add_argument(
        "--reference-flux",
        required=True,
        help="reference flux CSV or HDF5 source, optionally PATH::DATASET",
    )
    parser.add_argument(
        "--low-order-flux",
        required=True,
        help="low-order flux CSV or HDF5 source, optionally PATH::DATASET",
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
        "--source-label",
        default="external low-order SPH iteration",
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
        "--sph-change-tolerance",
        type=float,
        default=None,
        help="optional early-stop tolerance on max relative SPH change",
    )
    parser.add_argument(
        "--flux-ratio-tolerance",
        type=float,
        default=None,
        help="optional early-stop tolerance on max |reference/low_order - 1|",
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
        help="return an error if configured convergence tolerances are not met",
    )
    parser.add_argument(
        "--acceptance-min-completed-iterations",
        type=int,
        default=None,
        help="production acceptance: require at least this many SPH update cycles",
    )
    parser.add_argument(
        "--acceptance-require-final-solve",
        action="store_true",
        help="production acceptance: require a final DONJON solve row",
    )
    parser.add_argument(
        "--acceptance-require-converged",
        action="store_true",
        help="production acceptance: require the convergence criteria to pass",
    )
    parser.add_argument(
        "--acceptance-max-sph-rel-change",
        type=float,
        default=None,
        help="production acceptance: max relative SPH change in the last update",
    )
    parser.add_argument(
        "--acceptance-max-flux-ratio-residual",
        type=float,
        default=None,
        help="production acceptance: max |reference/low_order - 1| in the last update",
    )
    parser.add_argument(
        "--acceptance-sph-minimum-floor",
        type=float,
        default=None,
        help="production acceptance: minimum allowed final SPH factor",
    )
    parser.add_argument(
        "--acceptance-sph-maximum-ceiling",
        type=float,
        default=None,
        help="production acceptance: maximum allowed final SPH factor",
    )
    parser.add_argument(
        "--acceptance-max-keff-step-pcm",
        type=float,
        default=None,
        help="production acceptance: max absolute keff step across audit rows",
    )
    parser.add_argument(
        "--acceptance-max-final-keff-delta-pcm",
        type=float,
        default=None,
        help="production acceptance: max final-vs-previous keff delta",
    )
    parser.add_argument(
        "--fail-on-acceptance-violation",
        action="store_true",
        help="return an error after writing outputs if production acceptance fails",
    )
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


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openmc2donjon",
        description="Run an openmc2donjon utility command.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show package version and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for spec in _command_specs():
        parent = spec.parser_builder()
        command_parser = subparsers.add_parser(
            spec.name,
            aliases=list(spec.aliases),
            parents=[parent],
            add_help=False,
            help=spec.help,
            description=parent.description,
        )
        command_parser.set_defaults(func=spec.handler, _parser=command_parser)
    return parser


def _command_specs() -> tuple[CommandSpec, ...]:
    return (
        *adf.command_specs(),
        CommandSpec(
            "make-sph-sidecar",
            build_make_sph_sidecar_parser,
            _make_sph_sidecar_handler,
            "create an SPH sidecar",
        ),
        CommandSpec(
            "make-sph-update-table",
            build_make_sph_update_table_parser,
            _make_sph_update_table_handler,
            "compute the next SPH update table",
        ),
        CommandSpec(
            "augment-sph",
            build_augment_sph_parser,
            _augment_sph_handler,
            "inject SPH factors into an MGXS HDF5 handoff",
        ),
        CommandSpec(
            "extract-donjon-volume-flux",
            build_extract_donjon_volume_flux_parser,
            _extract_donjon_volume_flux_handler,
            "extract DONJON L_FLUX scalar unknowns",
        ),
        CommandSpec(
            "run-sph-iteration",
            build_run_sph_iteration_parser,
            _run_sph_iteration_handler,
            "run one fixed-OpenMC SPH iteration",
        ),
        CommandSpec(
            "run-sph-loop",
            build_run_sph_loop_parser,
            _run_sph_loop_handler,
            "run a DONJON-backed fixed-OpenMC SPH loop",
        ),
        CommandSpec(
            "make-donjon-sph-loop-config",
            build_make_donjon_sph_loop_config_parser,
            _make_donjon_sph_loop_config_handler,
            "write a generic DONJON-backed SPH loop config",
        ),
        *diagnostics.command_specs(),
    )


def _command_names() -> set[str]:
    names: set[str] = set()
    for spec in _command_specs():
        names.add(spec.name)
        names.update(spec.aliases)
    return names


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if raw_argv and raw_argv[0] in _command_names():
        args = build_command_parser().parse_args(raw_argv)
        return args.func(args)
    return _convert_handler(build_parser().parse_args(raw_argv))


def _convert_handler(args: argparse.Namespace) -> int:
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
            require_sph=args.require_sph,
            expected_adf_faces=args.expected_adf_faces,
            require_transport_dataset=args.require_transport_dataset,
            require_volume=args.require_volume,
            scatter_row_balance_warn=args.scatter_row_balance_warn,
            scatter_row_balance_fail=args.scatter_row_balance_fail,
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


def _augment_sph_handler(args: argparse.Namespace) -> int:
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
    except Exception as exc:
        parser.exit(1, f"openmc2donjon augment-sph: error: {exc}\n")
    return 0


def _make_sph_sidecar_handler(args: argparse.Namespace) -> int:
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
    except Exception as exc:
        parser.exit(1, f"openmc2donjon make-sph-sidecar: error: {exc}\n")
    return 0


def _make_sph_update_table_handler(args: argparse.Namespace) -> int:
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
            source_label=args.source_label,
            force=args.force,
            summary_json=args.summary_json,
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon make-sph-update-table: error: {exc}\n")
    return 0


def _extract_donjon_volume_flux_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.map_h5 is not None and args.scalar_flux_map is not None:
            parser.error("--map-h5 and --scalar-flux-map are mutually exclusive")
        scalar_flux_ids = (
            None if args.scalar_flux_map is None else _parse_scalar_flux_map(args.scalar_flux_map)
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
    except Exception as exc:
        parser.exit(1, f"openmc2donjon extract-donjon-volume-flux: error: {exc}\n")
    return 0


def _run_sph_iteration_handler(args: argparse.Namespace) -> int:
    parser = parser_from_args(args)
    try:
        if args.map_h5 is not None and args.scalar_flux_map is not None:
            parser.error("--map-h5 and --scalar-flux-map are mutually exclusive")
        scalar_flux_ids = (
            None if args.scalar_flux_map is None else _parse_scalar_flux_map(args.scalar_flux_map)
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
    except Exception as exc:
        parser.exit(1, f"openmc2donjon run-sph-iteration: error: {exc}\n")
    return 0


def _run_sph_loop_handler(args: argparse.Namespace) -> int:
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
    except Exception as exc:
        parser.exit(1, f"openmc2donjon run-sph-loop: error: {exc}\n")
    return 0


def _make_donjon_sph_loop_config_handler(args: argparse.Namespace) -> int:
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
            acceptance=_sph_loop_acceptance_from_args(args),
        )
    except Exception as exc:
        parser.exit(1, f"openmc2donjon make-donjon-sph-loop-config: error: {exc}\n")
    print(f"DONJON SPH loop config: {path}")
    return 0


def _sph_loop_acceptance_from_args(args: argparse.Namespace) -> dict[str, object] | None:
    acceptance: dict[str, object] = {}
    optional_values = {
        "min_completed_iterations": args.acceptance_min_completed_iterations,
        "max_sph_rel_change": args.acceptance_max_sph_rel_change,
        "max_flux_ratio_residual": args.acceptance_max_flux_ratio_residual,
        "sph_minimum_floor": args.acceptance_sph_minimum_floor,
        "sph_maximum_ceiling": args.acceptance_sph_maximum_ceiling,
        "max_keff_step_pcm": args.acceptance_max_keff_step_pcm,
        "max_final_keff_delta_pcm": args.acceptance_max_final_keff_delta_pcm,
    }
    for key, value in optional_values.items():
        if value is not None:
            acceptance[key] = value
    if args.acceptance_require_final_solve:
        acceptance["require_final_solve"] = True
    if args.acceptance_require_converged:
        acceptance["require_converged"] = True
    if args.fail_on_acceptance_violation:
        acceptance["fail_on_violation"] = True
    return acceptance or None


def _parse_scalar_flux_map(raw: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        if "=" not in item:
            raise ValueError("--scalar-flux-map entries must look like mixture=id")
        name, value = (part.strip() for part in item.split("=", 1))
        if not name:
            raise ValueError("--scalar-flux-map mixture names must be non-empty")
        if name in out:
            raise ValueError(f"--scalar-flux-map repeats mixture {name!r}")
        try:
            scalar_id = int(value)
        except ValueError as exc:
            raise ValueError(f"--scalar-flux-map id for {name!r} must be an integer") from exc
        if scalar_id <= 0:
            raise ValueError(f"--scalar-flux-map id for {name!r} must be positive")
        out[name] = scalar_id
    if not out:
        raise ValueError("--scalar-flux-map must list at least one mixture=id entry")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
