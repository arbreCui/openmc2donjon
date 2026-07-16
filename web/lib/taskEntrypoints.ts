export interface TaskEntrypoint {
  id: "handoff" | "convert" | "consumer" | "inspect";
  step: string;
  eyebrow: string;
  title: string;
  body: string;
  artifact: string;
  href: string;
  cta: string;
}

export const TASK_ENTRYPOINTS: readonly TaskEntrypoint[] = [
  {
    id: "handoff",
    step: "01",
    eyebrow: "Project-defined source",
    title: "Prepare the handoff your model needs",
    body:
      "Export an OpenMC MGXS HDF5 with the domains, energy structure, and optional equivalence evidence required by your project.",
    artifact: "Validated project HDF5",
    href: "/openmc",
    cta: "Prepare handoff",
  },
  {
    id: "convert",
    step: "Core",
    eyebrow: "Validate → write",
    title: "Convert one exact handoff",
    body:
      "Validate one MGXS input, write L_MULTICOMPO or L_MACROLIB, and record a hash-linked receipt. Repeat only as the project manifest requires.",
    artifact: "Converter object + receipt",
    href: "/convert",
    cta: "Open Converter",
  },
  {
    id: "consumer",
    step: "Next",
    eyebrow: "Project-defined downstream",
    title: "Connect the output to its consumer",
    body:
      "Use the geometry, mixture map, solver, boundaries, and acceptance observables belonging to your DRAGON/DONJON model.",
    artifact: "Project-specific solver result",
    href: "/donjon",
    cta: "Open consumer",
  },
  {
    id: "inspect",
    step: "Close",
    eyebrow: "Acceptance",
    title: "Inspect artifacts and close the result",
    body:
      "Review manifest contracts, Converter receipts, consumer runs, and the independent closure evidence defined for this project.",
    artifact: "Auditable acceptance evidence",
    href: "/inspect",
    cta: "Inspect results",
  },
] as const;
