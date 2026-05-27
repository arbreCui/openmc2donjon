import { describe, expect, it } from "vitest";
import { HOME_DEMO_SHORTCUTS } from "./demoShortcuts";

describe("home demo shortcuts", () => {
  it("offers converter, inspector, and OpenMC-side SPH demos in a stable order", () => {
    expect(HOME_DEMO_SHORTCUTS.map((entry) => entry.id)).toEqual([
      "convert-c5g7",
      "inspect-c5g7",
      "sph-sidecar",
    ]);
  });

  it("deep-links to prefilled demo pages", () => {
    const [convert, inspect, sph] = HOME_DEMO_SHORTCUTS;
    expect(convert.href).toContain("/convert?intent=direct-convert");
    expect(convert.href).toContain("input=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5");
    expect(inspect.href).toBe(
      "/inspect?path=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5",
    );
    expect(sph.href).toBe("/equivalence?kind=sph-sidecar");
  });
});
