import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import EvidenceLadder from "@/components/EvidenceLadder";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import { convertDecision } from "@/lib/convertDecision";
import { converterEvidenceLadder } from "@/lib/evidenceLadder";
import { primaryOutcomeClass } from "./ConvertReportShared";

/**
 * Card 1 of the post-run report: a pure, immutable render of what the run
 * reported — verdict, "Why this state", Preview ASCII, and the Copy CLI
 * reproducibility record. Optional delivery actions live in the OutputActions
 * completed-handoff card so the two cards stay disjoint.
 */
export default function ConvertOutcomeSummary({
  data,
  input,
  onConvert,
  mockBackend = false,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
  mockBackend?: boolean;
}) {
  const headline = data.dry_run
    ? "Dry run complete"
    : data.converted
      ? "ASCII written"
      : "Conversion stopped";
  const verdict = data.preflight_ok
    ? "HANDOFF CONTRACT PASS"
    : data.ok
      ? "CONVERTER ACTION COMPLETE"
      : "HANDOFF CONTRACT FAIL";
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <div
            className={`text-sm font-semibold ${
              data.ok ? "text-emerald-300" : "text-rose-300"
            }`}
          >
            {verdict}
          </div>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">
            {headline}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mockBackend ? (
            <span className="rounded border border-amber-300/25 bg-amber-300/[0.08] px-2 py-1 text-[11px] uppercase tracking-wider text-amber-200">
              mock fixture
            </span>
          ) : null}
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {data.format} / {data.writer_backend}
          </span>
        </div>
      </div>

      <EvidenceLadder stages={converterEvidenceLadder(data, input)} />

      <PrimaryOutcomeActions
        data={data}
        input={input}
        onConvert={onConvert}
        mockBackend={mockBackend}
      />
    </section>
  );
}

function PrimaryOutcomeActions({
  data,
  input,
  onConvert,
  mockBackend,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
  mockBackend: boolean;
}) {
  const decision = convertDecision(data, input, { mockBackend });
  const converted = data.converted && data.output_exists;
  const readyToConvert = data.ok && data.dry_run;
  const stopped = !data.ok || (!data.dry_run && !converted);
  return (
    <section className={"mt-4 rounded-lg border p-4 " + primaryOutcomeClass(decision.tone)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-75">
            {converted
              ? "output artifact"
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
        <CopyCliButton
          value={data.cli_command_text}
          label="Copy CLI"
          ariaLabel="Copy CLI command"
        />
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
