import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import { convertDecision } from "@/lib/convertDecision";
import {
  convertBundleHref,
  convertWriterCompareHref,
} from "@/lib/convertNextSteps";
import { convertWriterBackendResultLabel } from "@/lib/convertWriterBackend";
import { Meta } from "./ConvertReportPrimitives";
import {
  formatSize,
  primaryNextActionClass,
  primaryOutcomeClass,
  validationLabel,
} from "./ConvertReportShared";

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

      <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
        <Meta label="Input" value={data.input_path} mono />
        <Meta label="Output" value={data.output_path} mono />
        <Meta
          label="Output size"
          value={data.output_size == null ? "-" : formatSize(data.output_size)}
        />
        <Meta
          label="Writer"
          value={convertWriterBackendResultLabel(data.writer_backend)}
        />
        <Meta label="Validation" value={validationLabel(data)} />
      </dl>

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

      <ul className="mt-3 grid gap-1.5 text-[12px] leading-5 text-[var(--fg-1)] md:grid-cols-2">
        {decision.reasons.map((reason) => (
          <li key={reason} className="flex gap-2">
            <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
            <span>{reason}</span>
          </li>
        ))}
      </ul>

      <div
        className={
          "mt-4 rounded-md border px-3 py-2 " +
          primaryNextActionClass(decision.tone)
        }
      >
        <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
          {decision.nextAction.label}
        </div>
        <p className="mt-1 text-[12px] leading-5 text-[var(--fg-1)]">
          {decision.nextAction.body}
        </p>
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
