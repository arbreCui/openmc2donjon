export interface WorkflowStep {
  id: string;
  title: string;
  body: string;
  href: string;
  commandIds: string[];
}

export interface WorkflowLane {
  id: string;
  title: string;
  summary: string;
  steps: WorkflowStep[];
}

export const COMMAND_WORKFLOW_LANES: readonly WorkflowLane[] = [
  {
    id: "direct",
    title: "Direct converter handoff",
    summary:
      "Use this when OpenMC already produced the MGXS HDF5 and you want the cleanest path to DONJON ASCII.",
    steps: [
      {
        id: "handoff",
        title: "Get the HDF5 handoff",
        body: "Export from OpenMC or bring an existing production MGXS file.",
        href: "/openmc?intent=export&workflow=two-step",
        commandIds: ["openmc2donjon-export", "openmc2donjon-from-openmc"],
      },
      {
        id: "inspect",
        title: "Inspect and preflight",
        body: "Check the HDF5 contract, group structure, mixtures, scatter, and production gates.",
        href: "/inspect",
        commandIds: ["inspect", "check", "diff"],
      },
      {
        id: "convert",
        title: "Write ASCII",
        body: "Convert MGXS into L_MULTICOMPO or L_MACROLIB without adding equivalence factors.",
        href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
        commandIds: ["direct-convert"],
      },
      {
        id: "deliver",
        title: "Bundle and share",
        body: "Collect source HDF5, ASCII output, summaries, and logs into a reproducible delivery.",
        href: "/builder?command=bundle",
        commandIds: ["bundle", "validate-bundle"],
      },
    ],
  },
  {
    id: "equivalence",
    title: "One-shot ADF/SPH equivalence",
    summary:
      "Use this when the direct homogenized XS need one explicit correction stage before conversion.",
    steps: [
      {
        id: "drivers",
        title: "Prepare face or flux drivers",
        body: "Export OpenMC surface currents and/or canonicalize the low-order driver data.",
        href: "/builder?command=export-surface-flux",
        commandIds: ["export-surface-flux", "make-low-order-driver"],
      },
      {
        id: "qa",
        title: "Validate driver inputs",
        body: "Check face-flux and low-order layouts before they become correction factors.",
        href: "/builder?command=check-face-flux",
        commandIds: ["check-face-flux", "check-low-order-driver", "make-homogeneous-face-flux"],
      },
      {
        id: "sidecar",
        title: "Build sidecar factors",
        body: "Create ADF/DF or SPH sidecars as explicit artifacts, not hidden converter behavior.",
        href: "/equivalence?kind=adf-sidecar",
        commandIds: ["make-adf-sidecar", "make-sph-sidecar"],
      },
      {
        id: "augment",
        title: "Augment then convert",
        body: "Inject the chosen sidecar into the HDF5, then run the same converter path.",
        href: "/equivalence?kind=augment-adf",
        commandIds: ["augment-adf", "augment-sph", "direct-convert"],
      },
    ],
  },
  {
    id: "sph-loop",
    title: "Iterative SPH loop",
    summary:
      "Use this when DONJON flux feedback should update NSPH while OpenMC remains the fixed reference.",
    steps: [
      {
        id: "reference",
        title: "Freeze OpenMC reference",
        body: "OpenMC supplies fixed MGXS and reference flux. The loop does not rerun OpenMC each iteration.",
        href: "/openmc?intent=sph-loop&workflow=one-step&production=1",
        commandIds: ["prepare-openmc-sph-loop", "make-sph-loop-scaffold"],
      },
      {
        id: "config",
        title: "Configure DONJON loop",
        body: "Point the loop at the solve template, flux map, reference flux, and convergence policy.",
        href: "/builder?command=make-donjon-sph-loop-config",
        commandIds: ["make-donjon-sph-loop-config"],
      },
      {
        id: "iterate",
        title: "Solve, compare, update",
        body: "DONJON solves the current handoff; flux mismatch updates NSPH; the converter rewrites ASCII.",
        href: "/commands/run-sph-loop",
        commandIds: ["run-sph-loop", "run-sph-iteration"],
      },
      {
        id: "manual-tools",
        title: "Manual loop tools",
        body: "Use the low-level adapters when you need to debug or customize a single loop step.",
        href: "/builder?command=extract-donjon-volume-flux",
        commandIds: ["extract-donjon-volume-flux", "make-sph-update-table", "augment-sph"],
      },
      {
        id: "audit",
        title: "Audit acceptance",
        body: "Review convergence, production acceptance, solve history, and the final delivered artifacts.",
        href: "/audit",
        commandIds: ["run-sph-loop", "bundle", "validate-bundle"],
      },
    ],
  },
] as const;

export function workflowLaneCommandIds(): string[] {
  return COMMAND_WORKFLOW_LANES.flatMap((lane) =>
    lane.steps.flatMap((step) => step.commandIds),
  );
}
