import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import type { ConvertActionGuideStatus } from "@/lib/convertActionGuide";

export type GateStatus = "pass" | "warn" | "fail" | "skipped";

export function buildGates(data: ConvertResponse, input: ConvertPreflightInput) {
  const rowBalance = formatRelative(input.scatter_row_balance?.max_rel);
  const chiError = formatRelative(input.physics_checks?.chi_sum_max_abs_error);
  const uncertainty = input.uncertainty;
  const output = outputGate(data);

  return [
    {
      title: "Input contract",
      status: input.ok ? "pass" : "fail",
      summary: input.ok
        ? "Required MGXS datasets and dimensions are readable."
        : "The HDF5 handoff did not satisfy the required contract.",
      detail: `${input.mixtures ?? "?"} mixtures / ${input.energy_groups ?? "?"} groups`,
    },
    {
      title: "Energy mesh",
      status: input.energy_mesh_id ? "pass" : "warn",
      summary: input.energy_mesh_id
        ? "Energy bounds match a bundled known group structure."
        : "Energy bounds are internally valid but not identified as a known mesh.",
      detail: input.energy_mesh_name ?? input.energy_mesh_id ?? "unknown",
    },
    {
      title: "Physics consistency",
      status: input.ok ? "pass" : "fail",
      summary: "Scatter balance, chi normalization, and transport/P1 consistency.",
      detail: `row ${rowBalance} / chi ${chiError}`,
    },
    {
      title: "Uncertainty",
      status:
        uncertainty?.checked === false
          ? "skipped"
          : input.warnings.some((warning) =>
              warning.toLowerCase().includes("std_dev"),
            )
            ? "warn"
            : "pass",
      summary: "MGXS std_dev coverage and maximum relative uncertainty.",
      detail:
        uncertainty?.max_rel == null
          ? coverage(input) ?? "not reported"
          : `${coverage(input) ?? "coverage ?"} / max ${formatRelative(
              uncertainty.max_rel,
            )}`,
    },
    {
      title: "Output safety",
      status: output.status,
      summary: output.summary,
      detail: output.detail,
    },
  ] satisfies {
    title: string;
    status: GateStatus;
    summary: string;
    detail: string;
  }[];
}

function outputGate(data: ConvertResponse): {
  status: GateStatus;
  summary: string;
  detail: string;
} {
  if (data.converted) {
    return {
      status: "pass",
      summary: "ASCII output was written successfully.",
      detail: data.output_exists ? "output file exists" : "output existence unknown",
    };
  }
  if (!data.dry_run) {
    return {
      status: "fail",
      summary: "Conversion stopped before writing output.",
      detail: "no output written",
    };
  }
  if (data.output_exists) {
    return {
      status: "warn",
      summary: "Dry run found an existing output file at the target path.",
      detail: "enable overwrite before converting if replacement is intended",
    };
  }
  return {
    status: "pass",
    summary: "Dry run validated a writable output target without writing a file.",
    detail: "target path is clear",
  };
}

export function primaryOutcomeClass(tone: "ready" | "pending" | "blocked"): string {
  if (tone === "ready") {
    return "border-emerald-300/25 bg-emerald-300/[0.06] text-emerald-100";
  }
  if (tone === "pending") {
    return "border-cyan-300/25 bg-cyan-300/[0.055] text-cyan-100";
  }
  return "border-rose-300/25 bg-rose-300/[0.055] text-rose-100";
}

export function primaryNextActionClass(tone: "ready" | "pending" | "blocked"): string {
  if (tone === "ready") {
    return "border-emerald-300/20 bg-emerald-300/[0.045]";
  }
  if (tone === "pending") {
    return "border-cyan-300/25 bg-cyan-300/[0.075]";
  }
  return "border-rose-300/20 bg-rose-300/[0.045]";
}

export function nextStepClass(status: "ready" | "blocked" | "reference"): string {
  if (status === "ready") {
    return "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-100";
}

export function decisionTileClass(
  tone: "pass" | "warn" | "fail" | "accent" | "neutral",
) {
  if (tone === "pass") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (tone === "warn") {
    return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  }
  if (tone === "fail") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  if (tone === "accent") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]";
}

export function actionGuideClass(status: ConvertActionGuideStatus) {
  if (status === "done") {
    return "border-emerald-400/25 bg-emerald-400/10 text-emerald-100";
  }
  if (status === "ready" || status === "running") {
    return "border-cyan-300/30 bg-cyan-300/10 text-cyan-100";
  }
  if (status === "blocked") {
    return "border-rose-400/30 bg-rose-400/10 text-rose-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}

export function gateCardClass(status: GateStatus) {
  if (status === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06]";
  if (status === "warn") return "border-amber-400/25 bg-amber-400/[0.06]";
  if (status === "fail") return "border-rose-400/25 bg-rose-400/[0.06]";
  return "border-[var(--edge)] bg-white/[0.02]";
}

export function gateBadgeClass(status: GateStatus) {
  if (status === "pass") return "border-emerald-400/30 text-emerald-300";
  if (status === "warn") return "border-amber-400/30 text-amber-300";
  if (status === "fail") return "border-rose-400/30 text-rose-300";
  return "border-[var(--edge-bright)] text-[var(--fg-2)]";
}

export function actionGuideStatusLabel(status: ConvertActionGuideStatus) {
  if (status === "done") return "done";
  if (status === "ready") return "ready";
  if (status === "running") return "running";
  if (status === "blocked") return "blocked";
  return "waiting";
}

export function preflightMode(data: ConvertResponse): string {
  if (data.cli_command.includes("--production")) return "production";
  if (data.cli_command.includes("--check") || data.preflight) return "preflight";
  return "none";
}

export function validationLabel(data: ConvertResponse): string {
  if (!data.preflight) return "skipped";
  return data.preflight_ok ? "pass" : "fail";
}

export function humanDecision(value: string | null | undefined): string {
  if (!value) return "not reported";
  return value.replaceAll("_", " ");
}

export function compactEquivalence(input: ConvertPreflightInput): string {
  const parts: string[] = [];
  if (input.adf_mixtures) {
    const faces = input.adf_faces?.length ?? 0;
    parts.push(faces > 0 ? `ADF ${input.adf_mixtures}/${faces}f` : `ADF ${input.adf_mixtures}`);
  }
  if (input.sph_calculations) {
    parts.push(`SPH ${input.sph_calculations}`);
  }
  return parts.length === 0 ? "none" : parts.join(" + ");
}

export function compactUncertainty(input: ConvertPreflightInput): string {
  const maxRel = input.uncertainty?.max_rel;
  if (maxRel != null) return `std_dev max ${formatRelative(maxRel)}`;
  const reported = coverage(input);
  return reported == null ? "std_dev not reported" : `std_dev ${reported}`;
}

export function coverage(input: ConvertPreflightInput): string | null {
  const datasets = input.uncertainty?.datasets;
  const expected = input.uncertainty?.expected_datasets;
  if (datasets == null || expected == null) return null;
  return `${datasets}/${expected}`;
}

export function formatRelative(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs < 1.0e-3 || abs >= 1.0e3) return value.toExponential(3);
  return value.toPrecision(4);
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
