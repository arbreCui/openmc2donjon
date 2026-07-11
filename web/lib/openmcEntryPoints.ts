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
    eyebrow: "Need HDF5 first",
    title: "Prepare OpenMC MGXS HDF5",
    body:
      "Start here when your input is an OpenMC recipe/statepoint and you still need the converter-facing MGXS HDF5. If that HDF5 already exists, skip this page and open Convert.",
    primaryLabel: "Plan HDF5 export",
    secondaryHref: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    secondaryLabel: "Already have HDF5? Convert",
    workflow: "two-step",
    equivalence: "direct",
    production: true,
    check: true,
  },
  {
    id: "openmc-sph",
    eyebrow: "OpenMC-side equivalence",
    title: "Prepare CE/MG SPH factors",
    body:
      "Start here when a colorset or core model needs equivalence before conversion: compare OpenMC CE reference flux against OpenMC MG macro flux on the same geometry/output regions, inject NSPH, then convert to MACROLIB for DONJON.",
    primaryLabel: "Plan CE/MG SPH route",
    secondaryHref:
      "/openmc?workflow=two-step&equivalence=sph&format=macrolib#openmc-sph-summary",
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
