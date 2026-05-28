import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import { GateBadge } from "./ConvertReportPrimitives";
import {
  buildGates,
  compactEquivalence,
  compactUncertainty,
  decisionTileClass,
  gateCardClass,
  humanDecision,
  validationLabel,
} from "./ConvertReportShared";

interface ValidationSummaryItem {
  label: string;
  value: string;
  detail: string;
  tone: "pass" | "warn" | "fail" | "accent" | "neutral";
}

export default function ConvertValidationSummary({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput;
}) {
  const items = buildValidationSummaryItems(data, input);
  const production = data.cli_command.includes("--production");
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Validation summary
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            A user-facing snapshot of whether this HDF5 handoff is ready to
            write. Technical gate evidence is kept in the details section.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {production ? "production preset" : "standard checks"}
        </span>
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-6">
        {items.map((item) => (
          <ValidationTile key={item.label} item={item} />
        ))}
      </div>
      <ProductionGateHighlights gates={buildGates(data, input)} />
      <ValidationIssuePreview input={input} />
    </section>
  );
}

function ProductionGateHighlights({
  gates,
}: {
  gates: ReturnType<typeof buildGates>;
}) {
  return (
    <div className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">
            Gate highlights
          </h3>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            The visible production checks that decide whether the handoff is
            safe to write or package.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          contract + physics
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        {gates.map((gate) => (
          <article
            key={gate.title}
            className={"rounded-md border px-3 py-2 " + gateCardClass(gate.status)}
          >
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[12px] font-semibold tracking-tight">
                {gate.title}
              </h4>
              <GateBadge status={gate.status} />
            </div>
            <p className="mt-2 text-[11px] leading-4 text-[var(--fg-2)]">
              {gate.summary}
            </p>
            <div className="mt-2 truncate font-mono text-[11px] text-[var(--fg-1)]">
              {gate.detail}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function ValidationTile({ item }: { item: ValidationSummaryItem }) {
  return (
    <article className={"rounded-md border px-3 py-2 " + decisionTileClass(item.tone)}>
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
        {item.label}
      </div>
      <div className="mt-1 truncate font-mono text-[13px]" title={item.value}>
        {item.value}
      </div>
      <p className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
        {item.detail}
      </p>
    </article>
  );
}

function ValidationIssuePreview({ input }: { input: ConvertPreflightInput }) {
  const issue = input.issues[0] ?? null;
  const warning = input.warnings[0] ?? null;
  if (!issue && !warning) return null;
  return (
    <div className="mt-4 grid gap-2 md:grid-cols-2">
      {issue ? (
        <div className="rounded-md border border-rose-300/20 bg-rose-300/[0.055] px-3 py-2 text-sm text-rose-100">
          <span className="font-semibold">First issue:</span>{" "}
          <span className="text-[var(--fg-1)]">{issue}</span>
        </div>
      ) : null}
      {warning ? (
        <div className="rounded-md border border-amber-300/20 bg-amber-300/[0.055] px-3 py-2 text-sm text-amber-100">
          <span className="font-semibold">First warning:</span>{" "}
          <span className="text-[var(--fg-1)]">{warning}</span>
        </div>
      ) : null}
    </div>
  );
}

function buildValidationSummaryItems(
  data: ConvertResponse,
  input: ConvertPreflightInput,
): ValidationSummaryItem[] {
  const moments = input.legendre_order == null ? "?" : String(input.legendre_order + 1);
  const uncertainty = compactUncertainty(input);
  return [
    {
      label: "Result",
      value: validationLabel(data),
      detail: data.preflight ? humanDecision(data.preflight.decision) : "no preflight payload",
      tone: data.preflight_ok && input.ok ? "pass" : "fail",
    },
    {
      label: "Issues",
      value: String(input.issues.length),
      detail: input.issues.length === 0 ? "No blocking input issues." : "Resolve before writing.",
      tone: input.issues.length === 0 ? "pass" : "fail",
    },
    {
      label: "Warnings",
      value: String(input.warnings.length),
      detail: input.warnings.length === 0 ? "No audit warnings." : "Review before delivery.",
      tone: input.warnings.length === 0 ? "pass" : "warn",
    },
    {
      label: "Mesh",
      value: input.energy_mesh_name ?? input.energy_mesh_id ?? "custom",
      detail: input.energy_mesh_id ? "Known group structure." : "Custom or unidentified mesh.",
      tone: input.energy_mesh_id ? "pass" : "warn",
    },
    {
      label: "Shape",
      value: `${input.mixtures ?? "?"} mixes / ${input.energy_groups ?? "?"}g`,
      detail: `${moments} Legendre moment(s), ${input.state_points ?? "?"} state point(s).`,
      tone: "neutral",
    },
    {
      label: "Equivalence",
      value: compactEquivalence(input),
      detail: uncertainty,
      tone: input.adf_mixtures || input.sph_calculations ? "accent" : "neutral",
    },
  ];
}
