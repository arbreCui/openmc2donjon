export interface ProductionPathStep {
  id: "direct-conversion" | "equivalence-factors" | "sph-loop-audit";
  label: string;
  title: string;
  body: string;
  result: string;
  href: string;
}

export const PRODUCTION_PATH_STEPS: readonly ProductionPathStep[] = [
  {
    id: "direct-conversion",
    label: "01",
    title: "Direct conversion",
    body:
      "Start from an OpenMC MGXS HDF5 handoff, run production gates, and write DONJON-facing ASCII.",
    result: "L_MULTICOMPO / L_MACROLIB",
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
  },
  {
    id: "equivalence-factors",
    label: "02",
    title: "ADF / SPH sidecars",
    body:
      "When direct homogenization bias is too large, build or inject equivalence factors before reconverting.",
    result: "augmented HDF5 handoff",
    href: "/equivalence?kind=adf-sidecar",
  },
  {
    id: "sph-loop-audit",
    label: "03",
    title: "SPH loop audit",
    body:
      "For iterative SPH, review convergence, production acceptance, solve trace, and delivered artifacts.",
    result: "accepted production record",
    href: "/audit",
  },
] as const;
