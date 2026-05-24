"use client";

import { useEffect, useState } from "react";
import { ApiError, TextPreview, api } from "@/lib/api";
import { analyzeDonjonAsciiPreview } from "@/lib/asciiPreview";

type PreviewState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: TextPreview }
  | { kind: "error"; message: string; status?: number };

export default function AsciiPreview({ path }: { path: string }) {
  const [state, setState] = useState<PreviewState>({ kind: "idle" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .textPreview(path)
      .then((data) => {
        if (!cancelled) setState({ kind: "ok", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState(toPreviewError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            ASCII output preview
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            First bounded slice of the generated DRAGON/DONJON text file.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          read-only
        </span>
      </div>

      <div className="mt-3">
        <PreviewBody state={state} />
      </div>
    </section>
  );
}

function PreviewBody({ state }: { state: PreviewState }) {
  if (state.kind === "idle" || state.kind === "loading") {
    return (
      <div className="rounded-md border border-[var(--edge)] bg-black/20 px-3 py-3 text-sm text-[var(--fg-2)]">
        Loading ASCII preview…
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="rounded-md border border-amber-400/25 bg-amber-400/[0.06] px-3 py-3">
        <div className="text-sm font-semibold text-amber-300">
          Preview unavailable{state.status ? ` (HTTP ${state.status})` : ""}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </div>
    );
  }
  const { data } = state;
  const analysis = analyzeDonjonAsciiPreview(data.text);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-[var(--fg-2)] tab-num">
        <span>{data.displayed_lines} lines</span>
        <span>
          {formatSize(data.preview_bytes)} / {formatSize(data.file_size)}
        </span>
        {data.truncated ? (
          <span className="text-amber-300">
            truncated by {data.truncated_by.join(" + ")}
          </span>
        ) : (
          <span className="text-emerald-300">complete within preview limit</span>
        )}
      </div>
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
        <div className="grid gap-2 md:grid-cols-[180px_1fr]">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              Handoff signature
            </div>
            <div
              className={
                "mt-1 rounded border px-2 py-1 font-mono text-[12px] " +
                (analysis.likelyDonjonAscii
                  ? "border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-100"
                  : "border-amber-300/25 bg-amber-300/[0.08] text-amber-100")
              }
            >
              {analysis.signature ?? "not found"}
            </div>
            <div className="mt-1 text-[12px] text-[var(--fg-3)]">
              {analysis.format === "unknown"
                ? "format unknown"
                : `${analysis.format} ASCII`}
            </div>
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              Visible block scan
            </div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {analysis.blockHits.map((hit) => (
                <BlockChip key={hit.id} label={hit.label} present={hit.present} />
              ))}
            </div>
            {analysis.notes.length > 0 ? (
              <ul className="mt-2 space-y-1 text-[12px] text-amber-100">
                {analysis.notes.map((note) => (
                  <li key={note}>- {note}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-[12px] text-emerald-200">
                Signature and core visible blocks look consistent in this preview slice.
              </p>
            )}
          </div>
        </div>
      </div>
      <pre className="max-h-[34rem] overflow-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-3 font-mono text-[12px] leading-5 text-[var(--fg-1)]">
        {data.text || "(empty file)"}
      </pre>
    </div>
  );
}

function BlockChip({ label, present }: { label: string; present: boolean }) {
  return (
    <span
      className={
        "rounded border px-2 py-1 text-[11px] " +
        (present
          ? "border-emerald-300/20 bg-emerald-300/[0.06] text-emerald-100"
          : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-3)]")
      }
    >
      {present ? "✓ " : ""}
      {label}
    </span>
  );
}

function toPreviewError(err: unknown): Extract<PreviewState, { kind: "error" }> {
  if (err instanceof ApiError) {
    return {
      kind: "error",
      status: err.status,
      message: err.detail ?? err.message,
    };
  }
  if (err instanceof Error) return { kind: "error", message: err.message };
  return { kind: "error", message: "Unknown error." };
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
