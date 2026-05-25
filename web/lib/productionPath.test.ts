import { describe, expect, it } from "vitest";
import { PRODUCTION_PATH_STEPS } from "./productionPath";

describe("production path steps", () => {
  it("keeps the home page path in physical workflow order", () => {
    expect(PRODUCTION_PATH_STEPS.map((step) => step.id)).toEqual([
      "direct-conversion",
      "equivalence-factors",
      "sph-loop-audit",
    ]);
  });

  it("links each step to the matching web workflow", () => {
    const [direct, equivalence, audit] = PRODUCTION_PATH_STEPS;
    expect(direct.href).toBe(
      "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    );
    expect(equivalence.href).toBe("/equivalence?kind=adf-sidecar");
    expect(audit.href).toBe("/audit");
  });
});
