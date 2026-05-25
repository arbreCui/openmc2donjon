import type { ConvertFormat } from "./api";
import {
  convertBundleBuilderHrefFromPaths,
  type ConvertWalkthroughRun,
} from "./convertWalkthrough";

export type ConvertActionGuideStepId = "dry-run" | "convert" | "preview" | "bundle";
export type ConvertActionGuideStatus = "waiting" | "ready" | "running" | "done" | "blocked";

export interface ConvertActionGuideStep {
  id: ConvertActionGuideStepId;
  label: string;
  title: string;
  body: string;
  status: ConvertActionGuideStatus;
  href?: string;
  hrefLabel?: string;
}

export interface ConvertActionGuideInput {
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
  run: ConvertWalkthroughRun;
}

export function convertActionGuideSteps({
  inputPath,
  outputPath,
  format,
  run,
}: ConvertActionGuideInput): ConvertActionGuideStep[] {
  const input = inputPath.trim();
  const output = outputPath.trim();
  const hasPaths = input.length > 0 && output.length > 0;
  const outputObject = format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";

  const failed =
    run.kind === "error" ||
    (run.kind === "ok" &&
      (run.ok === false || (run.preflightOk === false && run.converted !== true)));
  const dryRunRunning = run.kind === "loading" && run.mode === "dry-run";
  const convertRunning = run.kind === "loading" && run.mode === "convert";
  const dryRunPassed =
    run.kind === "ok" && run.ok === true && run.dryRun === true && run.preflightOk !== false;
  const converted =
    run.kind === "ok" &&
    run.ok === true &&
    run.converted === true &&
    run.outputExists === true;
  const previewHref = converted ? "#ascii-output-preview" : undefined;
  const bundleHref = converted
    ? convertBundleBuilderHrefFromPaths({
        inputPath: input,
        outputPath: output,
        format,
      }) ?? undefined
    : undefined;

  return [
    {
      id: "dry-run",
      label: "01",
      title: "Dry run",
      body: "Validate the HDF5 handoff and output target without writing an ASCII file.",
      status: failed
        ? "blocked"
        : dryRunRunning
          ? "running"
          : dryRunPassed || converted
            ? "done"
            : hasPaths
              ? "ready"
              : "waiting",
    },
    {
      id: "convert",
      label: "02",
      title: "Convert",
      body: `Write the ${outputObject} ASCII handoff for DONJON.`,
      status: failed
        ? "blocked"
        : convertRunning
          ? "running"
          : converted
            ? "done"
            : dryRunPassed
              ? "ready"
              : "waiting",
    },
    {
      id: "preview",
      label: "03",
      title: "Preview ASCII",
      body: "Read the generated LCM blocks before handing the file downstream.",
      status: failed ? "blocked" : converted ? "ready" : "waiting",
      href: previewHref,
      hrefLabel: previewHref ? "Open preview" : undefined,
    },
    {
      id: "bundle",
      label: "04",
      title: "Bundle handoff",
      body: "Package the input, ASCII output, summaries, and logs into a delivery record.",
      status: failed ? "blocked" : converted ? "ready" : "waiting",
      href: bundleHref,
      hrefLabel: bundleHref ? "Open bundle builder" : undefined,
    },
  ];
}
