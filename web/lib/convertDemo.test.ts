import { describe, expect, it } from "vitest";
import { C5G7_PRODUCTION_DEMO } from "./convertDemo";

describe("convert demo presets", () => {
  it("uses the mock C5G7 handoff with production gates enabled", () => {
    expect(C5G7_PRODUCTION_DEMO.inputPath).toBe(
      "/mock/home/openmc-runs/c5g7/handoff.h5",
    );
    expect(C5G7_PRODUCTION_DEMO.outputPath).toBe(
      "/mock/home/openmc-runs/c5g7/out.mcompo.txt",
    );
    expect(C5G7_PRODUCTION_DEMO.format).toBe("multicompo");
    expect(C5G7_PRODUCTION_DEMO.check).toBe(true);
    expect(C5G7_PRODUCTION_DEMO.production).toBe(true);
  });
});
