import { describe, expect, it } from "vitest";
import {
  convertBundleBuilderHrefFromPaths,
  convertWorkflowStageSummary,
  convertWalkthroughStatuses,
} from "./convertWalkthrough";

describe("convert production walkthrough", () => {
  it("builds bundle builder links from draft converter paths", () => {
    expect(
      convertBundleBuilderHrefFromPaths({
        inputPath: "/runs/case/mgxs_library.h5",
        outputPath: "/runs/case/out.mcompo.txt",
        format: "multicompo",
      }),
    ).toBe(
      "/builder?command=bundle&output_dir=%2Fruns%2Fcase%2Fbundle&mgxs=%2Fruns%2Fcase%2Fmgxs_library.h5&mcompo=%2Fruns%2Fcase%2Fout.mcompo.txt",
    );

    expect(
      convertBundleBuilderHrefFromPaths({
        inputPath: "/runs/case/mgxs_library.h5",
        outputPath: "/runs/case/out.macrolib.txt",
        format: "macrolib",
      }),
    ).toContain("macrolib=%2Fruns%2Fcase%2Fout.macrolib.txt");
  });

  it("does not link to bundle builder until both paths are known", () => {
    expect(
      convertBundleBuilderHrefFromPaths({
        inputPath: "",
        outputPath: "/runs/case/out.mcompo.txt",
        format: "multicompo",
      }),
    ).toBeNull();
  });

  it("marks dry-run pass as ready for conversion but not yet bundle-ready", () => {
    expect(
      convertWalkthroughStatuses({
        hasInput: true,
        hasOutput: true,
        run: {
          kind: "ok",
          ok: true,
          dryRun: true,
          converted: false,
          outputExists: false,
          preflightOk: true,
        },
      }),
    ).toEqual({
      source: "ready",
      "dry-run": "passed",
      convert: "ready",
      bundle: "planned",
    });
  });

  it("marks converted output as ready for bundle handoff", () => {
    expect(
      convertWalkthroughStatuses({
        hasInput: true,
        hasOutput: true,
        run: {
          kind: "ok",
          ok: true,
          dryRun: false,
          converted: true,
          outputExists: true,
          preflightOk: true,
        },
      }),
    ).toMatchObject({
      "dry-run": "passed",
      convert: "done",
      bundle: "ready",
    });
  });

  it("blocks downstream stages when validation fails", () => {
    expect(
      convertWalkthroughStatuses({
        hasInput: true,
        hasOutput: true,
        run: {
          kind: "ok",
          ok: false,
          dryRun: true,
          converted: false,
          outputExists: false,
          preflightOk: false,
        },
      }),
    ).toMatchObject({
      "dry-run": "blocked",
      convert: "blocked",
      bundle: "blocked",
    });
  });

  it("summarizes the empty form as a fill-path stage", () => {
    const summary = convertWorkflowStageSummary({
      hasInput: false,
      hasOutput: false,
      run: { kind: "idle" },
    });
    expect(summary.active).toBe("fill");
    expect(summary.title).toBe("Fill the source and target paths");
    expect(summary.stages.map((stage) => stage.status)).toEqual([
      "current",
      "upcoming",
      "upcoming",
      "upcoming",
    ]);
  });

  it("summarizes a passing dry run as ready to convert", () => {
    const summary = convertWorkflowStageSummary({
      hasInput: true,
      hasOutput: true,
      run: {
        kind: "ok",
        ok: true,
        dryRun: true,
        converted: false,
        outputExists: false,
        preflightOk: true,
      },
    });
    expect(summary.active).toBe("convert");
    expect(summary.title).toBe("Dry run passed; convert next");
    expect(summary.body).toContain("No ASCII file was written");
    expect(summary.stages.map((stage) => stage.status)).toEqual([
      "complete",
      "complete",
      "current",
      "upcoming",
    ]);
  });

  it("summarizes converted output as ready to review and bundle", () => {
    const summary = convertWorkflowStageSummary({
      hasInput: true,
      hasOutput: true,
      run: {
        kind: "ok",
        ok: true,
        dryRun: false,
        converted: true,
        outputExists: true,
        preflightOk: true,
      },
    });
    expect(summary.active).toBe("review");
    expect(summary.tone).toBe("ready");
    expect(summary.stages.map((stage) => stage.status)).toEqual([
      "complete",
      "complete",
      "complete",
      "current",
    ]);
  });
});
