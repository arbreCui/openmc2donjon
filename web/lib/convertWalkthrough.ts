import type { ConvertFormat } from "./api";

export type ConvertWalkthroughPhase = "source" | "dry-run" | "convert" | "bundle";

export type ConvertWalkthroughStatus =
  | "needed"
  | "recommended"
  | "running"
  | "passed"
  | "ready"
  | "done"
  | "blocked"
  | "planned";

export interface ConvertWalkthroughRun {
  kind: "idle" | "loading" | "ok" | "error";
  mode?: "dry-run" | "convert";
  ok?: boolean;
  dryRun?: boolean;
  converted?: boolean;
  outputExists?: boolean;
  preflightOk?: boolean | null;
}

export interface ConvertWalkthroughInput {
  hasInput: boolean;
  hasOutput: boolean;
  run: ConvertWalkthroughRun;
}

export function convertWalkthroughStatuses({
  hasInput,
  hasOutput,
  run,
}: ConvertWalkthroughInput): Record<ConvertWalkthroughPhase, ConvertWalkthroughStatus> {
  const hasPaths = hasInput && hasOutput;
  const failed = run.kind === "error" || (run.kind === "ok" && run.ok === false);
  const loadingDryRun = run.kind === "loading" && run.mode === "dry-run";
  const loadingConvert = run.kind === "loading" && run.mode === "convert";
  const dryRunPassed = run.kind === "ok" && run.ok === true && run.dryRun === true;
  const converted =
    run.kind === "ok" &&
    run.ok === true &&
    run.converted === true &&
    run.outputExists === true;
  const preflightFailed =
    run.kind === "ok" &&
    run.preflightOk === false &&
    run.converted !== true;

  return {
    source: hasInput ? "ready" : "needed",
    "dry-run": failed || preflightFailed
      ? "blocked"
      : loadingDryRun
        ? "running"
        : dryRunPassed || converted
          ? "passed"
          : hasPaths
            ? "recommended"
            : "needed",
    convert: failed || preflightFailed
      ? "blocked"
      : loadingConvert
        ? "running"
        : converted
          ? "done"
          : dryRunPassed || hasPaths
            ? "ready"
            : "needed",
    bundle: failed || preflightFailed
      ? "blocked"
      : converted
        ? "ready"
        : hasPaths
          ? "planned"
          : "needed",
  };
}

export function convertBundleBuilderHrefFromPaths({
  inputPath,
  outputPath,
  format,
}: {
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
}): string | null {
  const input = inputPath.trim();
  const output = outputPath.trim();
  if (!input || !output) return null;

  const params = new URLSearchParams({
    command: "bundle",
    output_dir: siblingBundleDir(output),
    mgxs: input,
  });
  if (format === "macrolib") {
    params.set("macrolib", output);
  } else {
    params.set("mcompo", output);
  }
  return `/builder?${params.toString()}`;
}

function siblingBundleDir(outputPath: string): string {
  const index = outputPath.lastIndexOf("/");
  if (index <= 0) return "bundle";
  return `${outputPath.slice(0, index)}/bundle`;
}
