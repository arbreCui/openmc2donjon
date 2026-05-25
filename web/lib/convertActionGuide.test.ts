import { describe, expect, it } from "vitest";
import { convertActionGuideSteps } from "./convertActionGuide";

describe("convertActionGuideSteps", () => {
  it("starts with dry run ready and downstream actions waiting when paths are known", () => {
    const steps = convertActionGuideSteps({
      inputPath: "/runs/case/mgxs.h5",
      outputPath: "/runs/case/out.mcompo.txt",
      format: "multicompo",
      run: { kind: "idle" },
    });

    expect(statuses(steps)).toEqual({
      "dry-run": "ready",
      convert: "waiting",
      preview: "waiting",
      bundle: "waiting",
    });
  });

  it("marks convert as ready after a passing dry run without claiming preview is available", () => {
    const steps = convertActionGuideSteps({
      inputPath: "/runs/case/mgxs.h5",
      outputPath: "/runs/case/out.mcompo.txt",
      format: "multicompo",
      run: {
        kind: "ok",
        ok: true,
        dryRun: true,
        converted: false,
        outputExists: false,
        preflightOk: true,
      },
    });

    expect(statuses(steps)).toMatchObject({
      "dry-run": "done",
      convert: "ready",
      preview: "waiting",
      bundle: "waiting",
    });
  });

  it("links preview and bundle only after conversion writes an output", () => {
    const steps = convertActionGuideSteps({
      inputPath: "/runs/case/mgxs.h5",
      outputPath: "/runs/case/out.macrolib.txt",
      format: "macrolib",
      run: {
        kind: "ok",
        ok: true,
        dryRun: false,
        converted: true,
        outputExists: true,
        preflightOk: true,
      },
    });

    expect(statuses(steps)).toMatchObject({
      "dry-run": "done",
      convert: "done",
      preview: "ready",
      bundle: "ready",
    });
    expect(steps.find((step) => step.id === "preview")?.href).toBe("#ascii-output-preview");
    expect(steps.find((step) => step.id === "bundle")?.href).toContain(
      "macrolib=%2Fruns%2Fcase%2Fout.macrolib.txt",
    );
  });

  it("blocks every action after a failed preflight", () => {
    const steps = convertActionGuideSteps({
      inputPath: "/runs/case/mgxs.h5",
      outputPath: "/runs/case/out.mcompo.txt",
      format: "multicompo",
      run: {
        kind: "ok",
        ok: false,
        dryRun: true,
        converted: false,
        outputExists: false,
        preflightOk: false,
      },
    });

    expect(statuses(steps)).toEqual({
      "dry-run": "blocked",
      convert: "blocked",
      preview: "blocked",
      bundle: "blocked",
    });
  });
});

function statuses(
  steps: ReturnType<typeof convertActionGuideSteps>,
): Record<string, string> {
  return Object.fromEntries(steps.map((step) => [step.id, step.status]));
}
