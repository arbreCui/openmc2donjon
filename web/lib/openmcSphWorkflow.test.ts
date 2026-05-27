import { describe, expect, it } from "vitest";
import {
  OPENMC_SPH_WORKFLOW_STEPS,
  isOpenmcSphEquivalenceKind,
  isOpenmcSphWorkflowCommand,
  openmcSphWorkflowSteps,
} from "./openmcSphWorkflow";

describe("openmcSphWorkflow", () => {
  it("shows the CE/MG OpenMC SPH route in execution order", () => {
    expect(OPENMC_SPH_WORKFLOW_STEPS.map((step) => step.id)).toEqual([
      "ce-flux",
      "mg-flux",
      "sph-sidecar",
      "augment",
      "convert",
    ]);
  });

  it("keeps CE and MG flux exports distinct", () => {
    const ce = OPENMC_SPH_WORKFLOW_STEPS.find((step) => step.id === "ce-flux");
    const mg = OPENMC_SPH_WORKFLOW_STEPS.find((step) => step.id === "mg-flux");

    expect(ce?.href).toContain("dataset_name=openmc_volume_flux");
    expect(ce?.cli).toContain("--tally-name openmc_ce_volume_flux");
    expect(mg?.href).toContain("dataset_name=openmc_mg_flux");
    expect(mg?.cli).toContain("--tally-name openmc_mg_volume_flux");
  });

  it("marks both export-volume-flux steps active on the flux builder", () => {
    const active = openmcSphWorkflowSteps("export-volume-flux").filter(
      (step) => step.active,
    );

    expect(active.map((step) => step.id)).toEqual(["ce-flux", "mg-flux"]);
  });

  it("recognizes only OpenMC-side SPH page contexts", () => {
    expect(isOpenmcSphWorkflowCommand("make-openmc-sph-sidecar")).toBe(true);
    expect(isOpenmcSphWorkflowCommand("make-sph-update-table")).toBe(true);
    expect(isOpenmcSphWorkflowCommand("export-surface-flux")).toBe(false);
    expect(isOpenmcSphEquivalenceKind("openmc-sph-sidecar")).toBe(true);
    expect(isOpenmcSphEquivalenceKind("adf-sidecar")).toBe(false);
  });

  it("treats the lower-level SPH table command as the SPH sidecar step", () => {
    const active = openmcSphWorkflowSteps("make-sph-update-table").filter(
      (step) => step.active,
    );

    expect(active.map((step) => step.id)).toEqual(["sph-sidecar"]);
  });
});
