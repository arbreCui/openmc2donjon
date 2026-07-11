export type AdfWorkflowStepId = "adf-sidecar" | "augment" | "convert";

export interface AdfWorkflowStep {
  id: AdfWorkflowStepId;
  title: string;
  badge: string;
  body: string;
  commandId: string;
  href: string;
  cli: string;
}

/**
 * The ADF/DF sidecar route as an ordered command workflow, mirroring the
 * OpenMC-side SPH panel's step model. The canned CLIs chain by filename
 * (adf_sidecar.h5 -> mgxs_with_adf.h5 -> DONJON ASCII) and the make/augment
 * steps are pinned to the /equivalence form defaults by adfWorkflow.test.ts.
 */
export const ADF_WORKFLOW_STEPS: readonly AdfWorkflowStep[] = [
  {
    id: "adf-sidecar",
    title: "Build ADF/DF sidecar",
    badge: "ADF",
    body:
      "Generate the ADF/DF sidecar from the MGXS HDF5. Unity mode is for plumbing; flux-ratio mode needs heterogeneous and homogeneous face flux.",
    commandId: "make-adf-sidecar",
    href: "/equivalence?kind=adf-sidecar",
    cli:
      "openmc2donjon make-adf-sidecar mgxs_library.h5 -o adf_sidecar.h5 " +
      "--mode flux-ratio --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX " +
      "--surface-flux face_flux.h5 --homogeneous-face-flux homogeneous_face_flux.h5",
  },
  {
    id: "augment",
    title: "Augment MGXS with ADF/DF",
    badge: "HDF5",
    body:
      "Attach the sidecar factors to the MGXS HDF5 as records — cross sections unchanged. The converter then carries the ADF blocks into DONJON ASCII.",
    commandId: "augment-adf",
    href: "/equivalence?kind=augment-adf",
    cli:
      "openmc2donjon augment-adf mgxs_library.h5 --adf-source adf_sidecar.h5 " +
      "-o mgxs_with_adf.h5 --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
  },
  {
    id: "convert",
    title: "Convert for DONJON",
    badge: "ASCII",
    body:
      "Run the normal converter on the ADF-augmented HDF5 and write the DONJON ASCII output.",
    commandId: "direct-convert",
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    cli:
      "openmc2donjon mgxs_with_adf.h5 -o out.mcompo.txt " +
      "--format multicompo --check --production",
  },
] as const;

export function isAdfEquivalenceKind(kind: string): boolean {
  return kind === "adf-sidecar" || kind === "augment-adf";
}

export function adfWorkflowSteps(
  activeCommandId: string | null,
): readonly (AdfWorkflowStep & { active: boolean })[] {
  return ADF_WORKFLOW_STEPS.map((step) => ({
    ...step,
    active: activeCommandId != null && step.commandId === activeCommandId,
  }));
}
