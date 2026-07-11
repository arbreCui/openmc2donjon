"use client";

import { useEffect, useState } from "react";
import { ApiError, api, type BundleInspection } from "@/lib/api";

type ManifestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; data: BundleInspection }
  | { kind: "missing"; message: string }
  | { kind: "error"; message: string };

export default function BundleManifestProbe({
  manifestPath,
  enabled,
  onManifestReady,
}: {
  manifestPath: string;
  enabled: boolean;
  /**
   * Reports whether the manifest was found on disk, so the parent can gate
   * manifest-dependent hrefs (e.g. the DONJON guide's manifest= param).
   * Pass a stable callback (a useState setter): it is an effect dependency.
   */
  onManifestReady?: (ready: boolean) => void;
}) {
  const [state, setState] = useState<ManifestState>({ kind: "idle" });

  useEffect(() => {
    if (!enabled) {
      setState({ kind: "idle" });
      onManifestReady?.(false);
      return;
    }
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .inspectBundle(manifestPath)
      .then((data) => {
        if (cancelled) return;
        setState({ kind: "ready", data });
        onManifestReady?.(true);
      })
      .catch((err) => {
        if (cancelled) return;
        onManifestReady?.(false);
        if (err instanceof ApiError && err.status === 404) {
          setState({
            kind: "missing",
            message:
              err.detail ??
              "Bundle manifest has not been written yet. Run the bundle command first.",
          });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.detail ?? err.message
            : err instanceof Error
              ? err.message
              : "Unknown bundle manifest error";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, manifestPath, onManifestReady]);

  if (!enabled || state.kind === "idle") return null;

  return (
    <div className="mt-3 rounded-md border border-current/15 bg-black/15 px-3 py-2 text-[12px]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="font-semibold tracking-tight">Bundle manifest status</div>
        <span
          className={
            "rounded border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] " +
            badgeClass(state)
          }
        >
          {badgeLabel(state)}
        </span>
      </div>
      <ManifestBody state={state} manifestPath={manifestPath} />
    </div>
  );
}

function ManifestBody({
  state,
  manifestPath,
}: {
  state: ManifestState;
  manifestPath: string;
}) {
  if (state.kind === "loading") {
    return (
      <p className="mt-1 text-[var(--fg-2)]">
        Checking <span className="font-mono">{manifestPath}</span>…
      </p>
    );
  }
  if (state.kind === "missing") {
    return (
      <p className="mt-1 text-[var(--fg-2)]">
        {state.message} Run the bundle command, then use the validation command
        against <span className="font-mono">{manifestPath}</span>.
      </p>
    );
  }
  if (state.kind === "error") {
    return <p className="mt-1 text-amber-100">{state.message}</p>;
  }
  if (state.kind !== "ready") return null;

  const failing = state.data.artifacts.filter((artifact) => !artifact.ok);
  return (
    <div className="mt-2 space-y-2">
      <div className="grid gap-2 md:grid-cols-3">
        <ManifestStat label="decision" value={state.data.decision} />
        <ManifestStat
          label="artifacts"
          value={`${state.data.artifact_count} checked`}
        />
        <ManifestStat
          label="result"
          value={state.data.ok ? "ready to share" : "needs attention"}
        />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {state.data.artifacts.slice(0, 6).map((artifact) => (
          <span
            key={`${artifact.label}:${artifact.path}`}
            className={
              "rounded border px-2 py-1 font-mono text-[11px] " +
              (artifact.ok
                ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100"
                : "border-amber-300/25 bg-amber-300/10 text-amber-100")
            }
            title={artifact.path}
          >
            {artifact.label}
          </span>
        ))}
      </div>
      {failing.length ? (
        <p className="text-amber-100">
          {failing.length} artifact{failing.length === 1 ? "" : "s"} failed validation.
          Open the validate-bundle command for details.
        </p>
      ) : (
        <p className="text-[var(--fg-2)]">
          Manifest and artifacts validate locally. This is the handoff record to
          archive or send with the ASCII output.
        </p>
      )}
    </div>
  );
}

function ManifestStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-current/10 bg-black/10 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-60">
        {label}
      </div>
      <div className="mt-0.5 truncate font-mono text-[11px]" title={value}>
        {value}
      </div>
    </div>
  );
}

function badgeLabel(state: ManifestState): string {
  if (state.kind === "loading") return "checking";
  if (state.kind === "ready") return state.data.ok ? "valid" : "failed";
  if (state.kind === "missing") return "not written";
  return "error";
}

function badgeClass(state: ManifestState): string {
  if (state.kind === "ready" && state.data.ok) {
    return "border-emerald-300/20 bg-emerald-300/10 text-emerald-100";
  }
  if (state.kind === "loading") {
    return "border-cyan-300/20 bg-cyan-300/10 text-cyan-100";
  }
  return "border-amber-300/25 bg-amber-300/10 text-amber-100";
}
