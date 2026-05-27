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

export interface WorkflowOccurrence {
  lane: WorkflowLane;
  step: WorkflowStep;
  stepIndex: number;
  previousStep: WorkflowStep | null;
  nextStep: WorkflowStep | null;
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
    title: "OpenMC-side ADF/SPH equivalence",
    summary:
      "Use this when OpenMC CE/MG evidence produces explicit ADF/DF or SPH factors before conversion.",
    steps: [
      {
        id: "drivers",
        title: "Prepare OpenMC evidence",
        body: "Export OpenMC surface currents for ADF/DF, or bring OpenMC CE/MG SPH factors for each output region and group.",
        href: "/builder?command=export-surface-flux",
        commandIds: ["export-surface-flux", "make-low-order-driver", "make-openmc-sph-sidecar"],
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
        body: "Create ADF/DF or OpenMC-side SPH sidecars as explicit artifacts, not hidden converter behavior.",
        href: "/equivalence?kind=adf-sidecar",
        commandIds: ["make-adf-sidecar", "make-openmc-sph-sidecar", "make-sph-sidecar"],
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
] as const;

export function workflowLaneCommandIds(): string[] {
  return COMMAND_WORKFLOW_LANES.flatMap((lane) =>
    lane.steps.flatMap((step) => step.commandIds),
  );
}

export function commandWorkflowOccurrences(commandId: string): WorkflowOccurrence[] {
  const occurrences: WorkflowOccurrence[] = [];
  for (const lane of COMMAND_WORKFLOW_LANES) {
    lane.steps.forEach((step, index) => {
      if (!step.commandIds.includes(commandId)) return;
      occurrences.push({
        lane,
        step,
        stepIndex: index,
        previousStep: lane.steps[index - 1] ?? null,
        nextStep: lane.steps[index + 1] ?? null,
      });
    });
  }
  return occurrences;
}
