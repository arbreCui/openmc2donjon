"use client";

import { useEffect, useState } from "react";
import { ApiError, TextPreview, api } from "@/lib/api";

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
      <pre className="max-h-[34rem] overflow-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-3 font-mono text-[12px] leading-5 text-[var(--fg-1)]">
        {data.text || "(empty file)"}
      </pre>
    </div>
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
