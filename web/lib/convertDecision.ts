import type { ConvertPreflightInput, ConvertResponse } from "./api";
import { convertObjectLabel } from "./convertNextSteps";

export interface ConvertDecision {
  tone: "ready" | "pending" | "blocked";
  badge: string;
  title: string;
  body: string;
  reasons: string[];
  nextAction: {
    label: string;
    body: string;
  };
}

export function convertDecision(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): ConvertDecision {
  const objectLabel = convertObjectLabel(data.format);
  const converted = data.converted && data.output_exists;
  if (converted) {
    return {
      tone: "ready",
      badge: objectLabel,
      title: "ASCII handoff ready",
      body: `${objectLabel} was written and confirmed at the output path.`,
      reasons: [
        "The converter wrote the ASCII file.",
        data.output_size == null
          ? "Output existence was confirmed; size was not reported."
          : `Output size: ${data.output_size} bytes.`,
        "Preview the ASCII blocks or package the handoff for delivery.",
      ],
      nextAction: {
        label: "Review or deliver",
        body:
          "The ASCII file now exists. Preview the LCM blocks, bundle the handoff, or copy the CLI command for reproducibility.",
      },
    };
  }

  if (data.ok && data.dry_run) {
    return {
      tone: "pending",
      badge: "dry run pass",
      title: "Ready to convert",
      body:
        "Dry run passed without writing a file. Convert now when the output path and validation summary look right.",
      reasons: dryRunPassReasons(data, input),
      nextAction: {
        label: "Next action",
        body:
          "No ASCII file was written. Press Convert now to create the DONJON-facing handoff at the target path.",
      },
    };
  }

  return {
    tone: "blocked",
    badge: "blocked",
    title: "Do not convert yet",
    body:
      "Resolve the failed request or validation result, then rerun dry run before writing an ASCII handoff.",
    reasons: blockedReasons(data, input),
    nextAction: {
      label: "Before writing",
      body:
        "Fix the failed checks, rerun dry run, and only convert after the validation result is acceptable.",
    },
  };
}

function dryRunPassReasons(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): string[] {
  const warnings = input?.warnings.length ?? 0;
  const reasons = [
    data.preflight
      ? `Preflight decision: ${humanDecision(data.preflight.decision)}.`
      : "No preflight payload was returned.",
    "Dry run did not create or replace an ASCII file.",
  ];
  if (warnings > 0) {
    reasons.push(`${warnings} warning(s) remain for audit review.`);
  } else if (input) {
    reasons.push("No validation warnings were reported.");
  }
  if (data.preflight?.output_issue) {
    reasons.push(`Output note: ${data.preflight.output_issue}.`);
  }
  return reasons;
}

function blockedReasons(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): string[] {
  const reasons: string[] = [];
  if (!data.preflight) {
    reasons.push("The request did not produce a preflight payload.");
  } else {
    reasons.push(`Preflight decision: ${humanDecision(data.preflight.decision)}.`);
  }
  if (input?.issues.length) {
    reasons.push(firstCounted("issue", input.issues));
  } else if (data.preflight && !data.preflight_ok) {
    reasons.push("Preflight failed without a mixture-level issue list.");
  }
  if (input?.warnings.length) {
    reasons.push(firstCounted("warning", input.warnings));
  }
  if (data.preflight?.output_issue) {
    reasons.push(`Output issue: ${data.preflight.output_issue}.`);
  }
  if (reasons.length === 0) {
    reasons.push("The converter did not reach an acceptable handoff state.");
  }
  return reasons;
}

function firstCounted(kind: "issue" | "warning", values: string[]): string {
  const first = values[0];
  const extra = values.length > 1 ? ` (+${values.length - 1} more)` : "";
  return `${values.length} ${kind}${values.length === 1 ? "" : "s"}: ${first}${extra}.`;
}

function humanDecision(decision: string | null | undefined): string {
  if (!decision) return "not reported";
  return decision.replace(/^openmc2donjon_/, "").replace(/_/g, " ");
}
