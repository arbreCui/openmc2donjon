"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { ConvertFormat, ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import {
  convertActionGuideSteps,
  type ConvertActionGuideStatus,
} from "@/lib/convertActionGuide";
import {
  convertBundleHref,
  convertNextSteps,
} from "@/lib/convertNextSteps";
import type { ConvertWalkthroughRun } from "@/lib/convertWalkthrough";
import { convertDecision } from "@/lib/convertDecision";
import AsciiPreview from "./AsciiPreview";
import ArtifactAnatomyCard from "./ArtifactAnatomyCard";
import ConversionSummaryStrip from "./ConversionSummaryStrip";
import DeliveryChecklist from "./DeliveryChecklist";
import HandoffPipeline from "./HandoffPipeline";
import OutputActions from "./OutputActions";

export type ConvertRunState =
  | { kind: "idle" }
  | { kind: "loading"; mode: "dry-run" | "convert" }
  | { kind: "ok"; data: ConvertResponse }
  | { kind: "error"; message: string; status?: number };

type GateStatus = "pass" | "warn" | "fail" | "skipped";

export default function ConvertReport({
  state,
  onConvert,
  draftInputPath = "",
  draftOutputPath = "",
  format = "multicompo",
}: {
  state: ConvertRunState;
  onConvert?: () => void;
  draftInputPath?: string;
  draftOutputPath?: string;
  format?: ConvertFormat;
}) {
  return (
    <div className="space-y-4">
      <ConvertActionProgress
        state={state}
        draftInputPath={draftInputPath}
        draftOutputPath={draftOutputPath}
        format={format}
      />
      <ResultBody state={state} onConvert={onConvert} />
    </div>
  );
}

function ResultBody({
  state,
  onConvert,
}: {
  state: ConvertRunState;
  onConvert?: () => void;
}) {
  if (state.kind === "idle") {
    return (
      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">
          Ready for a dry run
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-[var(--fg-2)]">
          Start with a dry run to validate the HDF5 contract, energy mesh,
          production checks, and output path without writing an ASCII file.
        </p>
      </section>
    );
  }
  if (state.kind === "loading") {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)] tab-num">
        {state.mode === "dry-run"
          ? "Validating input and output target…"
          : "Validating input and writing ASCII output…"}
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
  return <ConvertSummary data={state.data} onConvert={onConvert} />;
}

function ConvertSummary({
  data,
  onConvert,
}: {
  data: ConvertResponse;
  onConvert?: () => void;
}) {
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
          <Meta label="Validation" value={data.preflight_ok ? "pass" : "fail"} />
        </dl>

        <RunModeNotice data={data} />

        <PrimaryOutcomeActions data={data} input={input} onConvert={onConvert} />

        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            CLI equivalent
          </div>
          <pre className="mt-1 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
            {data.cli_command_text}
          </pre>
        </div>

        <RunDetails data={data} input={input} onConvert={onConvert} />
      </section>

      <HandoffPipeline data={data} input={input} />

      {input ? (
        <ValidationEvidenceDetails data={data} input={input} />
      ) : null}
      {data.converted && data.output_exists ? (
        <div id="ascii-output-preview">
          <AsciiPreview path={data.output_path} format={data.format} input={input} />
        </div>
      ) : null}
    </div>
  );
}

function RunDetails({
  data,
  input,
  onConvert,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
}) {
  return (
    <details
      open={!data.ok}
      className="mt-4 rounded-lg border border-[var(--edge)] bg-black/10 p-3 [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold tracking-tight">
              Run details and delivery checklist
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
              Open this when you need the block anatomy, production evidence, or
              delivery checklist behind the main handoff action.
            </p>
          </div>
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {data.ok ? "optional details" : "review required"}
          </span>
        </div>
      </summary>
      <div className="mt-4 space-y-4">
        <ConversionSummaryStrip data={data} input={input} />
        <ArtifactAnatomyCard data={data} input={input} />
        {input ? <ProductionEvidenceStrip input={input} /> : null}
        {input ? <PreflightDecisionPanel data={data} input={input} /> : null}
        <DeliveryChecklist data={data} input={input} onConvert={onConvert} />
        <OutputActions data={data} onConvert={onConvert} />
        <NextStepsPanel data={data} input={input} />
      </div>
    </details>
  );
}

function PrimaryOutcomeActions({
  data,
  input,
  onConvert,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
}) {
  const decision = convertDecision(data, input);
  const converted = data.converted && data.output_exists;
  const readyToConvert = data.ok && data.dry_run;
  const stopped = !data.ok || (!data.dry_run && !converted);
  return (
    <section className={"mt-4 rounded-lg border p-4 " + primaryOutcomeClass(decision.tone)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-75">
            {converted
              ? "handoff artifact"
              : readyToConvert
                ? "no-write checkpoint"
                : "converter result"}
          </div>
          <h3 className="mt-1 text-base font-semibold tracking-tight">
            {decision.title}
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-1)]">
            {decision.body}
          </p>
        </div>
        <span className="rounded border border-current/25 px-2 py-1 font-mono text-[11px] uppercase tracking-wider">
          {decision.badge}
        </span>
      </div>

      <ul className="mt-3 grid gap-1.5 text-[12px] leading-5 text-[var(--fg-1)] md:grid-cols-2">
        {decision.reasons.map((reason) => (
          <li key={reason} className="flex gap-2">
            <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
            <span>{reason}</span>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap gap-2">
        {readyToConvert && onConvert ? (
          <button type="button" onClick={onConvert} className="btn btn-primary">
            Convert now
          </button>
        ) : null}
        {converted ? (
          <a href="#ascii-output-preview" className="btn btn-primary">
            Preview ASCII
          </a>
        ) : null}
        <CopyCliButton
          value={data.cli_command_text}
          label="Copy CLI"
          ariaLabel="Copy CLI command"
        />
        {converted ? (
          <Link href={convertBundleHref(data)} className="btn btn-secondary">
            Bundle
          </Link>
        ) : null}
        {stopped ? (
          <Link
            href={`/inspect?path=${encodeURIComponent(data.input_path)}`}
            className="btn btn-secondary"
          >
            Inspect HDF5
          </Link>
        ) : null}
      </div>

      <div className="mt-3 grid gap-2 text-[12px] md:grid-cols-2">
        <OutcomePath label="input" value={data.input_path} />
        <OutcomePath
          label={converted ? "DONJON ASCII" : "target"}
          value={data.output_path}
        />
      </div>
    </section>
  );
}

function OutcomePath({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-current/10 bg-black/15 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-65">
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-[12px]">{value}</div>
    </div>
  );
}

function primaryOutcomeClass(tone: "ready" | "pending" | "blocked"): string {
  if (tone === "ready") {
    return "border-emerald-300/25 bg-emerald-300/[0.06] text-emerald-100";
  }
  if (tone === "pending") {
    return "border-cyan-300/25 bg-cyan-300/[0.055] text-cyan-100";
  }
  return "border-rose-300/25 bg-rose-300/[0.055] text-rose-100";
}

function NextStepsPanel({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
}) {
  const steps = convertNextSteps(data, input);
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight">
          Production handoff next steps
        </h3>
        <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
          after convert
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {steps.map((step) => (
          <article
            key={step.id}
            className={"rounded-md border px-3 py-2 " + nextStepClass(step.status)}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
                {step.label}
              </span>
              {step.href ? <StepLink href={step.href} /> : null}
            </div>
            <h4 className="mt-2 text-sm font-semibold tracking-tight">
              {step.title}
            </h4>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {step.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function StepLink({ href }: { href: string }) {
  const label = href.startsWith("#") ? "jump" : "open";
  if (href.startsWith("#")) {
    return (
      <a href={href} className="text-[11px] text-[var(--accent-2)] hover:underline">
        {label}
      </a>
    );
  }
  return (
    <Link href={href} className="text-[11px] text-[var(--accent-2)] hover:underline">
      {label}
    </Link>
  );
}

function nextStepClass(status: "ready" | "blocked" | "reference"): string {
  if (status === "ready") {
    return "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-100";
}

function ProductionEvidenceStrip({ input }: { input: ConvertPreflightInput }) {
  const uncertaintyCoverage = coverage(input);
  const items = [
    {
      label: "Energy mesh",
      value: input.energy_mesh_name ?? input.energy_mesh_id ?? "unknown",
      tone: input.energy_mesh_id ? "pass" : "warn",
      detail: input.energy_mesh_id
        ? "Known group structure identified."
        : "Unknown/custom mesh: acceptable only when intentional.",
    },
    {
      label: "std_dev coverage",
      value: uncertaintyCoverage ?? "not reported",
      tone:
        input.uncertainty?.expected_datasets == null ||
        input.uncertainty.expected_datasets === input.uncertainty.datasets
          ? "pass"
          : "warn",
      detail: "OpenMC tally uncertainty visibility for production review.",
    },
    {
      label: "max std_dev / mean",
      value:
        input.uncertainty?.max_rel == null
          ? "—"
          : formatRelative(input.uncertainty.max_rel),
      tone:
        input.uncertainty?.max_rel == null || input.uncertainty.max_rel <= 0.05
          ? "pass"
          : "warn",
      detail: "Default warning level is 5e-2 unless the run overrides it.",
    },
  ] as const;
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight">
          Production evidence
        </h3>
        <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
          audit trail
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        {items.map((item) => (
          <div
            key={item.label}
            className={
              "rounded-md border px-3 py-2 " +
              (item.tone === "pass"
                ? "border-emerald-400/20 bg-emerald-400/[0.05]"
                : "border-amber-400/25 bg-amber-400/[0.06]")
            }
          >
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {item.label}
            </div>
            <div className="mt-1 font-mono text-[12px] text-[var(--fg-0)]">
              {item.value}
            </div>
            <p className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
              {item.detail}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

function RunModeNotice({ data }: { data: ConvertResponse }) {
  const title = data.dry_run
    ? "Dry run did not write an ASCII file."
    : data.converted
      ? "Convert wrote the ASCII handoff."
      : "Convert stopped before writing output.";
  const body = data.dry_run
    ? "Use this result to review validation, equivalence metadata, and output safety before pressing Convert."
    : data.converted
      ? "This path is the artifact to hand to DONJON or preview in the ASCII viewer below."
      : "Resolve the failed checks or request error, then run the converter again.";
  return (
    <div
      className={
        "mt-4 rounded-md border px-3 py-2 text-sm " +
        (data.dry_run
          ? "border-cyan-300/20 bg-cyan-300/[0.05] text-cyan-100"
          : data.converted
            ? "border-emerald-300/20 bg-emerald-300/[0.05] text-emerald-100"
            : "border-rose-300/20 bg-rose-300/[0.05] text-rose-100")
      }
    >
      <span className="font-semibold">{title}</span>
      <span className="ml-2 text-[var(--fg-1)]">{body}</span>
    </div>
  );
}

function ConvertActionProgress({
  state,
  draftInputPath,
  draftOutputPath,
  format,
}: {
  state: ConvertRunState;
  draftInputPath: string;
  draftOutputPath: string;
  format: ConvertFormat;
}) {
  const inputPath = state.kind === "ok" ? state.data.input_path : draftInputPath;
  const outputPath = state.kind === "ok" ? state.data.output_path : draftOutputPath;
  const resolvedFormat = state.kind === "ok" ? state.data.format : format;
  const steps = convertActionGuideSteps({
    inputPath,
    outputPath,
    format: resolvedFormat,
    run: convertActionRunFromState(state),
  });
  return (
    <section className="rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Converter action guide
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Follow these four user actions: validate without writing, write the
            ASCII handoff, preview the LCM blocks, then bundle the delivery
            record.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {resolvedFormat === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO"}
        </span>
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {steps.map((step) => (
          <article
            key={step.id}
            className={"rounded-lg border px-3 py-2 " + actionGuideClass(step.status)}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="rounded border border-current/25 px-1.5 py-0.5 font-mono text-[10px]">
                {step.label}
              </span>
              <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
                {actionGuideStatusLabel(step.status)}
              </span>
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {step.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {step.body}
            </p>
            {step.href && step.hrefLabel ? (
              <Link
                href={step.href}
                className="mt-3 inline-flex text-[12px] font-medium text-[var(--accent-2)] hover:underline"
              >
                {step.hrefLabel}
              </Link>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function convertActionRunFromState(state: ConvertRunState): ConvertWalkthroughRun {
  if (state.kind === "loading") {
    return { kind: "loading", mode: state.mode };
  }
  if (state.kind === "ok") {
    return {
      kind: "ok",
      ok: state.data.ok,
      dryRun: state.data.dry_run,
      converted: state.data.converted,
      outputExists: state.data.output_exists,
      preflightOk: state.data.preflight_ok,
    };
  }
  return { kind: state.kind };
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

function ValidationEvidenceDetails({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput;
}) {
  const open = !data.ok || !input.ok || input.issues.length > 0;
  const production = data.cli_command.includes("--production");
  const warningText =
    input.warnings.length === 0 ? "no warnings" : `${input.warnings.length} warning(s)`;
  return (
    <details
      open={open}
      className="glass rounded-xl p-5 [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold tracking-tight">
              Detailed validation evidence
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-[var(--fg-2)]">
              Reviewer details for QA and troubleshooting. The main result above
              is enough for normal convert decisions.
            </p>
          </div>
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {production ? "production checks" : "basic checks"} · {warningText}
          </span>
        </div>
      </summary>

      <div className="mt-4 space-y-4">
        <CheckCards data={data} input={input} />
        <InputStats input={input} />
      </div>
    </details>
  );
}

function CheckCards({
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
            {production ? "Production checks" : "Basic checks"}
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            {production
              ? "Strict checks for a production DONJON handoff."
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

function decisionTileClass(tone: "pass" | "warn" | "fail" | "accent" | "neutral") {
  if (tone === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  if (tone === "warn") return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  if (tone === "fail") return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  if (tone === "accent") return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]";
}

function actionGuideClass(status: ConvertActionGuideStatus) {
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

function actionGuideStatusLabel(status: ConvertActionGuideStatus) {
  if (status === "done") return "done";
  if (status === "ready") return "ready";
  if (status === "running") return "running";
  if (status === "blocked") return "blocked";
  return "waiting";
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
