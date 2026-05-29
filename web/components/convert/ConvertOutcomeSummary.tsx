import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import { convertDecision } from "@/lib/convertDecision";
import {
  convertBundleHref,
  convertWriterCompareHref,
} from "@/lib/convertNextSteps";
import {
  convertResultOverview,
  type ConvertResultOverviewTone,
} from "@/lib/convertResultOverview";
import { primaryOutcomeClass } from "./ConvertReportShared";

export default function ConvertOutcomeSummary({
  data,
  input,
  onConvert,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
}) {
  const headline = data.dry_run
    ? "Dry run complete"
    : data.converted
      ? "ASCII written"
      : "Conversion stopped";
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <div
            className={`text-sm font-semibold ${
              data.ok ? "text-emerald-300" : "text-rose-300"
            }`}
          >
            {data.ok ? "PASS" : "FAIL"}
          </div>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">
            {headline}
          </h2>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {data.format} / {data.writer_backend}
        </span>
      </div>

      <ResultOverview data={data} />

      <PrimaryOutcomeActions data={data} input={input} onConvert={onConvert} />
    </section>
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
        {converted && data.writer_backend === "pygan" ? (
          <Link href={convertWriterCompareHref(data)} className="btn btn-secondary">
            Validate PyGan
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

      <details className="mt-3 text-[12px]" open={decision.tone === "blocked"}>
        <summary className="cursor-pointer text-[var(--fg-2)] hover:text-[var(--fg-1)]">
          Why this state
        </summary>
        <ul className="mt-2 grid gap-1.5 leading-5 text-[var(--fg-1)] md:grid-cols-2">
          {decision.reasons.map((reason) => (
            <li key={reason} className="flex gap-2">
              <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function ResultOverview({ data }: { data: ConvertResponse }) {
  const tiles = convertResultOverview(data);
  return (
    <div className="mt-4 grid gap-2 lg:grid-cols-3">
      {tiles.map((tile) => (
        <article key={tile.id} className={"rounded-lg border px-3 py-2 " + resultTileClass(tile.tone)}>
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            {tile.label}
          </div>
          <div
            className={
              "mt-1 truncate text-sm font-semibold tracking-tight " +
              (tile.mono ? "font-mono" : "")
            }
            title={tile.value}
          >
            {tile.value}
          </div>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
            {tile.body}
          </p>
        </article>
      ))}
    </div>
  );
}

function resultTileClass(tone: ConvertResultOverviewTone): string {
  if (tone === "ready") {
    return "border-emerald-400/20 bg-emerald-400/[0.055] text-emerald-100";
  }
  if (tone === "pending") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
}
