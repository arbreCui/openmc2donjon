"use client";

import { FormEvent, useState } from "react";
import { ApiError, HandoffInspection, api } from "@/lib/api";
import MixtureTable from "@/components/inspect/MixtureTable";
import Summary from "@/components/inspect/Summary";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: HandoffInspection }
  | { kind: "error"; message: string; status?: number };

export default function InspectPage() {
  const [path, setPath] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = path.trim();
    if (!trimmed) {
      setState({ kind: "error", message: "Enter a path first." });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await api.inspect(trimmed);
      setState({ kind: "ok", data });
    } catch (err) {
      if (err instanceof ApiError) {
        setState({ kind: "error", message: err.message, status: err.status });
      } else if (err instanceof Error) {
        setState({ kind: "error", message: err.message });
      } else {
        setState({ kind: "error", message: "Unknown error." });
      }
    }
  };

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="grad-text">Inspect HDF5 handoff</span>
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-2)]">
            Read an MGXS HDF5 file produced by{" "}
            <code className="font-mono">openmc2donjon-export</code> or{" "}
            <code className="font-mono">openmc2donjon-from-openmc</code> and
            show its file-level summary and mixture roster.
          </p>
        </header>

        <form
          className="glass rounded-xl p-4 flex flex-col sm:flex-row sm:items-stretch gap-3"
          onSubmit={submit}
        >
          <input
            type="text"
            placeholder="/path/to/mgxs_library.h5"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="flex-1 min-w-0 px-3 py-2 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
            spellCheck={false}
            autoComplete="off"
            aria-label="HDF5 handoff path"
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={state.kind === "loading"}
          >
            {state.kind === "loading" ? "Reading…" : "Inspect"}
          </button>
        </form>

        <section className="mt-6">
          <ResultView state={state} />
        </section>
      </div>
    </main>
  );
}

function ResultView({ state }: { state: State }) {
  if (state.kind === "idle") {
    return (
      <p className="text-sm text-[var(--fg-3)]">
        Tip: with{" "}
        <code className="font-mono">openmc2donjon serve --mock</code>{" "}
        running, any path (even a fake one) returns the bundled
        C5G7-shape fixture so you can preview the layout.
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
    <div className="space-y-6">
      <Summary data={state.data} />
      <MixtureTable mixtures={state.data.mixtures} />
    </div>
  );
}
