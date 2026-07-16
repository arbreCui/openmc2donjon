import type {
  ConvertFormat,
  OpenmcWorkflowArtifact,
  OpenmcWorkflowCheck,
  OpenmcWorkflowPlan,
} from "./api";
import { OPENMC_SPH_WORKFLOW_STEPS } from "./openmcSphWorkflow";
import {
  withProjectComponentContext,
  type ProjectComponentRouteContext,
} from "./projectWorkspace";

export type OpenmcWalkthroughPhase = "source" | "plan" | "run" | "review" | "bundle";

// The page plans commands; it never executes them. The vocabulary is
// therefore planning-tense only: a successful plan is "planned", an
// in-flight plan request is "planning".
export type OpenmcWalkthroughStatus =
  | "needed"
  | "ready"
  | "planning"
  | "blocked"
  | "planned"
  | "written"
  | "verified"
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
        ? "planning"
        : planned
          ? "planned"
          : sourceReady
            ? "ready"
            : "needed",
    run: failed ? "blocked" : planned ? "ready" : "planned",
    review: failed ? "blocked" : "planned",
    bundle: failed ? "blocked" : hasRunDir ? "planned" : "optional",
  };
}

export const OPENMC_SPH_SIDECAR_FORM_HREF =
  "/equivalence?kind=openmc-sph-sidecar&contract=physical-sph";

const OPENMC_SPH_SIDECAR_CHECK_NAME = "SPH sidecar";

export interface OpenmcSphPrerequisiteCommand {
  id: string;
  badge: string;
  title: string;
  cli: string;
}

export function isFailedOpenmcSphSidecarCheck(check: OpenmcWorkflowCheck): boolean {
  return check.name === OPENMC_SPH_SIDECAR_CHECK_NAME && check.status === "fail";
}

export function openmcSphSidecarCheckFailed(plan: OpenmcWorkflowPlan): boolean {
  return plan.equivalence === "sph" && plan.checks.some(isFailedOpenmcSphSidecarCheck);
}

/**
 * The three commands that build the SPH sidecar this plan consumes. They are
 * spliced ahead of the plan's own command list when the sidecar readiness
 * check fails, so "copy these in order" no longer omits its own prerequisite.
 */
export function openmcSphPrerequisiteCommands(): OpenmcSphPrerequisiteCommand[] {
  const wanted: readonly string[] = ["ce-flux", "mg-flux", "sph-sidecar"];
  return OPENMC_SPH_WORKFLOW_STEPS.filter((step) => wanted.includes(step.id)).map(
    (step) => ({ id: step.id, badge: step.badge, title: step.title, cli: step.cli }),
  );
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
  projectContext?: ProjectComponentRouteContext,
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
  const href = `/convert?${params.toString()}`;
  return projectContext
    ? withProjectComponentContext(href, projectContext)
    : href;
}

/** Build the "already have an HDF5" route before an OpenMC plan exists. */
export function openmcDirectConvertHref(
  inputPath: string,
  outputPath: string,
  format: ConvertFormat,
  production: boolean,
  projectContext?: ProjectComponentRouteContext,
): string {
  const input = inputPath.trim();
  const output = outputPath.trim();
  const hasProjectContext = Boolean(
    projectContext?.projectRoot ||
      projectContext?.componentId ||
      projectContext?.contract,
  );
  if (!input && !output && !hasProjectContext) return "/convert";
  const params = new URLSearchParams({
    intent: "direct-convert",
    format,
    check: "1",
    production: production ? "1" : "0",
  });
  if (input) params.set("input", input);
  if (output) params.set("output", output);
  const href = `/convert?${params.toString()}`;
  return projectContext
    ? withProjectComponentContext(href, projectContext)
    : href;
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
