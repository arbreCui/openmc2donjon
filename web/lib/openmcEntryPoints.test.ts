import { describe, expect, it } from "vitest";
import {
  OPENMC_ENTRY_POINTS,
  activeOpenmcEntryPoint,
  openmcEntryPoint,
} from "./openmcEntryPoints";

describe("openmcEntryPoints", () => {
  it("offers direct MGXS and OpenMC-side SPH as the two primary entries", () => {
    expect(OPENMC_ENTRY_POINTS.map((entry) => entry.id)).toEqual([
      "direct-mgxs",
      "openmc-sph",
    ]);
  });

  it("maps the SPH entry to two-step OpenMC-side SPH planning", () => {
    const sph = openmcEntryPoint("openmc-sph");

    expect(sph.workflow).toBe("two-step");
    expect(sph.equivalence).toBe("sph");
    expect(sph.production).toBe(true);
    expect(sph.secondaryHref).toContain("export-volume-flux");
  });

  it("identifies the active entry from the planner state", () => {
    expect(activeOpenmcEntryPoint("two-step", "sph")).toBe("openmc-sph");
    expect(activeOpenmcEntryPoint("one-step", "sph")).toBe("direct-mgxs");
    expect(activeOpenmcEntryPoint("two-step", "direct")).toBe("direct-mgxs");
  });
});
