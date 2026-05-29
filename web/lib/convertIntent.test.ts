import { describe, expect, it } from "vitest";
import { convertIntentCopy } from "./convertIntent";

describe("convertIntentCopy", () => {
  it("explains that openmc-sph conversion consumes a corrected handoff", () => {
    const copy = convertIntentCopy("openmc-sph");

    expect(copy.title).toBe("Convert a corrected SPH handoff");
    expect(copy.body).toContain("does not recompute SPH");
    expect(copy.body).toContain("corrected HDF5");
    expect(copy.body).toContain("GROUP/*/NSPH");
    expect(copy.tone).toBe("sph");
  });
});

