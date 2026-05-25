import type { ConvertFormat } from "./api";

export type ConvertWalkthroughPhase = "source" | "dry-run" | "convert" | "bundle";

export type ConvertWorkflowStageId = "fill" | "dry-run" | "convert" | "review";

export type ConvertWorkflowStageStatus =
  | "complete"
  | "current"
  | "running"
  | "blocked"
  | "upcoming";

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

export interface ConvertWorkflowStage {
  id: ConvertWorkflowStageId;
  label: string;
  status: ConvertWorkflowStageStatus;
}

export interface ConvertWorkflowStageSummary {
  active: ConvertWorkflowStageId;
  title: string;
  body: string;
  tone: Exclude<ConvertWorkflowStageStatus, "upcoming" | "complete"> | "ready";
  stages: ConvertWorkflowStage[];
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

export function convertWorkflowStageSummary(
  input: ConvertWalkthroughInput,
): ConvertWorkflowStageSummary {
  const { hasInput, hasOutput, run } = input;
  const hasPaths = hasInput && hasOutput;
  const failed =
    run.kind === "error" ||
    (run.kind === "ok" &&
      (run.ok === false || (run.preflightOk === false && run.converted !== true)));
  const converted =
    run.kind === "ok" &&
    run.ok === true &&
    run.converted === true &&
    run.outputExists === true;
  const dryRunPassed = run.kind === "ok" && run.ok === true && run.dryRun === true;

  if (failed) {
    return stageSummary({
      active: "dry-run",
      title: "Fix validation before writing",
      body:
        "The converter stopped at the dry-run gate. Resolve the reported issues, then rerun dry run before Convert.",
      tone: "blocked",
      completeThrough: hasPaths ? "fill" : null,
      blockedFrom: "dry-run",
    });
  }

  if (run.kind === "loading" && run.mode === "dry-run") {
    return stageSummary({
      active: "dry-run",
      title: "Checking without writing",
      body:
        "Dry run is reading the HDF5 handoff and applying the selected validation gates. No ASCII file is being written.",
      tone: "running",
      completeThrough: hasPaths ? "fill" : null,
      activeStatus: "running",
    });
  }

  if (run.kind === "loading" && run.mode === "convert") {
    return stageSummary({
      active: "convert",
      title: "Writing the ASCII handoff",
      body:
        "Convert is creating the DONJON-facing ASCII file at the selected target path.",
      tone: "running",
      completeThrough: "dry-run",
      activeStatus: "running",
    });
  }

  if (converted) {
    return stageSummary({
      active: "review",
      title: "ASCII handoff ready",
      body:
        "The converter wrote the ASCII library. Preview the LCM blocks or bundle the delivery record next.",
      tone: "ready",
      completeThrough: "convert",
    });
  }

  if (dryRunPassed) {
    return stageSummary({
      active: "convert",
      title: "Dry run passed; convert next",
      body:
        "No ASCII file was written by dry run. Press Convert to create the DONJON-facing handoff at the target path.",
      tone: "current",
      completeThrough: "dry-run",
    });
  }

  if (hasPaths) {
    return stageSummary({
      active: "dry-run",
      title: "Ready for a no-write dry run",
      body:
        "The source and target paths are set. Run dry run to check the HDF5 contract before writing ASCII.",
      tone: "current",
      completeThrough: "fill",
    });
  }

  return stageSummary({
    active: "fill",
    title: "Fill the source and target paths",
    body:
      "Choose the OpenMC MGXS HDF5 input and the ASCII output path, then run the no-write dry run.",
    tone: "current",
    completeThrough: null,
  });
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

function stageSummary({
  active,
  title,
  body,
  tone,
  completeThrough,
  blockedFrom,
  activeStatus = "current",
}: {
  active: ConvertWorkflowStageId;
  title: string;
  body: string;
  tone: ConvertWorkflowStageSummary["tone"];
  completeThrough: ConvertWorkflowStageId | null;
  blockedFrom?: ConvertWorkflowStageId;
  activeStatus?: ConvertWorkflowStageStatus;
}): ConvertWorkflowStageSummary {
  return {
    active,
    title,
    body,
    tone,
    stages: STAGE_ORDER.map((stage) => ({
      ...stage,
      status: stageStatus(stage.id, active, completeThrough, blockedFrom, activeStatus),
    })),
  };
}

function stageStatus(
  id: ConvertWorkflowStageId,
  active: ConvertWorkflowStageId,
  completeThrough: ConvertWorkflowStageId | null,
  blockedFrom?: ConvertWorkflowStageId,
  activeStatus: ConvertWorkflowStageStatus = "current",
): ConvertWorkflowStageStatus {
  if (blockedFrom && stageIndex(id) >= stageIndex(blockedFrom)) return "blocked";
  if (id === active) return activeStatus;
  if (completeThrough && stageIndex(id) <= stageIndex(completeThrough)) return "complete";
  return "upcoming";
}

function stageIndex(id: ConvertWorkflowStageId): number {
  return STAGE_ORDER.findIndex((stage) => stage.id === id);
}

const STAGE_ORDER: readonly Omit<ConvertWorkflowStage, "status">[] = [
  { id: "fill", label: "Fill" },
  { id: "dry-run", label: "Dry run" },
  { id: "convert", label: "Convert" },
  { id: "review", label: "Preview/Bundle" },
];
