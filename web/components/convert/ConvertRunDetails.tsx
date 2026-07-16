import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import {
  convertNextSteps,
  isCopyCliDestination,
  type ConvertDownstreamDestination,
} from "@/lib/convertNextSteps";
import ArtifactAnatomyCard from "./ArtifactAnatomyCard";
import ConversionSummaryStrip from "./ConversionSummaryStrip";
import DeliveryChecklist from "./DeliveryChecklist";
import HandoffPipeline from "./HandoffPipeline";
import {
  DecisionTile,
  GateBadge,
  IssueList,
} from "./ConvertReportPrimitives";
import {
  buildGates,
  coverage,
  formatRelative,
  gateCardClass,
  humanDecision,
  nextStepClass,
  preflightMode,
  uncertaintyGateStatus,
} from "./ConvertReportShared";

export default function ConvertRunDetails({
  data,
  input,
  onConvert,
  downstream,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
  downstream?: ConvertDownstreamDestination | null;
}) {
  return (
    <details
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
        <CliEquivalentBlock command={data.cli_command_text} />
        <HandoffPipeline data={data} input={input} />
        <ConversionSummaryStrip data={data} input={input} />
        <ArtifactAnatomyCard data={data} input={input} />
        {input ? <ProductionEvidenceStrip input={input} /> : null}
        {input ? <PreflightDecisionPanel data={data} input={input} /> : null}
        {input ? <CheckCards data={data} input={input} /> : null}
        {input ? <InputStats input={input} /> : null}
        <DeliveryChecklist data={data} input={input} onConvert={onConvert} downstream={downstream} />
        <NextStepsPanel data={data} input={input} downstream={downstream} />
      </div>
    </details>
  );
}

function CliEquivalentBlock({ command }: { command: string }) {
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">
            CLI equivalent
          </h3>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            Same converter request as a reproducible terminal command.
          </p>
        </div>
        <CopyCliButton value={command} label="Copy CLI" ariaLabel="Copy CLI command" />
      </div>
      <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
        {command}
      </pre>
    </section>
  );
}

function NextStepsPanel({
  data,
  input,
  downstream,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  downstream?: ConvertDownstreamDestination | null;
}) {
  const steps = convertNextSteps(data, input, { downstream });
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
  const label = href.startsWith("#")
    ? "jump"
    : isCopyCliDestination(href)
      ? "open · CLI"
      : "open";
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

function ProductionEvidenceStrip({ input }: { input: ConvertPreflightInput }) {
  const uncertaintyCoverage = coverage(input);
  const uncertaintyStatus = uncertaintyGateStatus(input);
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
      tone: uncertaintyStatus,
      detail: "OpenMC tally uncertainty visibility for production review.",
    },
    {
      label: "max std_dev / mean",
      value:
        input.uncertainty?.max_rel == null
          ? "not evaluated"
          : formatRelative(input.uncertainty.max_rel),
      tone:
        input.uncertainty?.max_rel == null
          ? "skipped"
          : input.uncertainty.max_rel <= 0.05
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
                : item.tone === "fail"
                  ? "border-rose-400/25 bg-rose-400/[0.06]"
                  : item.tone === "skipped"
                    ? "border-[var(--edge)] bg-black/10"
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
            className={"rounded-lg border p-4 " + gateCardClass(gate.status)}
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
              {value == null ? "-" : String(value)}
            </div>
          </div>
        ))}
      </div>

      <IssueList title="Issues" items={input.issues} tone="rose" />
      <IssueList title="Warnings" items={input.warnings} tone="amber" />
    </section>
  );
}
