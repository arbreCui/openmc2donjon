"""Command catalog API for the localhost web UI.

The catalog is intentionally descriptive: it tells the frontend which
CLI workflows exist, how they fit into the production pipeline, and
whether a first-class web surface already exists. Command execution
stays in the dedicated workflow endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..commands import adf, diagnostics, sph, web as web_commands


COMMANDS_SCHEMA = "openmc2donjon.commands.v1"


@dataclass(frozen=True)
class CommandGroup:
    id: str
    label: str
    summary: str


@dataclass(frozen=True)
class CommandDetail:
    group: str
    title: str
    summary: str
    status: str
    status_label: str
    cli: str
    web_path: str | None = None
    tags: tuple[str, ...] = ()
    use_when: str | None = None
    produces: str | None = None
    next_step: str | None = None


@dataclass(frozen=True)
class CommandGuidance:
    use_when: str
    produces: str
    next_step: str


GROUPS: tuple[CommandGroup, ...] = (
    CommandGroup(
        "convert",
        "Direct converter",
        "Turn an OpenMC MGXS HDF5 handoff into DONJON ASCII LCM output.",
    ),
    CommandGroup(
        "inspect",
        "Inspect and preflight",
        "Understand an HDF5 handoff before conversion or compare two handoffs.",
    ),
    CommandGroup(
        "openmc",
        "OpenMC production export",
        "Build OpenMC CE/MG handoff inputs from a recipe and statepoint.",
    ),
    CommandGroup(
        "adf",
        "ADF / DF equivalence",
        "Prepare face-flux, low-order, and ADF sidecar data for one-shot equivalence.",
    ),
    CommandGroup(
        "sph",
        "OpenMC-side SPH equivalence",
        "Create and inject SPH factors produced from OpenMC CE/MG equivalence.",
    ),
    CommandGroup(
        "package",
        "Package and diagnostics",
        "Bundle artifacts, validate manifests, and check the local runtime.",
    ),
    CommandGroup(
        "web",
        "Local web service",
        "Run the localhost FastAPI backend used by the web interface.",
    ),
)


GROUP_GUIDANCE: dict[str, CommandGuidance] = {
    "convert": CommandGuidance(
        use_when="You already have an openmc2donjon MGXS HDF5 handoff and want DONJON input.",
        produces="An ASCII L_MULTICOMPO or L_MACROLIB file.",
        next_step="Preview or hand the ASCII file to DONJON; use Inspect first for suspicious HDF5 inputs.",
    ),
    "inspect": CommandGuidance(
        use_when="You need to understand or validate an HDF5 handoff before conversion.",
        produces="A metadata, mesh, mixture, and production-gate summary.",
        next_step="Fix failed gates, then convert or compare against a reference handoff.",
    ),
    "openmc": CommandGuidance(
        use_when="Your starting point is an OpenMC recipe/statepoint rather than an existing handoff HDF5.",
        produces=(
            "An MGXS HDF5 handoff, optional OpenMC-side equivalence sidecars, "
            "ASCII output, and run bundle."
        ),
        next_step="Inspect the generated HDF5 and keep the managed run directory as the production record.",
    ),
    "adf": CommandGuidance(
        use_when="You want one-shot discontinuity-factor equivalence from face-flux information.",
        produces="ADF/DF sidecar data or an ADF-augmented MGXS HDF5 handoff.",
        next_step="Convert the augmented HDF5 or use the OpenMC planner to include ADF in the handoff.",
    ),
    "sph": CommandGuidance(
        use_when=(
            "You already have SPH factors from OpenMC CE/MG equivalence "
            "and need to carry them to DONJON."
        ),
        produces="SPH sidecars and SPH-augmented HDF5 handoffs.",
        next_step=(
            "Inject the sidecar into the HDF5, then return to direct conversion."
        ),
    ),
    "package": CommandGuidance(
        use_when="You are preparing results for sharing, archiving, or runtime troubleshooting.",
        produces="A manifest-backed bundle or an environment diagnostic report.",
        next_step="Validate the bundle before sending it to another machine or collaborator.",
    ),
    "web": CommandGuidance(
        use_when="You want to use the localhost web UI instead of memorizing CLI flags.",
        produces="A FastAPI backend serving the web endpoints.",
        next_step="Open the Next.js frontend and use Convert, OpenMC, Inspect, Equivalence, or Commands.",
    ),
}


COMMAND_GUIDANCE: dict[str, CommandGuidance] = {
    "direct-convert": CommandGuidance(
        use_when="Use this first when the HDF5 handoff already exists.",
        produces=(
            "A DONJON ASCII L_MULTICOMPO or L_MACROLIB object, plus the "
            "preflight decision when checks are enabled."
        ),
        next_step=(
            "Preview the generated ASCII, then open the prefilled bundle "
            "builder before moving to DONJON consumption."
        ),
    ),
    "check": CommandGuidance(
        use_when=(
            "Use this before converting a new or changed MGXS HDF5 handoff."
        ),
        produces=(
            "A production preflight decision only; it does not write the "
            "DONJON ASCII handoff."
        ),
        next_step=(
            "If the decision is accepted, return to Convert with the same "
            "paths and write the ASCII output; otherwise fix the HDF5 input."
        ),
    ),
    "openmc2donjon-from-openmc": CommandGuidance(
        use_when="Use this when one managed command should export, check, convert, and bundle the handoff.",
        produces="HDF5, ASCII, summaries, and bundle metadata in one run directory.",
        next_step="Use the OpenMC planner to assemble the command before running it.",
    ),
    "openmc2donjon-export": CommandGuidance(
        use_when="Use this for a two-step workflow where HDF5 is archived or inspected before conversion.",
        produces="A standalone MGXS HDF5 contract file.",
        next_step="Inspect the HDF5, optionally augment it, then run direct conversion.",
    ),
    "serve": CommandGuidance(
        use_when="Use this before opening the web UI locally.",
        produces="The localhost API backend on the selected host and port.",
        next_step="Open http://localhost:3000 and keep the backend process running.",
    ),
}


DETAILS: dict[str, CommandDetail] = {
    "direct-convert": CommandDetail(
        group="convert",
        title="Direct MGXS conversion",
        summary=(
            "Convert one OpenMC MGXS HDF5 handoff to L_MULTICOMPO or "
            "L_MACROLIB ASCII, with optional production preflight."
        ),
        status="ready",
        status_label="Web form ready",
        web_path="/convert?intent=direct-convert&format=multicompo&check=1&production=1",
        cli=(
            "openmc2donjon mgxs_library.h5 --format multicompo "
            "-o out.mcompo.txt --check"
        ),
        tags=("HDF5", "MULTICOMPO", "MACROLIB"),
    ),
    "inspect": CommandDetail(
        group="inspect",
        title="Inspect MGXS handoff",
        summary="Summarize groups, mixtures, state points, mesh ID, ADF, SPH, and datasets.",
        status="ready",
        status_label="Viewer ready",
        web_path="/inspect",
        cli="openmc2donjon inspect mgxs_library.h5",
        tags=("HDF5", "mesh", "mixtures"),
    ),
    "check": CommandDetail(
        group="inspect",
        title="Production preflight",
        summary="Run the MGXS input-contract and production physics gates.",
        status="partial",
        status_label="Available inside Convert",
        web_path="/convert?intent=check&format=multicompo&check=1&production=1",
        cli="openmc2donjon check mgxs_library.h5 --production",
        tags=("preflight", "production gates"),
    ),
    "diff": CommandDetail(
        group="inspect",
        title="HDF5 handoff diff",
        summary="Compare two MGXS HDF5 handoffs for conversion-relevant differences.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=diff",
        cli="openmc2donjon diff reference.h5 candidate.h5",
        tags=("QA", "regression"),
    ),
    "openmc2donjon-export": CommandDetail(
        group="openmc",
        title="Export OpenMC MGXS HDF5",
        summary=(
            "Export an OpenMC mgxs.Library-like object or recipe/statepoint "
            "into the openmc2donjon HDF5 contract."
        ),
        status="partial",
        status_label="Workflow planner ready",
        web_path="/openmc?intent=export&workflow=two-step",
        cli="openmc2donjon-export --recipe recipe.py --statepoint statepoint.h5 -o mgxs_library.h5",
        tags=("OpenMC", "HDF5", "two-step"),
    ),
    "openmc2donjon-from-openmc": CommandDetail(
        group="openmc",
        title="One-step OpenMC handoff",
        summary=(
            "Export MGXS from an OpenMC recipe/statepoint, optionally inject "
            "ADF/SPH data, run preflight, convert, and bundle artifacts."
        ),
        status="partial",
        status_label="Workflow planner ready",
        web_path="/openmc?intent=from-openmc&workflow=one-step",
        cli="openmc2donjon-from-openmc --recipe recipe.py --statepoint statepoint.h5 -o out.mcompo.txt",
        tags=("OpenMC", "one-step", "bundle"),
    ),
    "export-surface-flux": CommandDetail(
        group="adf",
        title="Export OpenMC surface flux",
        summary="Export a MeshSurfaceFilter + MuSurfaceFilter current tally for ADF/DF work.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=export-surface-flux",
        cli="openmc2donjon export-surface-flux statepoint.h5 --output face_flux.h5",
        tags=("OpenMC", "ADF", "surface flux"),
    ),
    "export-volume-flux": CommandDetail(
        group="sph",
        title="Export OpenMC volume flux",
        summary=(
            "Export a region/group OpenMC flux tally for CE/MG SPH equivalence."
        ),
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=export-volume-flux",
        cli=(
            "openmc2donjon export-volume-flux statepoint.h5 --mgxs mgxs_library.h5 "
            "--dataset-name openmc_volume_flux -o openmc_ce_flux.h5"
        ),
        tags=("OpenMC", "SPH", "volume flux"),
        use_when=(
            "You need CE reference or MG macro flux in the canonical "
            "(mixture, group) HDF5 layout before computing OpenMC-side SPH."
        ),
        produces="A flux HDF5 source consumed by make-openmc-sph-sidecar.",
        next_step="Run it once for CE and once for MG, then build the OpenMC SPH sidecar.",
    ),
    "check-face-flux": CommandDetail(
        group="adf",
        title="Check face-flux inputs",
        summary="Validate heterogeneous and homogeneous face-flux data before ADF construction.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=check-face-flux",
        cli=(
            "openmc2donjon check-face-flux mgxs_library.h5 "
            "--surface-flux face_flux.h5 --homogeneous-face-flux homogeneous_face_flux.h5"
        ),
        tags=("ADF", "QA"),
    ),
    "make-low-order-driver": CommandDetail(
        group="adf",
        title="Make low-order driver",
        summary="Canonicalize low-order flux/current inputs used by ADF reconstruction.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=make-low-order-driver",
        cli="openmc2donjon make-low-order-driver input.h5 --output driver.h5",
        tags=("ADF", "low order"),
    ),
    "check-low-order-driver": CommandDetail(
        group="adf",
        title="Check low-order driver",
        summary="Validate a low-order handoff before using it for homogeneous face flux.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=check-low-order-driver",
        cli="openmc2donjon check-low-order-driver mgxs_library.h5 driver.h5",
        tags=("ADF", "QA"),
    ),
    "make-homogeneous-face-flux": CommandDetail(
        group="adf",
        title="Reconstruct homogeneous face flux",
        summary="Create the homogeneous face-flux side of a flux-ratio ADF definition.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=make-homogeneous-face-flux",
        cli=(
            "openmc2donjon make-homogeneous-face-flux mgxs_library.h5 "
            "-o homogeneous_face_flux.h5 --volume-flux flux.h5 --net-current current.h5"
        ),
        tags=("ADF", "face flux"),
    ),
    "make-adf-sidecar": CommandDetail(
        group="adf",
        title="Make ADF/DF sidecar",
        summary="Build an ADF/DF HDF5 sidecar from heterogeneous and homogeneous face flux.",
        status="partial",
        status_label="Command builder ready",
        web_path="/equivalence?kind=adf-sidecar",
        cli="openmc2donjon make-adf-sidecar mgxs_library.h5 --output adf_sidecar.h5",
        tags=("ADF", "sidecar"),
        use_when=(
            "You need a copyable make-adf-sidecar command for unity plumbing "
            "or flux-ratio ADF inputs."
        ),
        produces="A command that writes an ADF/DF sidecar HDF5 when run locally.",
        next_step="Run the CLI command, then inject the sidecar or include it in the OpenMC planner.",
    ),
    "augment-adf": CommandDetail(
        group="adf",
        title="Inject ADF/DF",
        summary="Add computed discontinuity factors to an MGXS HDF5 handoff before conversion.",
        status="partial",
        status_label="Command builder ready",
        web_path="/equivalence?kind=augment-adf",
        cli="openmc2donjon augment-adf mgxs_library.h5 --adf-source adf_sidecar.h5 -o augmented.h5",
        tags=("ADF", "HDF5 augment"),
        use_when="You already have an ADF/DF sidecar and need to attach it to the MGXS handoff.",
        produces="A command that writes an ADF-augmented MGXS HDF5 when run locally.",
        next_step="Convert the augmented HDF5 with the direct converter page.",
    ),
    "make-sph-sidecar": CommandDetail(
        group="sph",
        title="Make SPH sidecar",
        summary="Create a sidecar HDF5 for SPH factors produced by OpenMC CE/MG equivalence.",
        status="partial",
        status_label="Command builder ready",
        web_path="/equivalence?kind=sph-sidecar",
        cli="openmc2donjon make-sph-sidecar mgxs_library.h5 --output sph_sidecar.h5",
        tags=("SPH", "sidecar"),
        use_when=(
            "You have OpenMC-side SPH factors in a table, unity plumbing "
            "values, or a validated NSPH source and need a DONJON handoff sidecar."
        ),
        produces="A command that writes an SPH sidecar HDF5 when run locally.",
        next_step="Run the CLI command, inject the sidecar, then convert the augmented HDF5.",
    ),
    "make-openmc-sph-sidecar": CommandDetail(
        group="sph",
        title="Compute OpenMC-side SPH sidecar",
        summary=(
            "Compare OpenMC CE reference flux and OpenMC MG macro flux, then "
            "write both an auditable SPH table and sidecar HDF5."
        ),
        status="partial",
        status_label="Command builder ready",
        web_path="/equivalence?kind=openmc-sph-sidecar",
        cli=(
            "openmc2donjon make-openmc-sph-sidecar mgxs_library.h5 "
            "-o sph_sidecar.h5 --reference-flux openmc_ce_flux.h5 "
            "--mg-flux openmc_mg_flux.h5"
        ),
        tags=("SPH", "OpenMC"),
        use_when=(
            "You have OpenMC CE and OpenMC MG fluxes from the same geometry "
            "and want explicit SPH factors per output region and group."
        ),
        produces="A command that writes an SPH CSV table and sidecar HDF5 when run locally.",
        next_step=(
            "Inject the sidecar with augment-sph, then convert the augmented HDF5 "
            "with --format macrolib for DONJON DSPH/MAC consumption."
        ),
    ),
    "make-sph-update-table": CommandDetail(
        group="sph",
        title="Compute OpenMC-side SPH table",
        summary="Compare OpenMC CE reference flux and OpenMC MG macro flux to compute SPH factors.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=make-sph-update-table",
        cli=(
            "openmc2donjon make-sph-update-table mgxs_library.h5 -o sph_update.csv "
            "--reference-flux openmc_ce_flux.h5 --low-order-flux openmc_mg_flux.h5"
        ),
        tags=("SPH", "OpenMC"),
    ),
    "augment-sph": CommandDetail(
        group="sph",
        title="Inject SPH factors",
        summary="Attach SPH factors to an MGXS HDF5 handoff before deterministic conversion.",
        status="partial",
        status_label="Command builder ready",
        web_path="/equivalence?kind=augment-sph",
        cli="openmc2donjon augment-sph mgxs_library.h5 --sph-source sph_sidecar.h5 -o augmented.h5",
        tags=("SPH", "HDF5 augment"),
        use_when="You already have an SPH sidecar and need to attach it to the MGXS handoff.",
        produces="A command that writes an SPH-augmented MGXS HDF5 when run locally.",
        next_step=(
            "Convert the augmented HDF5 with the direct converter page. For "
            "OpenMC-side SPH consumed by DONJON DSPH/MAC, choose MACROLIB output."
        ),
    ),
    "bundle": CommandDetail(
        group="package",
        title="Bundle production artifacts",
        summary="Collect handoffs, ASCII outputs, summaries, and logs into a manifest-backed directory.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=bundle",
        cli="openmc2donjon bundle --output-dir bundle",
        tags=("release", "archive"),
    ),
    "validate-bundle": CommandDetail(
        group="package",
        title="Validate bundle",
        summary="Check a manifest-backed production bundle before sharing or archiving it.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=validate-bundle",
        cli="openmc2donjon validate-bundle bundle/manifest.json",
        tags=("release", "QA"),
    ),
    "doctor": CommandDetail(
        group="package",
        title="Runtime doctor",
        summary="Check Python package state and local runtime prerequisites.",
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=doctor",
        cli="openmc2donjon doctor",
        tags=("environment",),
    ),
    "pygan-doctor": CommandDetail(
        group="package",
        title="PyGan doctor",
        summary=(
            "Check whether the optional PyGan DRAGON/DONJON validation "
            "backend is available."
        ),
        status="partial",
        status_label="Web diagnostics ready",
        web_path="/pygan",
        cli="openmc2donjon pygan-doctor",
        tags=("environment", "PyGan"),
    ),
    "pygan-inspect-compo": CommandDetail(
        group="package",
        title="Inspect COMPO with PyGan",
        summary=(
            "Read a DRAGON/DONJON COMPO or MULTICOMPO through PyGan and "
            "report its LCM root structure."
        ),
        status="partial",
        status_label="Command builder ready",
        web_path="/builder?command=pygan-inspect-compo",
        cli="openmc2donjon pygan-inspect-compo FUEL30.COMPO --summary-json fuel30.pygan.json",
        tags=("PyGan", "COMPO", "validation"),
    ),
    "compare-writers": CommandDetail(
        group="package",
        title="Compare ASCII and PyGan writers",
        summary=(
            "Write the same MGXS handoff with both writer backends and compare "
            "the resulting LCM trees semantically."
        ),
        status="partial",
        status_label="Web compare ready",
        web_path="/pygan?tab=compare",
        cli="openmc2donjon compare-writers mgxs_library.h5 --format multicompo",
        tags=("PyGan", "validation", "writer"),
    ),
    "serve": CommandDetail(
        group="web",
        title="Start web backend",
        summary="Run the localhost FastAPI backend consumed by this web UI.",
        status="ready",
        status_label="Command builder ready",
        web_path="/builder?command=serve",
        cli="openmc2donjon serve --mock",
        tags=("localhost", "FastAPI"),
    ),
}


def register_command_routes(app: Any) -> None:
    @app.get("/api/commands")
    def api_commands() -> dict[str, Any]:
        return build_command_catalog()


def build_command_catalog() -> dict[str, Any]:
    commands = [_direct_convert_entry()]
    commands.extend(_entrypoint_entry(name) for name in _standalone_entrypoints())
    commands.extend(_cli_entry(spec) for spec in _cli_specs())
    group_counts = _group_counts(commands)
    groups = [
        {
            "id": group.id,
            "label": group.label,
            "summary": group.summary,
            "command_count": group_counts.get(group.id, 0),
        }
        for group in GROUPS
    ]
    status_counts: dict[str, int] = {}
    for command in commands:
        status = str(command["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema": COMMANDS_SCHEMA,
        "groups": groups,
        "commands": commands,
        "status_counts": status_counts,
    }


def _direct_convert_entry() -> dict[str, Any]:
    detail = DETAILS["direct-convert"]
    return _detail_payload(
        "direct-convert",
        "openmc2donjon <input_h5>",
        (),
        "default converter invocation",
        detail,
        kind="default",
    )


def _entrypoint_entry(name: str) -> dict[str, Any]:
    detail = DETAILS[name]
    return _detail_payload(
        name,
        name,
        (),
        detail.summary,
        detail,
        kind="entrypoint",
    )


def _cli_entry(spec: Any) -> dict[str, Any]:
    detail = DETAILS.get(
        spec.name,
        CommandDetail(
            group="package",
            title=spec.name,
            summary=spec.help,
            status="planned",
            status_label="CLI only",
            cli=f"openmc2donjon {spec.name}",
        ),
    )
    return _detail_payload(
        spec.name,
        spec.name,
        tuple(spec.aliases),
        spec.help,
        detail,
        kind="subcommand",
    )


def _detail_payload(
    command_id: str,
    name: str,
    aliases: tuple[str, ...],
    cli_help: str,
    detail: CommandDetail,
    *,
    kind: str,
) -> dict[str, Any]:
    guidance = _command_guidance(command_id, detail)
    return {
        "id": command_id,
        "kind": kind,
        "name": name,
        "aliases": list(aliases),
        "group": detail.group,
        "title": detail.title,
        "summary": detail.summary,
        "cli_help": cli_help,
        "status": detail.status,
        "status_label": detail.status_label,
        "web_path": detail.web_path,
        "cli": detail.cli,
        "tags": list(detail.tags),
        "use_when": guidance.use_when,
        "produces": guidance.produces,
        "next_step": guidance.next_step,
    }


def _command_guidance(command_id: str, detail: CommandDetail) -> CommandGuidance:
    base = COMMAND_GUIDANCE.get(command_id) or GROUP_GUIDANCE[detail.group]
    return CommandGuidance(
        use_when=detail.use_when or base.use_when,
        produces=detail.produces or base.produces,
        next_step=detail.next_step or base.next_step,
    )


def _cli_specs() -> tuple[Any, ...]:
    return (
        *adf.command_specs(),
        *sph.command_specs(),
        *diagnostics.command_specs(),
        *web_commands.command_specs(),
    )


def _standalone_entrypoints() -> tuple[str, ...]:
    return (
        "openmc2donjon-export",
        "openmc2donjon-from-openmc",
    )


def _group_counts(commands: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for command in commands:
        group = str(command["group"])
        counts[group] = counts.get(group, 0) + 1
    return counts
