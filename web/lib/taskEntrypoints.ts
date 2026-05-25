export interface TaskEntrypoint {
  id: "openmc-export" | "direct-convert" | "equivalence" | "sph-audit";
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
}

export const TASK_ENTRYPOINTS: readonly TaskEntrypoint[] = [
  {
    id: "openmc-export",
    eyebrow: "Start from OpenMC",
    title: "Plan an OpenMC export",
    body:
      "Use the recipe/statepoint planner when OpenMC still needs to produce the MGXS HDF5 handoff.",
    href: "/openmc?workflow=two-step&production=1",
    cta: "Open planner",
  },
  {
    id: "direct-convert",
    eyebrow: "I already have HDF5",
    title: "Convert MGXS to ASCII",
    body:
      "Dry-run production gates, write L_MULTICOMPO or L_MACROLIB ASCII, then package the handoff.",
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    cta: "Open converter",
  },
  {
    id: "equivalence",
    eyebrow: "Need ADF or SPH",
    title: "Build sidecar factors",
    body:
      "Create or inject ADF/DF and SPH sidecars before returning to the same direct conversion path.",
    href: "/equivalence?kind=adf-sidecar",
    cta: "Open sidecars",
  },
  {
    id: "sph-audit",
    eyebrow: "SPH loop finished",
    title: "Review loop audit",
    body:
      "Inspect convergence diagnostics, production acceptance, solve history, and delivered artifacts.",
    href: "/audit",
    cta: "Open audit",
  },
] as const;
