"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { ConvertResponse } from "@/lib/api";
import { convertBundleHref } from "@/lib/convertNextSteps";

export default function OutputActions({
  data,
  onConvert,
}: {
  data: ConvertResponse;
  onConvert?: () => void;
}) {
  const notice = outputNotice(data);
  const canConvertNow = data.dry_run && data.ok && !data.output_exists && onConvert;
  const pathLabel =
    data.converted && data.output_exists ? "Copy DONJON path" : "Copy target path";
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Next actions</h3>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            Move from conversion result to input QA, command reference, or DONJON handoff.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {data.converted ? "artifact ready" : data.dry_run ? "dry run" : "stopped"}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          href={`/inspect?path=${encodeURIComponent(data.input_path)}`}
          className="btn btn-secondary"
        >
          Inspect input
        </Link>
        {canConvertNow ? (
          <button type="button" onClick={onConvert} className="btn btn-primary">
            Convert now
          </button>
        ) : null}
        {data.converted && data.output_exists ? (
          <a href="#ascii-output-preview" className="btn btn-secondary">
            Preview ASCII
          </a>
        ) : null}
        {data.converted && data.output_exists ? (
          <Link href={convertBundleHref(data)} className="btn btn-secondary">
            Bundle handoff
          </Link>
        ) : null}
        <Link href="/commands/direct-convert" className="btn btn-secondary">
          Command guide
        </Link>
        <CopyCliButton
          value={data.output_path}
          label={pathLabel}
          ariaLabel={pathLabel}
        />
        <CopyCliButton
          value={data.cli_command_text}
          label="Copy CLI"
          ariaLabel="Copy CLI command"
        />
      </div>

      <div
        className={
          "mt-3 rounded-md border px-3 py-2 text-sm " + outputNoticeClass(notice.tone)
        }
      >
        <span className="font-semibold">{notice.title}</span>
        <span className="ml-2 text-[var(--fg-1)]">{notice.body}</span>
      </div>
    </section>
  );
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
      body: "Review the ASCII preview, then pass this path to the DONJON-side workflow.",
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
