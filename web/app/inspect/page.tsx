"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  ApiError,
  HandoffInspection,
  MixtureDetail,
  api,
} from "@/lib/api";
import { useSettings } from "@/lib/settings";
import CrossSectionPlot from "@/components/inspect/CrossSectionPlot";
import MixtureTable from "@/components/inspect/MixtureTable";
import Summary from "@/components/inspect/Summary";

const FALLBACK_PLACEHOLDER = "/path/to/mgxs_library.h5";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: HandoffInspection; path: string }
  | { kind: "error"; message: string; status?: number };

type MixtureState =
  | { kind: "idle" }
  | { kind: "loading"; mixture: string }
  | { kind: "ok"; data: MixtureDetail }
  | { kind: "error"; mixture: string; message: string; status?: number };

export default function InspectPage() {
  const [path, setPath] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [selectedMixture, setSelectedMixture] = useState<string | null>(null);
  const [mixtureState, setMixtureState] = useState<MixtureState>({
    kind: "idle",
  });
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  // Show the saved default as a *placeholder* only - never pre-fill the
  // value, so users who want to type a new path don't have to clear
  // the input first. ``FALLBACK_PLACEHOLDER`` keeps the field signalling
  // its intent before the user has saved anything in Settings. An
  // explicit "Use saved prefix" button below the form copies the saved
  // value into the input when the user actually wants to save typing.
  const placeholder = savedPrefix || FALLBACK_PLACEHOLDER;
  const canUseSavedPrefix =
    settingsHydrated && savedPrefix !== "" && !path.startsWith(savedPrefix);

  const inspect = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = path.trim();
    if (!trimmed) {
      setState({ kind: "error", message: "Enter a path first." });
      return;
    }
    setState({ kind: "loading" });
    setSelectedMixture(null);
    setMixtureState({ kind: "idle" });
    try {
      const data = await api.inspect(trimmed);
      setState({ kind: "ok", data, path: trimmed });
    } catch (err) {
      setState(toErrorState(err));
    }
  };

  const handlePickMixture = useCallback((name: string) => {
    setSelectedMixture(name);
  }, []);

  useEffect(() => {
    if (state.kind !== "ok" || selectedMixture == null) return;
    const requested = selectedMixture;
    setMixtureState({ kind: "loading", mixture: requested });
    let cancelled = false;
    api
      .inspectMixture(state.path, requested, 0)
      .then((data) => {
        if (cancelled) return;
        setMixtureState({ kind: "ok", data });
      })
      .catch((err) => {
        if (cancelled) return;
        const base = toErrorState(err);
        if (base.kind === "error") {
          setMixtureState({
            kind: "error",
            mixture: requested,
            message: base.message,
            status: base.status,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [state, selectedMixture]);

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
            show its file-level summary, mixture roster, and per-mixture
            reaction-rate spectrum.
          </p>
        </header>

        <form
          className="glass rounded-xl p-4 flex flex-col sm:flex-row sm:items-stretch gap-3"
          onSubmit={inspect}
        >
          <input
            type="text"
            placeholder={placeholder}
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
          <FileResultView state={state} />
        </section>

        {state.kind === "ok" ? (
          <section className="mt-6 space-y-6">
            <MixtureTable
              mixtures={state.data.mixtures}
              selectedName={selectedMixture}
              onSelect={handlePickMixture}
            />
            <MixturePanel
              handoff={state.data}
              mixtureState={mixtureState}
              selectedMixture={selectedMixture}
            />
          </section>
        ) : null}
      </div>
    </main>
  );
}

function FileResultView({ state }: { state: State }) {
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
  return <Summary data={state.data} />;
}

function MixturePanel({
  handoff,
  mixtureState,
  selectedMixture,
}: {
  handoff: HandoffInspection;
  mixtureState: MixtureState;
  selectedMixture: string | null;
}) {
  if (selectedMixture == null) {
    return (
      <p className="text-sm text-[var(--fg-3)]">
        Click a row above to load its reaction-rate cross sections.
      </p>
    );
  }
  if (mixtureState.kind === "idle" || mixtureState.kind === "loading") {
    return (
      <p className="text-sm text-[var(--fg-2)] tab-num">
        Loading <span className="font-mono">{selectedMixture}</span>…
      </p>
    );
  }
  if (mixtureState.kind === "error") {
    return (
      <div className="glass rounded-xl p-5 border-rose-500/20">
        <div className="text-sm font-semibold text-rose-300">
          {mixtureState.status
            ? `HTTP ${mixtureState.status}`
            : "Mixture read failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">
          {mixtureState.message}
        </div>
      </div>
    );
  }
  const detail = mixtureState.data;
  const bounds = handoff.energy_bounds ?? [];
  return (
    <div className="space-y-3">
      <MixtureMeta detail={detail} />
      {bounds.length >= 2 ? (
        <CrossSectionPlot
          energyBounds={bounds}
          crossSections={detail.cross_sections}
          mixtureName={detail.mixture}
        />
      ) : (
        <div className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]">
          Cannot plot: the handoff has no <code>energy_bounds</code>{" "}
          (legacy file). Cross sections are still available via the API.
        </div>
      )}
    </div>
  );
}

function MixtureMeta({ detail }: { detail: MixtureDetail }) {
  const items: { label: string; value: string }[] = [];
  items.push({ label: "Mixture", value: detail.mixture });
  items.push({
    label: "Groups",
    value: detail.energy_groups == null ? "—" : String(detail.energy_groups),
  });
  items.push({
    label: "Legendre",
    value:
      detail.legendre_order == null ? "—" : `P${detail.legendre_order}`,
  });
  items.push({
    label: "Volume",
    value: detail.volume == null ? "—" : detail.volume.toFixed(3),
  });
  items.push({
    label: "Temperature",
    value:
      detail.temperature == null
        ? "—"
        : `${detail.temperature.toFixed(0)} K`,
  });
  if (detail.scatter) {
    items.push({
      label: "Scatter moment",
      value: `P${detail.scatter.moment_index}`,
    });
  }
  return (
    <div className="glass rounded-xl p-4 flex flex-wrap gap-x-6 gap-y-2 text-sm tab-num">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col">
          <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            {it.label}
          </span>
          <span className="font-mono">{it.value}</span>
        </div>
      ))}
    </div>
  );
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
