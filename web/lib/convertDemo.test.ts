import { describe, expect, it } from "vitest";
import {
  C5G7_PRODUCTION_DEMO,
  PRODUCTION_MINICASE_COMMAND,
  PRODUCTION_MINICASE_DEMO,
  convertDemoHref,
  convertDemoInspectHref,
  convertDemoWalkthrough,
} from "./convertDemo";

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

  it("points the live minicase preset at the smoke-run managed output", () => {
    expect(PRODUCTION_MINICASE_COMMAND).toBe(
      "bash scripts/run_production_minicase_smoke.sh",
    );
    expect(PRODUCTION_MINICASE_DEMO.inputPath).toBe(
      "/private/tmp/openmc2donjon_production_minicase_smoke/openmc2donjon_run/mgxs_library.h5",
    );
    expect(PRODUCTION_MINICASE_DEMO.outputPath).toBe(
      "/private/tmp/openmc2donjon_production_minicase_smoke/openmc2donjon_run/web_repeat.mcompo.txt",
    );
    expect(PRODUCTION_MINICASE_DEMO.production).toBe(true);
  });

  it("builds stable deep links for the converter walkthrough", () => {
    expect(convertDemoInspectHref(C5G7_PRODUCTION_DEMO)).toBe(
      "/inspect?path=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5",
    );
    expect(convertDemoHref(C5G7_PRODUCTION_DEMO)).toBe(
      "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    );
  });

  it("describes the direct conversion walkthrough in production order", () => {
    const steps = convertDemoWalkthrough(C5G7_PRODUCTION_DEMO);
    expect(steps.map((step) => step.id)).toEqual([
      "inspect",
      "dry-run",
      "convert",
      "review",
    ]);
    expect(steps[0].href).toContain("/inspect?");
    expect(steps[2].href).toContain("/convert?");
    expect(steps[3].href).toBe("/builder?command=bundle");
  });
});
