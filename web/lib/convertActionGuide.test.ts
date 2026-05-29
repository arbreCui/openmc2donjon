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
      review: "waiting",
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
      review: "waiting",
    });
  });

  it("links preview and bundle actions only after conversion writes an output", () => {
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
      review: "ready",
    });
    const reviewLinks = steps.find((step) => step.id === "review")?.links ?? [];
    expect(reviewLinks.map((link) => link.href)).toContain("#ascii-output-preview");
    expect(reviewLinks.find((link) => link.label === "Bundle handoff")?.href).toContain(
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
      review: "blocked",
    });
  });
});

function statuses(
  steps: ReturnType<typeof convertActionGuideSteps>,
): Record<string, string> {
  return Object.fromEntries(steps.map((step) => [step.id, step.status]));
}
