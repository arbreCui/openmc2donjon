import { describe, expect, it } from "vitest";
import {
  C5G7_PRODUCTION_DEMO,
  PRODUCTION_MINICASE_ARTIFACTS,
  PRODUCTION_MINICASE_COMMAND,
  PRODUCTION_MINICASE_DEMO,
  PRODUCTION_MINICASE_RUN_ROOT,
  convertDemoBundleHref,
  convertDemoHref,
  convertDemoInspectHref,
  convertDemoPreviewHref,
  convertDemoRequest,
  convertDemoWalkthrough,
  isProductionMinicasePath,
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

  it("documents the live minicase artifacts used by the web walkthrough", () => {
    expect(PRODUCTION_MINICASE_ARTIFACTS.map((artifact) => artifact.id)).toEqual([
      "run-root",
      "mgxs",
      "ascii",
      "bundle",
    ]);
    expect(PRODUCTION_MINICASE_ARTIFACTS[0].path).toBe(PRODUCTION_MINICASE_RUN_ROOT);
    expect(PRODUCTION_MINICASE_ARTIFACTS[1].href).toContain("/inspect?");
    expect(PRODUCTION_MINICASE_ARTIFACTS[2].href).toContain("/convert?");
    expect(PRODUCTION_MINICASE_ARTIFACTS[3].href).toContain(
      "/builder?command=bundle",
    );
  });

  it("detects paths inside the production minicase run root", () => {
    expect(isProductionMinicasePath(`${PRODUCTION_MINICASE_RUN_ROOT}/x.h5`)).toBe(
      true,
    );
    expect(isProductionMinicasePath("/tmp/other/x.h5")).toBe(false);
  });

  it("builds stable deep links for the converter walkthrough", () => {
    expect(convertDemoInspectHref(C5G7_PRODUCTION_DEMO)).toBe(
      "/inspect?path=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5",
    );
    expect(convertDemoHref(C5G7_PRODUCTION_DEMO)).toBe(
      "/convert?intent=direct-convert&input=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5&output=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fout.mcompo.txt&format=multicompo&check=1&production=1&require_known_mesh=0&comment=C5G7+production+demo+web+walkthrough",
    );
    expect(convertDemoBundleHref(C5G7_PRODUCTION_DEMO)).toBe(
      "/builder?command=bundle&output_dir=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fbundle&mgxs=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5&mcompo=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fout.mcompo.txt",
    );
    expect(convertDemoPreviewHref(C5G7_PRODUCTION_DEMO)).toBe(
      "#ascii-output-preview",
    );
  });

  it("builds the one-click mock dry-run request", () => {
    expect(
      convertDemoRequest(C5G7_PRODUCTION_DEMO, {
        dryRun: true,
        comment: "C5G7 mock production demo",
      }),
    ).toMatchObject({
      input_path: "/mock/home/openmc-runs/c5g7/handoff.h5",
      output_path: "/mock/home/openmc-runs/c5g7/out.mcompo.txt",
      format: "multicompo",
      dry_run: true,
      overwrite: false,
      check: true,
      production: true,
      require_known_energy_mesh: false,
      root_name: "CPO",
      comment: "C5G7 mock production demo",
    });
  });

  it("builds the one-click mock convert request from the same preset", () => {
    expect(
      convertDemoRequest(C5G7_PRODUCTION_DEMO, {
        dryRun: false,
        comment: "C5G7 mock production demo",
      }),
    ).toMatchObject({
      input_path: "/mock/home/openmc-runs/c5g7/handoff.h5",
      output_path: "/mock/home/openmc-runs/c5g7/out.mcompo.txt",
      dry_run: false,
      overwrite: false,
      check: true,
      production: true,
      comment: "C5G7 mock production demo",
    });
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
    expect(steps[3].href).toContain("/builder?command=bundle");
  });
});
