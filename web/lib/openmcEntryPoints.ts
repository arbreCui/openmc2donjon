import type { OpenmcEquivalenceMode, OpenmcWorkflowKind } from "./api";

export type OpenmcEntryPointId = "direct-mgxs" | "openmc-sph";

export interface OpenmcEntryPoint {
  id: OpenmcEntryPointId;
  eyebrow: string;
  title: string;
  body: string;
  primaryLabel: string;
  secondaryHref: string;
  secondaryLabel: string;
  workflow: OpenmcWorkflowKind;
  equivalence: OpenmcEquivalenceMode;
  production: boolean;
  check: boolean;
}

export const OPENMC_ENTRY_POINTS: readonly OpenmcEntryPoint[] = [
  {
    id: "direct-mgxs",
    eyebrow: "Direct handoff",
    title: "Convert an OpenMC MGXS handoff",
    body:
      "Start here when you already have an OpenMC MGXS HDF5. Inspect it, dry-run production gates, then write L_MULTICOMPO or L_MACROLIB ASCII.",
    primaryLabel: "Use direct converter",
    secondaryHref: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    secondaryLabel: "Open converter",
    workflow: "two-step",
    equivalence: "direct",
    production: true,
    check: true,
  },
  {
    id: "openmc-sph",
    eyebrow: "OpenMC-side equivalence",
    title: "Run CE/MG SPH preparation",
    body:
      "Start here for Alain's route: OpenMC CE reference plus OpenMC MG as the formal equivalence operator on the selected group structure and same geometry, then MACROLIB conversion for DONJON consumption.",
    primaryLabel: "Use CE/MG SPH route",
    secondaryHref: "/openmc?workflow=two-step&equivalence=sph&format=macrolib",
    secondaryLabel: "Open SPH summary",
    workflow: "two-step",
    equivalence: "sph",
    production: true,
    check: true,
  },
] as const;

export function openmcEntryPoint(id: OpenmcEntryPointId): OpenmcEntryPoint {
  return OPENMC_ENTRY_POINTS.find((item) => item.id === id) ?? OPENMC_ENTRY_POINTS[0];
}

export function activeOpenmcEntryPoint(
  workflow: OpenmcWorkflowKind,
  equivalence: OpenmcEquivalenceMode,
): OpenmcEntryPointId {
  if (workflow === "two-step" && equivalence === "sph") return "openmc-sph";
  return "direct-mgxs";
}
