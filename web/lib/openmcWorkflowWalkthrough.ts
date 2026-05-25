import type {
  ConvertFormat,
  OpenmcWorkflowArtifact,
  OpenmcWorkflowPlan,
} from "./api";

export type OpenmcWalkthroughPhase = "source" | "plan" | "run" | "review" | "bundle";

export type OpenmcWalkthroughStatus =
  | "needed"
  | "ready"
  | "running"
  | "passed"
  | "blocked"
  | "planned"
  | "optional";

export interface OpenmcWalkthroughRun {
  kind: "idle" | "loading" | "ok" | "error";
  ok?: boolean;
}

export interface OpenmcWalkthroughInput {
  hasRecipe: boolean;
  hasStatepoint: boolean;
  loadStatepoint: boolean;
  hasRunDir: boolean;
  run: OpenmcWalkthroughRun;
}

export function openmcWalkthroughStatuses({
  hasRecipe,
  hasStatepoint,
  loadStatepoint,
  hasRunDir,
  run,
}: OpenmcWalkthroughInput): Record<OpenmcWalkthroughPhase, OpenmcWalkthroughStatus> {
  const sourceReady = hasRecipe && (!loadStatepoint || hasStatepoint);
  const failed = run.kind === "error" || (run.kind === "ok" && run.ok === false);
  const planned = run.kind === "ok" && run.ok === true;

  return {
    source: sourceReady ? "ready" : "needed",
    plan: failed
      ? "blocked"
      : run.kind === "loading"
        ? "running"
        : planned
          ? "passed"
          : sourceReady
            ? "ready"
            : "needed",
    run: failed ? "blocked" : planned ? "ready" : "planned",
    review: failed ? "blocked" : "planned",
    bundle: failed ? "blocked" : hasRunDir ? "planned" : "optional",
  };
}

export function openmcInspectHref(plan: OpenmcWorkflowPlan): string | null {
  const hdf5 = conversionInputArtifact(plan) ?? firstArtifact(plan.artifacts, "hdf5");
  if (!hdf5) return null;
  return `/inspect?path=${encodeURIComponent(hdf5.path)}`;
}

export function openmcConvertHref(
  plan: OpenmcWorkflowPlan,
  format: ConvertFormat,
  production: boolean,
): string | null {
  const input = conversionInputArtifact(plan);
  const ascii = firstArtifact(plan.artifacts, "ascii");
  if (!input || !ascii) return null;
  const params = new URLSearchParams({
    intent: plan.workflow === "two-step" ? "direct-convert" : "check",
    input: input.path,
    output: ascii.path,
    format,
    check: "1",
    production: production ? "1" : "0",
    comment: `${plan.workflow_label} web handoff`,
  });
  return `/convert?${params.toString()}`;
}

export function openmcBundleBuilderHref(
  plan: OpenmcWorkflowPlan,
  format: ConvertFormat,
): string | null {
  const input = conversionInputArtifact(plan);
  const ascii = firstArtifact(plan.artifacts, "ascii");
  const outputDir = bundleOutputDir(plan);
  if (!input || !ascii || !outputDir) return null;
  const params = new URLSearchParams({
    command: "bundle",
    output_dir: outputDir,
    mgxs: input.path,
  });
  if (format === "macrolib") {
    params.set("macrolib", ascii.path);
  } else {
    params.set("mcompo", ascii.path);
  }
  return `/builder?${params.toString()}`;
}

function conversionInputArtifact(
  plan: OpenmcWorkflowPlan,
): OpenmcWorkflowArtifact | undefined {
  if (plan.workflow === "two-step" && plan.equivalence !== "direct") {
    const augmented = plan.artifacts.find((artifact) =>
      artifact.label.toLowerCase().includes("augmented"),
    );
    if (augmented) return augmented;
  }
  return firstArtifact(plan.artifacts, "hdf5");
}

function firstArtifact(
  artifacts: readonly OpenmcWorkflowArtifact[],
  kind: string,
): OpenmcWorkflowArtifact | undefined {
  return artifacts.find((artifact) => artifact.kind === kind);
}

function bundleOutputDir(plan: OpenmcWorkflowPlan): string | null {
  const manifest = plan.artifacts.find(
    (artifact) => artifact.label.toLowerCase() === "bundle manifest",
  );
  if (manifest) return parentDir(manifest.path);
  const summary = plan.artifacts.find(
    (artifact) => artifact.label.toLowerCase() === "pipeline summary",
  );
  if (summary) return parentDir(summary.path);
  return null;
}

function parentDir(path: string): string {
  const trimmed = path.trim();
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return ".";
  return trimmed.slice(0, index);
}
