import { describe, expect, it } from "vitest";
import { TASK_ENTRYPOINTS } from "./taskEntrypoints";

describe("task entrypoints", () => {
  it("offers the three top-level user tasks in stable order", () => {
    expect(TASK_ENTRYPOINTS.map((entry) => entry.id)).toEqual([
      "direct-convert",
      "openmc-sph",
      "inspect",
    ]);
  });

  it("links each task to the intended workflow surface", () => {
    const hrefs = Object.fromEntries(
      TASK_ENTRYPOINTS.map((entry) => [entry.id, entry.href]),
    );
    expect(hrefs["direct-convert"]).toBe(
      "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    );
    expect(hrefs["openmc-sph"]).toBe(
      "/openmc?workflow=two-step&equivalence=sph&format=macrolib&production=1",
    );
    expect(hrefs.inspect).toBe("/inspect");
  });
});
