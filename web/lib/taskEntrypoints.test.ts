import { describe, expect, it } from "vitest";
import { TASK_ENTRYPOINTS } from "./taskEntrypoints";

describe("task entrypoints", () => {
  it("offers the four top-level user tasks in stable order", () => {
    expect(TASK_ENTRYPOINTS.map((entry) => entry.id)).toEqual([
      "openmc-export",
      "direct-convert",
      "equivalence",
      "sph-audit",
    ]);
  });

  it("links each task to the intended workflow surface", () => {
    const hrefs = Object.fromEntries(
      TASK_ENTRYPOINTS.map((entry) => [entry.id, entry.href]),
    );
    expect(hrefs["openmc-export"]).toBe("/openmc?workflow=two-step&production=1");
    expect(hrefs["direct-convert"]).toBe(
      "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    );
    expect(hrefs.equivalence).toBe("/equivalence?kind=adf-sidecar");
    expect(hrefs["sph-audit"]).toBe("/audit");
  });
});
