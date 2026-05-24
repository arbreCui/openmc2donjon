"use client";

import { FormEvent, useRef, useState } from "react";
import { ApiError, SphLoopSummary, api } from "@/lib/api";
import { useSettings } from "@/lib/settings";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import AuditSummary from "@/components/audit/AuditSummary";
import ConvergenceChart from "@/components/audit/ConvergenceChart";
import AuditChecks from "@/components/audit/AuditChecks";
import AuditTimeline from "@/components/audit/AuditTimeline";
import AuditQuality from "@/components/audit/AuditQuality";

const FALLBACK_PLACEHOLDER = "/path/to/sph_loop_summary.json";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: SphLoopSummary; path: string }
  | { kind: "error"; message: string; status?: number };

export default function AuditPage() {
  const [path, setPath] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [browserOpen, setBrowserOpen] = useState(false);
  const auditButtonRef = useRef<HTMLButtonElement | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const placeholder = savedPrefix || FALLBACK_PLACEHOLDER;
  const canUseSavedPrefix =
    settingsHydrated && savedPrefix !== "" && !path.startsWith(savedPrefix);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = path.trim();
    if (!trimmed) {
      setState({ kind: "error", message: "Enter a path first." });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await api.audit(trimmed);
      setState({ kind: "ok", data, path: trimmed });
    } catch (err) {
      setState(toErrorState(err));
    }
  };

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="grad-text">Audit SPH loop run</span>
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-2)]">
            Read the JSON summary produced by{" "}
            <code className="font-mono">openmc2donjon run-sph-loop</code>{" "}
            (schema <code className="font-mono">openmc2donjon.sph-loop.v1</code>)
            and show the headline result: decision, iteration count,
            acceptance gate, and production audit. Detailed convergence
            and per-iteration tables land in later slices.
          </p>
        </header>

        <form
          className="glass rounded-xl p-4 flex flex-col sm:flex-row sm:items-stretch gap-3"
          onSubmit={submit}
        >
          <input
            type="text"
            placeholder={placeholder}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="flex-1 min-w-0 px-3 py-2 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
            spellCheck={false}
            autoComplete="off"
            aria-label="SPH loop summary path"
          />
          <button
            type="button"
            onClick={() => setBrowserOpen(true)}
            className="btn btn-secondary"
          >
            Browse…
          </button>
          <button
            ref={auditButtonRef}
            type="submit"
            className="btn btn-primary"
            disabled={state.kind === "loading"}
          >
            {state.kind === "loading" ? "Reading…" : "Audit"}
          </button>
        </form>

        <FileBrowserModal
          open={browserOpen}
          initialPath={pickBrowserStart(path.trim() || savedPrefix)}
          extensions={["json"]}
          fileTypeLabel="JSON"
          chipLabel="JSON"
          recentScope="json"
          onClose={() => setBrowserOpen(false)}
          onSelect={(picked) => {
            setPath(picked);
            setBrowserOpen(false);
            auditButtonRef.current?.focus();
          }}
        />

        {canUseSavedPrefix ? (
          <button
            type="button"
            onClick={() => setPath(savedPrefix)}
            className="mt-2 text-[12px] text-[var(--accent-2)] hover:underline"
          >
            Use saved prefix:{" "}
            <code className="font-mono">{savedPrefix}</code>
          </button>
        ) : null}

        <section className="mt-6">
          <Result state={state} />
        </section>
      </div>
    </main>
  );
}

function Result({ state }: { state: State }) {
  if (state.kind === "idle") {
    return (
      <p className="text-sm text-[var(--fg-3)]">
        Tip: with{" "}
        <code className="font-mono">openmc2donjon serve --mock</code>{" "}
        running, any path returns the bundled SPH loop summary so you
        can preview the layout.
      </p>
    );
  }
  if (state.kind === "loading") {
    return <p className="text-sm text-[var(--fg-2)] tab-num">Reading…</p>;
  }
  if (state.kind === "error") {
    return (
      <div className="glass rounded-xl p-5 border-rose-500/20">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Request failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <AuditSummary data={state.data} path={state.path} />
      <AuditQuality quality={state.data.quality} />
      <ConvergenceChart
        points={state.data.convergence}
        sphTolerance={state.data.sph_change_tolerance}
        fluxTolerance={state.data.flux_ratio_tolerance}
      />
      <AuditChecks
        acceptance={state.data.acceptance}
        productionAudit={state.data.production_audit}
      />
      <AuditTimeline
        rows={state.data.audit_rows}
        solves={state.data.solves}
        postprocesses={state.data.postprocesses}
        workflows={state.data.workflows}
      />
    </div>
  );
}

function pickBrowserStart(savedPrefix: string): string {
  const trimmed = savedPrefix.trim();
  if (!trimmed) return "~";
  const lastSlash = trimmed.lastIndexOf("/");
  if (lastSlash >= 0 && lastSlash < trimmed.length - 1) {
    const tail = trimmed.slice(lastSlash + 1);
    if (tail.includes(".")) {
      return trimmed.slice(0, lastSlash + 1);
    }
  }
  return trimmed;
}

function toErrorState(err: unknown): State {
  if (err instanceof ApiError) {
    return { kind: "error", message: err.message, status: err.status };
  }
  if (err instanceof Error) {
    return { kind: "error", message: err.message };
  }
  return { kind: "error", message: "Unknown error." };
}
