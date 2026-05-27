export interface ProductionPathStep {
  id: "openmc-equivalence" | "direct-conversion" | "delivery";
  label: string;
  title: string;
  body: string;
  result: string;
  href: string;
}

export const PRODUCTION_PATH_STEPS: readonly ProductionPathStep[] = [
  {
    id: "openmc-equivalence",
    label: "01",
    title: "OpenMC-side equivalence",
    body:
      "Use OpenMC CE as the reference and OpenMC MG 33g with the same geometry to produce corrected MGXS or SPH factors.",
    result: "corrected HDF5 / SPH sidecar",
    href: "/openmc?workflow=two-step&equivalence=sph&production=1",
  },
  {
    id: "direct-conversion",
    label: "02",
    title: "Direct conversion",
    body:
      "Inspect the corrected handoff, run production gates, and write DONJON-facing ASCII.",
    result: "L_MULTICOMPO / L_MACROLIB",
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
  },
  {
    id: "delivery",
    label: "03",
    title: "DONJON consumption",
    body:
      "Bundle the HDF5, ASCII output, summaries, and DONJON card inputs as the production record.",
    result: "reproducible handoff bundle",
    href: "/builder?command=bundle",
  },
] as const;
