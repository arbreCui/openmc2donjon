import { describe, expect, it } from "vitest";
import { TASK_ENTRYPOINTS } from "./taskEntrypoints";

describe("task entrypoints", () => {
  it("offers generic Converter-centered product stages", () => {
    expect(TASK_ENTRYPOINTS.map((entry) => entry.id)).toEqual([
      "handoff", "convert", "consumer", "inspect",
    ]);
    const hrefs = Object.fromEntries(TASK_ENTRYPOINTS.map((entry) => [entry.id, entry.href]));
    expect(hrefs.handoff).toBe("/openmc");
    expect(hrefs.convert).toBe("/convert");
    expect(hrefs.consumer).toBe("/donjon");
    expect(hrefs.inspect).toBe("/inspect");
  });

  it("does not embed IRENA component counts in generic tasks", () => {
    const copy = JSON.stringify(TASK_ENTRYPOINTS);
    expect(copy).not.toContain("five required");
    expect(copy).not.toContain("91 positions");
    expect(copy).not.toContain("colorset=int_ext");
  });
});
