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
    title: "OpenMC MGXS export",
    body:
      "Use this when OpenMC already produces the multi-group HDF5 handoff. Plan export, inspect the HDF5, then convert it directly to DONJON ASCII.",
    primaryLabel: "Use direct export",
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
    title: "CE/MG SPH preparation",
    body:
      "Use this when a CE OpenMC reference and a 33-group OpenMC macro solve share the same geometry. Export both flux fields, compute SPH, inject it, then convert.",
    primaryLabel: "Use SPH preparation",
    secondaryHref: "/builder?command=export-volume-flux",
    secondaryLabel: "Build flux export",
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
