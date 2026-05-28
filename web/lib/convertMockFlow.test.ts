import { describe, expect, it } from "vitest";
import { convertActionGuideSteps } from "./convertActionGuide";
import {
  C5G7_PRODUCTION_DEMO,
  convertDemoBundleHref,
  convertDemoInspectHref,
  convertDemoPreviewHref,
  convertDemoRequest,
} from "./convertDemo";

describe("mock converter user flow", () => {
  it("models Fill demo -> dry-run -> convert -> preview/bundle", () => {
    const dryRunRequest = convertDemoRequest(C5G7_PRODUCTION_DEMO, {
      dryRun: true,
      comment: "C5G7 mock production demo",
    });
    const convertRequest = convertDemoRequest(C5G7_PRODUCTION_DEMO, {
      dryRun: false,
      comment: "C5G7 mock production demo",
    });

    expect(dryRunRequest).toMatchObject({
      input_path: C5G7_PRODUCTION_DEMO.inputPath,
      output_path: C5G7_PRODUCTION_DEMO.outputPath,
      dry_run: true,
      check: true,
      production: true,
    });
    expect(convertRequest).toMatchObject({
      input_path: C5G7_PRODUCTION_DEMO.inputPath,
      output_path: C5G7_PRODUCTION_DEMO.outputPath,
      dry_run: false,
      check: true,
      production: true,
    });

    expect(
      convertActionGuideSteps({
        inputPath: C5G7_PRODUCTION_DEMO.inputPath,
        outputPath: C5G7_PRODUCTION_DEMO.outputPath,
        format: C5G7_PRODUCTION_DEMO.format,
        run: {
          kind: "ok",
          ok: true,
          dryRun: true,
          converted: false,
          outputExists: false,
          preflightOk: true,
        },
      }).map((step) => [step.id, step.status]),
    ).toEqual([
      ["dry-run", "done"],
      ["convert", "ready"],
      ["preview", "waiting"],
      ["bundle", "waiting"],
    ]);

    expect(
      convertActionGuideSteps({
        inputPath: C5G7_PRODUCTION_DEMO.inputPath,
        outputPath: C5G7_PRODUCTION_DEMO.outputPath,
        format: C5G7_PRODUCTION_DEMO.format,
        run: {
          kind: "ok",
          ok: true,
          dryRun: false,
          converted: true,
          outputExists: true,
          preflightOk: true,
        },
      }).map((step) => [step.id, step.status]),
    ).toEqual([
      ["dry-run", "done"],
      ["convert", "done"],
      ["preview", "ready"],
      ["bundle", "ready"],
    ]);

    expect(convertDemoInspectHref(C5G7_PRODUCTION_DEMO)).toContain("/inspect?");
    expect(convertDemoPreviewHref(C5G7_PRODUCTION_DEMO)).toBe(
      "#ascii-output-preview",
    );
    expect(convertDemoBundleHref(C5G7_PRODUCTION_DEMO)).toContain(
      "/builder?command=bundle",
    );
  });
});
