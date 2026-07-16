import { OPENMC_SPH_WORKFLOW_STEPS } from "./openmcSphWorkflow";

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
    title: "Converter handoff",
    summary:
      "Use this when OpenMC already produced the corrected MGXS HDF5 and you are ready for the core Converter step that writes DONJON ASCII.",
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
        body: "Check the HDF5 contract, group structure, mixtures, and scatter; run the production checks before writing.",
        href: "/inspect",
        commandIds: ["inspect", "check", "diff"],
      },
      {
        id: "convert",
        title: "Run Converter",
        body: "Validate the Converter-ready MGXS handoff, including SPH only when the project requires it, then serialize it as L_MULTICOMPO or L_MACROLIB.",
        href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
        commandIds: ["direct-convert"],
      },
      {
        id: "deliver",
        title: "Bundle and share",
        body: "Collect the MGXS HDF5, ASCII output, summaries, and logs into a reproducible bundle.",
        href: "/builder?command=bundle",
        commandIds: ["bundle", "validate-bundle"],
      },
    ],
  },
  {
    id: "openmc-sph",
    title: "OpenMC-side SPH equivalence",
    summary:
      "Use this SPH route when a fine-reference OpenMC CE model and its homogenized MG counterpart share the same boundary and project-declared domain mapping. Iterate the physical rate-preserving factors to convergence, validate and apply them to the handoff cross sections, then enter Converter for the requested DONJON object.",
    steps: OPENMC_SPH_WORKFLOW_STEPS.map((step) => ({
      id: step.id,
      title: step.title,
      body: step.body,
      href: step.href,
      commandIds:
        step.id === "sph-sidecar"
          ? [step.commandId, "make-sph-update-table"]
          : [step.commandId],
    })),
  },
  {
    id: "adf-df",
    title: "ADF/DF sidecar equivalence",
    summary:
      "Use this when face-flux evidence produces explicit ADF/DF factors before conversion. A sidecar is a small companion HDF5 carrying ADF/DF or SPH factors.",
    steps: [
      {
        id: "drivers",
        title: "Prepare face evidence",
        body: "Export OpenMC surface currents and prepare homogeneous face-flux evidence.",
        href: "/builder?command=export-surface-flux",
        commandIds: [
          "export-surface-flux",
          "make-low-order-driver",
        ],
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
        body: "Create ADF/DF sidecars as explicit artifacts, not hidden converter behavior.",
        href: "/equivalence?kind=adf-sidecar",
        commandIds: ["make-adf-sidecar"],
      },
      {
        id: "augment",
        title: "Augment then convert",
        body: "Attach the chosen sidecar to the HDF5, then run the same converter route.",
        href: "/equivalence?kind=augment-adf",
        commandIds: ["augment-adf", "direct-convert"],
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
