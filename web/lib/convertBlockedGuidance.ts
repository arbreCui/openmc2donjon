import type { ConvertPreflightInput, ConvertResponse } from "./api";

export interface ConvertBlockedGuidance {
  badge: string;
  title: string;
  body: string;
  primaryFix: string;
  facts: string[];
  tone: "fail" | "warn";
}

export function convertBlockedGuidance(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): ConvertBlockedGuidance {
  const facts = blockingFacts(data, input);

  if (!data.ok || data.preflight_ok === false || input?.ok === false) {
    return {
      badge: "blocked",
      title: "Fix validation before writing",
      body:
        "The converter did not produce a production-ready ASCII handoff. Review the failed check, fix the input HDF5 or options, then rerun dry-run.",
      primaryFix: "Start with the first HDF5 issue or production gate failure.",
      facts,
      tone: "fail",
    };
  }

  if (data.dry_run && data.output_exists) {
    return {
      badge: "target exists",
      title: "Choose overwrite or a new output path",
      body:
        "Dry-run passed, but the target path already exists. The web converter will not replace it until the run options explicitly allow replacement.",
      primaryFix:
        "Pick a fresh output path, or enable overwrite only if replacing that file is intended.",
      facts,
      tone: "warn",
    };
  }

  if (data.converted && !data.output_exists) {
    return {
      badge: "not confirmed",
      title: "Confirm the written file",
      body:
        "The conversion response returned, but the backend could not confirm a readable ASCII file at the target path.",
      primaryFix:
        "Refresh file status, check the output directory permissions, then rerun Convert if needed.",
      facts,
      tone: "warn",
    };
  }

  return {
    badge: "stopped",
    title: "Rerun dry-run before writing",
    body:
      "This result is not ready for preview or bundling. Recheck the paths and run dry-run again before converting.",
    primaryFix: "Use the source inspector and CLI command text to reproduce the request.",
    facts,
    tone: "warn",
  };
}

function blockingFacts(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): string[] {
  const facts: string[] = [];
  if (data.preflight?.output_issue) {
    facts.push(`Output issue: ${data.preflight.output_issue}`);
  }
  if (input?.issues.length) {
    facts.push(firstCounted("issue", input.issues));
  }
  if (input?.warnings.length) {
    facts.push(firstCounted("warning", input.warnings));
  }
  if (!data.preflight) {
    facts.push("No preflight payload was returned.");
  } else if (data.preflight_ok === false) {
    facts.push(`Preflight decision: ${humanDecision(data.preflight.decision)}`);
  }
  if (data.dry_run && data.output_exists) {
    facts.push(`Existing target: ${data.output_path}`);
  }
  if (data.converted && !data.output_exists) {
    facts.push(`Unconfirmed target: ${data.output_path}`);
  }
  if (!data.ok && facts.length === 0) {
    facts.push("The converter stopped before reaching an acceptable handoff state.");
  }
  if (facts.length === 0) {
    facts.push("Preview and bundle remain locked until a confirmed ASCII file exists.");
  }
  return facts.slice(0, 4);
}

function firstCounted(kind: "issue" | "warning", values: string[]): string {
  const first = values[0];
  const extra = values.length > 1 ? ` (+${values.length - 1} more)` : "";
  return `${values.length} ${kind}${values.length === 1 ? "" : "s"}: ${first}${extra}`;
}

function humanDecision(decision: string | null | undefined): string {
  if (!decision) return "not reported";
  return decision.replace(/^openmc2donjon_/, "").replace(/_/g, " ");
}
