import { describe, expect, it } from "vitest";
import {
  ADF_WORKFLOW_STEPS,
  adfWorkflowSteps,
  isAdfEquivalenceKind,
} from "./adfWorkflow";
import {
  buildEquivalenceCli,
  defaultEquivalenceOptions,
} from "./equivalenceCommand";

describe("adfWorkflow", () => {
  it("shows the ADF/DF sidecar route in execution order", () => {
    expect(ADF_WORKFLOW_STEPS.map((step) => step.id)).toEqual([
      "adf-sidecar",
      "augment",
      "convert",
    ]);
    expect(ADF_WORKFLOW_STEPS.map((step) => step.commandId)).toEqual([
      "make-adf-sidecar",
      "augment-adf",
      "direct-convert",
    ]);
  });

  it("deep-links the make and augment steps to their /equivalence tabs", () => {
    const [make, augment, convert] = ADF_WORKFLOW_STEPS;

    expect(make.href).toBe("/equivalence?kind=adf-sidecar");
    expect(augment.href).toBe("/equivalence?kind=augment-adf");
    expect(convert.href).toContain("/convert?");
  });

  it("chains artifact filenames from step to step", () => {
    const [make, augment, convert] = ADF_WORKFLOW_STEPS;

    expect(make.cli).toContain("-o adf_sidecar.h5");
    expect(augment.cli).toContain("--adf-source adf_sidecar.h5");
    expect(augment.cli).toContain("-o mgxs_with_adf.h5");
    expect(convert.cli).toContain("mgxs_with_adf.h5");
  });

  it("keeps the canned make/augment CLIs pinned to the /equivalence form", () => {
    // Parity rule (same pattern as the SPH panel naming tests): the
    // panel's canned command must equal what the live form builds from
    // its own defaults, so neither can drift silently.
    const [make, augment] = ADF_WORKFLOW_STEPS;

    expect(make.cli).toBe(
      buildEquivalenceCli({
        ...defaultEquivalenceOptions("adf-sidecar"),
        inputH5: "mgxs_library.h5",
        adfMode: "flux-ratio",
        surfaceFlux: "face_flux.h5",
        homogeneousFaceFlux: "homogeneous_face_flux.h5",
      }),
    );
    expect(augment.cli).toBe(
      buildEquivalenceCli({
        ...defaultEquivalenceOptions("augment-adf"),
        inputH5: "mgxs_library.h5",
        adfSource: "adf_sidecar.h5",
      }),
    );
  });

  it("marks only the matching step active", () => {
    expect(
      adfWorkflowSteps("make-adf-sidecar")
        .filter((step) => step.active)
        .map((step) => step.id),
    ).toEqual(["adf-sidecar"]);
    expect(
      adfWorkflowSteps("augment-adf")
        .filter((step) => step.active)
        .map((step) => step.id),
    ).toEqual(["augment"]);
    expect(adfWorkflowSteps(null).some((step) => step.active)).toBe(false);
  });

  it("recognizes only the ADF equivalence kinds", () => {
    expect(isAdfEquivalenceKind("adf-sidecar")).toBe(true);
    expect(isAdfEquivalenceKind("augment-adf")).toBe(true);
    expect(isAdfEquivalenceKind("openmc-sph-sidecar")).toBe(false);
    expect(isAdfEquivalenceKind("augment-sph")).toBe(false);
    expect(isAdfEquivalenceKind("sph-sidecar")).toBe(false);
  });
});
