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
      "Start here when your input is an OpenMC recipe/statepoint and you still need the MGXS HDF5. If that HDF5 already exists, skip this page and open Converter.",
    primaryLabel: "Plan HDF5 export",
    secondaryHref: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    secondaryLabel: "Already have HDF5? Open Converter",
    workflow: "two-step",
    equivalence: "direct",
    production: true,
    check: true,
  },
  {
    id: "openmc-sph",
    eyebrow: "SPH equivalence",
    title: "Prepare matched CE/MG domains and their SPH",
    body:
      "Compare a fine CE reference against its homogenized MG model on the same project-declared domains, iterate rate-preserving NSPH to convergence, pre-apply the validated factors, then send that HDF5 to Converter.",
    primaryLabel: "Plan CE/MG SPH route",
    secondaryHref:
      "/openmc?workflow=two-step&equivalence=sph&format=multicompo&production=1#openmc-sph-summary",
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
