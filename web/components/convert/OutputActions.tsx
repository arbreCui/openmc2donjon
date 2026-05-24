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
  const actions = handoffActions(data, onConvert);
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Continue the handoff</h3>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            The normal post-conversion path is inspect evidence, preview ASCII,
            bundle the artifact, then hand the command record to the next workflow.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {data.converted ? "artifact ready" : data.dry_run ? "dry run" : "stopped"}
        </span>
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {actions.map((action) => (
          <ActionCard key={action.id} action={action} />
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {canConvertNow ? (
          <button type="button" onClick={onConvert} className="btn btn-primary">
            Convert now
          </button>
        ) : null}
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

interface HandoffAction {
  id: string;
  label: string;
  title: string;
  body: string;
  href?: string;
  disabled?: boolean;
  status: "ready" | "reference" | "blocked";
}

function handoffActions(
  data: ConvertResponse,
  onConvert?: () => void,
): HandoffAction[] {
  const outputReady = data.converted && data.output_exists;
  const canConvertNow = data.dry_run && data.ok && !data.output_exists && onConvert;
  return [
    {
      id: "inspect",
      label: "Evidence",
      title: "Inspect input HDF5",
      body: "Open mixture roster, energy mesh identity, ADF/SPH metadata, and production warnings.",
      href: `/inspect?path=${encodeURIComponent(data.input_path)}`,
      status: "reference",
    },
    {
      id: "preview",
      label: "ASCII",
      title: outputReady ? "Preview ASCII blocks" : "Preview waits for output",
      body: outputReady
        ? "Jump to the LCM ASCII signature, visible block tree, and first lines."
        : canConvertNow
          ? "Dry run passed. Convert writes the ASCII file before preview is available."
          : "The output file was not confirmed, so the preview cannot be opened yet.",
      href: outputReady ? "#ascii-output-preview" : undefined,
      disabled: !outputReady,
      status: outputReady ? "ready" : "blocked",
    },
    {
      id: "bundle",
      label: "Bundle",
      title: outputReady ? "Bundle handoff" : "Bundle after convert",
      body: outputReady
        ? "Open the bundle builder with MGXS and ASCII paths already filled."
        : "Package the input, ASCII output, summaries, and logs after conversion succeeds.",
      href: outputReady ? convertBundleHref(data) : undefined,
      disabled: !outputReady,
      status: outputReady ? "ready" : "blocked",
    },
    {
      id: "guide",
      label: "Command",
      title: "Open command guide",
      body: "Review when to use direct conversion, what it writes, and where it sits in the workflow map.",
      href: "/commands/direct-convert",
      status: "reference",
    },
  ];
}

function ActionCard({ action }: { action: HandoffAction }) {
  return (
    <article className={"rounded-md border p-3 " + actionCardClass(action.status)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
          {action.label}
        </span>
        {action.disabled || !action.href ? (
          <span className="text-[11px] text-[var(--fg-3)]">waiting</span>
        ) : (
          <ActionLink href={action.href} />
        )}
      </div>
      <h4 className="mt-2 text-sm font-semibold tracking-tight">{action.title}</h4>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
        {action.body}
      </p>
    </article>
  );
}

function ActionLink({ href }: { href: string }) {
  if (href.startsWith("#")) {
    return (
      <a href={href} className="text-[11px] text-[var(--accent-2)] hover:underline">
        jump
      </a>
    );
  }
  return (
    <Link href={href} className="text-[11px] text-[var(--accent-2)] hover:underline">
      open
    </Link>
  );
}

function actionCardClass(status: HandoffAction["status"]): string {
  if (status === "ready") {
    return "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-100";
  }
  if (status === "blocked") {
    return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  }
  return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-100";
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
