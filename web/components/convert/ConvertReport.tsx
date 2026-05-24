"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import AsciiPreview from "./AsciiPreview";

export type ConvertRunState =
  | { kind: "idle" }
  | { kind: "loading"; mode: "dry-run" | "convert" }
  | { kind: "ok"; data: ConvertResponse }
  | { kind: "error"; message: string; status?: number };

type StepStatus = "complete" | "current" | "pending" | "fail";
type GateStatus = "pass" | "warn" | "fail" | "skipped";

const STEPS = [
  { id: "select", label: "Select HDF5" },
  { id: "preflight", label: "Preflight" },
  { id: "convert", label: "Convert" },
  { id: "review", label: "Review" },
] as const;

export default function ConvertReport({ state }: { state: ConvertRunState }) {
  return (
    <div className="space-y-4">
      <WorkflowStepper statuses={stepStatuses(state)} />
      <ResultBody state={state} />
    </div>
  );
}

function ResultBody({ state }: { state: ConvertRunState }) {
  if (state.kind === "idle") {
    return (
      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">
          Ready for a dry run
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-[var(--fg-2)]">
          Start with a dry run to validate the HDF5 contract, energy mesh,
          production gates, and output path without writing an ASCII file.
        </p>
      </section>
    );
  }
  if (state.kind === "loading") {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)] tab-num">
        {state.mode === "dry-run"
          ? "Running preflight and output checks…"
          : "Running preflight and writing ASCII output…"}
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section className="glass rounded-xl border-rose-500/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Request failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </section>
    );
  }
  return <ConvertSummary data={state.data} />;
}

function ConvertSummary({ data }: { data: ConvertResponse }) {
  const input = data.preflight?.inputs[0] ?? null;
  const headline = data.dry_run
    ? "Dry run complete"
    : data.converted
      ? "ASCII written"
      : "Conversion stopped";
  return (
    <div className="space-y-4">
      <section className="glass rounded-xl p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <div className={`text-sm font-semibold ${data.ok ? "text-emerald-300" : "text-rose-300"}`}>
              {data.ok ? "PASS" : "FAIL"}
            </div>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">
              {headline}
            </h2>
          </div>
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {data.format}
          </span>
        </div>

        <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
          <Meta label="Input" value={data.input_path} mono />
          <Meta label="Output" value={data.output_path} mono />
          <Meta
            label="Output size"
            value={data.output_size == null ? "—" : formatSize(data.output_size)}
          />
          <Meta label="Preflight" value={data.preflight_ok ? "pass" : "fail"} />
        </dl>

        {input ? <PreflightDecisionPanel data={data} input={input} /> : null}

        <PostConvertActions data={data} />

        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            CLI equivalent
          </div>
          <pre className="mt-1 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
            {data.cli_command_text}
          </pre>
        </div>
      </section>

      {input ? (
        <>
          <GateCards data={data} input={input} />
          <InputStats input={input} />
        </>
      ) : null}
      {data.converted && data.output_exists ? (
        <div id="ascii-output-preview">
          <AsciiPreview path={data.output_path} />
        </div>
      ) : null}
    </div>
  );
}

function WorkflowStepper({ statuses }: { statuses: Record<string, StepStatus> }) {
  return (
    <section className="grid gap-2 md:grid-cols-4">
      {STEPS.map((step, index) => {
        const status = statuses[step.id] ?? "pending";
        return (
          <div
            key={step.id}
            className={
              "rounded-lg border px-3 py-2 " +
              stepCardClass(status)
            }
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="text-[11px] uppercase tracking-wider">
                {statusLabel(status)}
              </span>
            </div>
            <div className="mt-1 text-sm font-medium">{step.label}</div>
          </div>
        );
      })}
    </section>
  );
}

function PreflightDecisionPanel({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput;
}) {
  const outputIssue = data.preflight?.output_issue ?? null;
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <DecisionTile
          label="mode"
          value={preflightMode(data)}
          tone={data.cli_command.includes("--production") ? "accent" : "neutral"}
        />
        <DecisionTile
          label="decision"
          value={humanDecision(data.preflight?.decision)}
          tone={data.preflight_ok ? "pass" : "fail"}
        />
        <DecisionTile
          label="issues"
          value={String(input.issues.length)}
          tone={input.issues.length === 0 ? "pass" : "fail"}
        />
        <DecisionTile
          label="warnings"
          value={String(input.warnings.length)}
          tone={input.warnings.length === 0 ? "pass" : "warn"}
        />
      </div>
      {outputIssue ? (
        <div className="mt-3 rounded-md border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-sm text-amber-100">
          <span className="font-semibold">Output issue:</span>{" "}
          <span className="text-[var(--fg-1)]">{outputIssue}</span>
        </div>
      ) : null}
    </section>
  );
}

function DecisionTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "pass" | "warn" | "fail" | "accent" | "neutral";
}) {
  return (
    <div className={"rounded-md border px-3 py-2 " + decisionTileClass(tone)}>
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
        {label}
      </div>
      <div className="mt-1 font-mono text-[13px]">{value}</div>
    </div>
  );
}

function PostConvertActions({ data }: { data: ConvertResponse }) {
  const notice = outputNotice(data);
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap gap-2">
        <Link
          href={`/inspect?path=${encodeURIComponent(data.input_path)}`}
          className="btn btn-secondary"
        >
          Inspect input
        </Link>
        <CopyCliButton
          value={data.output_path}
          label="Copy output path"
          ariaLabel="Copy output path"
        />
        {data.converted && data.output_exists ? (
          <a href="#ascii-output-preview" className="btn btn-secondary">
            Preview ASCII
          </a>
        ) : null}
      </div>
      <div
        className={
          "rounded-md border px-3 py-2 text-sm " + outputNoticeClass(notice.tone)
        }
      >
        <span className="font-semibold">{notice.title}</span>
        <span className="ml-2 text-[var(--fg-1)]">{notice.body}</span>
      </div>
    </div>
  );
}

function GateCards({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput;
}) {
  const gates = buildGates(data, input);
  const production = data.cli_command.includes("--production");
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            {production ? "Production gates" : "Preflight gates"}
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            {production
              ? "Strict acceptance checks for a production DONJON handoff."
              : "Basic contract and output checks before writing ASCII."}
          </p>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {gates.map((gate) => (
          <article
            key={gate.title}
            className={
              "rounded-lg border p-4 " + gateCardClass(gate.status)
            }
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold tracking-tight">
                {gate.title}
              </h3>
              <GateBadge status={gate.status} />
            </div>
            <p className="mt-2 text-sm text-[var(--fg-2)]">{gate.summary}</p>
            {gate.detail ? (
              <div className="mt-3 font-mono text-[12px] text-[var(--fg-1)]">
                {gate.detail}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function InputStats({ input }: { input: ConvertPreflightInput }) {
  const stats = [
    ["groups", input.energy_groups],
    ["moments", input.legendre_order == null ? null : input.legendre_order + 1],
    ["mixtures", input.mixtures],
    ["states", input.state_points],
    ["fissionable", input.fissionable_mixtures],
    ["ADF mixes", input.adf_mixtures],
    ["SPH calcs", input.sph_calculations],
    ["std_dev", coverage(input)],
  ];
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="text-base font-semibold tracking-tight">
          Input details
        </h2>
        <span
          className={
            "rounded border px-2 py-1 text-[11px] uppercase tracking-wider " +
            (input.ok
              ? "border-emerald-400/30 text-emerald-300"
              : "border-rose-400/30 text-rose-300")
          }
        >
          {input.ok ? "pass" : "fail"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        {stats.map(([label, value]) => (
          <div
            key={label}
            className="rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2"
          >
            <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              {label}
            </div>
            <div className="mt-1 text-sm tab-num text-[var(--fg-0)]">
              {value == null ? "—" : String(value)}
            </div>
          </div>
        ))}
      </div>

      <IssueList title="Issues" items={input.issues} tone="rose" />
      <IssueList title="Warnings" items={input.warnings} tone="amber" />
    </section>
  );
}

function GateBadge({ status }: { status: GateStatus }) {
  return (
    <span
      className={
        "rounded-md border px-2 py-0.5 text-[11px] uppercase tracking-wider " +
        gateBadgeClass(status)
      }
    >
      {status}
    </span>
  );
}

function IssueList({
  title,
  items,
  tone,
}: {
  title: string;
  items: readonly string[];
  tone: "rose" | "amber";
}) {
  if (items.length === 0) return null;
  const color = tone === "rose" ? "text-rose-300" : "text-amber-300";
  return (
    <div className="mt-4">
      <div className={`text-sm font-semibold ${color}`}>{title}</div>
      <ul className="mt-1 space-y-1 text-sm text-[var(--fg-1)]">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function Meta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </dt>
      <dd
        className={
          "mt-0.5 truncate text-[var(--fg-1)] " + (mono ? "font-mono" : "")
        }
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}

function buildGates(data: ConvertResponse, input: ConvertPreflightInput) {
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
          : input.warnings.some((warning) => warning.toLowerCase().includes("std_dev"))
            ? "warn"
            : "pass",
      summary: "MGXS std_dev coverage and maximum relative uncertainty.",
      detail:
        uncertainty?.max_rel == null
          ? coverage(input) ?? "not reported"
          : `${coverage(input) ?? "coverage ?"} / max ${formatRelative(uncertainty.max_rel)}`,
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

function outputNotice(data: ConvertResponse): {
  tone: "pass" | "warn" | "fail" | "neutral";
  title: string;
  body: string;
} {
  if (data.converted) {
    return {
      tone: "pass",
      title: "Output file written.",
      body: "Review the ASCII preview below before handing the file to DONJON.",
    };
  }
  if (!data.dry_run) {
    return {
      tone: "fail",
      title: "No output file written.",
      body: "Fix the failing checks or request error, then run Convert again.",
    };
  }
  if (data.output_exists) {
    return {
      tone: "warn",
      title: "Dry run only; target already exists.",
      body: "Enable Overwrite output before converting if this file should be replaced.",
    };
  }
  return {
    tone: "neutral",
    title: "Dry run only; no file written.",
    body: "The target path is clear, so Convert will write the ASCII file there.",
  };
}

function outputNoticeClass(tone: "pass" | "warn" | "fail" | "neutral") {
  if (tone === "pass") {
    return "border-emerald-400/25 bg-emerald-400/10 text-emerald-200";
  }
  if (tone === "warn") {
    return "border-amber-400/25 bg-amber-400/10 text-amber-200";
  }
  if (tone === "fail") {
    return "border-rose-400/25 bg-rose-400/10 text-rose-200";
  }
  return "border-[var(--edge)] bg-white/[0.03] text-[var(--fg-2)]";
}

function decisionTileClass(tone: "pass" | "warn" | "fail" | "accent" | "neutral") {
  if (tone === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  if (tone === "warn") return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  if (tone === "fail") return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  if (tone === "accent") return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]";
}

function stepStatuses(state: ConvertRunState): Record<string, StepStatus> {
  if (state.kind === "idle") {
    return {
      select: "current",
      preflight: "pending",
      convert: "pending",
      review: "pending",
    };
  }
  if (state.kind === "loading") {
    return {
      select: "complete",
      preflight: state.mode === "convert" ? "complete" : "current",
      convert: state.mode === "convert" ? "current" : "pending",
      review: "pending",
    };
  }
  if (state.kind === "error") {
    return {
      select: "complete",
      preflight: "fail",
      convert: "pending",
      review: "pending",
    };
  }
  const data = state.data;
  if (!data.ok) {
    return {
      select: "complete",
      preflight: data.preflight_ok ? "complete" : "fail",
      convert: "fail",
      review: "pending",
    };
  }
  if (data.dry_run) {
    return {
      select: "complete",
      preflight: "complete",
      convert: "pending",
      review: "current",
    };
  }
  return {
    select: "complete",
    preflight: "complete",
    convert: data.converted ? "complete" : "fail",
    review: "current",
  };
}

function stepCardClass(status: StepStatus) {
  if (status === "complete") {
    return "border-emerald-400/25 bg-emerald-400/10 text-emerald-100";
  }
  if (status === "current") {
    return "border-cyan-300/30 bg-cyan-300/10 text-cyan-100";
  }
  if (status === "fail") {
    return "border-rose-400/30 bg-rose-400/10 text-rose-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}

function gateCardClass(status: GateStatus) {
  if (status === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06]";
  if (status === "warn") return "border-amber-400/25 bg-amber-400/[0.06]";
  if (status === "fail") return "border-rose-400/25 bg-rose-400/[0.06]";
  return "border-[var(--edge)] bg-white/[0.02]";
}

function gateBadgeClass(status: GateStatus) {
  if (status === "pass") return "border-emerald-400/30 text-emerald-300";
  if (status === "warn") return "border-amber-400/30 text-amber-300";
  if (status === "fail") return "border-rose-400/30 text-rose-300";
  return "border-[var(--edge-bright)] text-[var(--fg-2)]";
}

function statusLabel(status: StepStatus) {
  if (status === "complete") return "done";
  if (status === "current") return "active";
  if (status === "fail") return "failed";
  return "pending";
}

function preflightMode(data: ConvertResponse): string {
  if (data.cli_command.includes("--production")) return "production";
  if (data.cli_command.includes("--check") || data.preflight) return "preflight";
  return "none";
}

function humanDecision(value: string | null | undefined): string {
  if (!value) return "not reported";
  return value.replaceAll("_", " ");
}

function coverage(input: ConvertPreflightInput): string | null {
  const datasets = input.uncertainty?.datasets;
  const expected = input.uncertainty?.expected_datasets;
  if (datasets == null || expected == null) return null;
  return `${datasets}/${expected}`;
}

function formatRelative(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs < 1.0e-3 || abs >= 1.0e3) return value.toExponential(3);
  return value.toPrecision(4);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
