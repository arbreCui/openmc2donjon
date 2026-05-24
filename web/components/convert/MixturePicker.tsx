"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  HandoffInspection,
  MixtureSummary,
  api,
} from "@/lib/api";
import { parseMixtures } from "@/lib/convertCommand";

type LoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: HandoffInspection }
  | { kind: "error"; message: string; status?: number };

export default function MixturePicker({
  inputPath,
  value,
  onChange,
}: {
  inputPath: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [state, setState] = useState<LoadState>({ kind: "idle" });
  const selected = useMemo(() => new Set(parseMixtures(value) ?? []), [value]);

  useEffect(() => {
    setState({ kind: "idle" });
  }, [inputPath]);

  async function loadMixtures() {
    const path = inputPath.trim();
    if (!path) {
      setState({ kind: "error", message: "Enter an input HDF5 path first." });
      return;
    }
    setState({ kind: "loading" });
    try {
      setState({ kind: "ok", data: await api.inspect(path) });
    } catch (err) {
      setState(toLoadError(err));
    }
  }

  function setSelected(names: Iterable<string>) {
    onChange(Array.from(names).join("\n"));
  }

  function toggle(name: string) {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setSelected(next);
  }

  const mixtures = state.kind === "ok" ? state.data.mixtures : [];
  const selectedCount = mixtures.filter((mixture) => selected.has(mixture.name)).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void loadMixtures()}
          className="btn btn-secondary"
          disabled={state.kind === "loading"}
        >
          {state.kind === "loading" ? "Loading mixtures…" : "Load mixtures"}
        </button>
        {mixtures.length > 0 ? (
          <>
            <button
              type="button"
              onClick={() => setSelected(mixtures.map((mixture) => mixture.name))}
              className="btn btn-secondary"
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() =>
                setSelected(fissionableMixtures(mixtures).map((mixture) => mixture.name))
              }
              className="btn btn-secondary"
            >
              Fissionable only
            </button>
            <button
              type="button"
              onClick={() => onChange("")}
              className="btn btn-secondary"
            >
              Clear
            </button>
            <span className="text-[12px] text-[var(--fg-3)] tab-num">
              {selectedCount} / {mixtures.length} selected
            </span>
          </>
        ) : null}
      </div>

      <LoadStateView state={state} selected={selected} onToggle={toggle} />
    </div>
  );
}

function LoadStateView({
  state,
  selected,
  onToggle,
}: {
  state: LoadState;
  selected: Set<string>;
  onToggle: (name: string) => void;
}) {
  if (state.kind === "idle") {
    return (
      <p className="text-[12px] text-[var(--fg-3)]">
        Load mixtures from the selected HDF5 to choose a subset visually.
      </p>
    );
  }
  if (state.kind === "loading") {
    return (
      <p className="text-[12px] text-[var(--fg-2)] tab-num">
        Reading HDF5 mixture roster…
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="rounded-md border border-amber-400/25 bg-amber-400/[0.06] px-3 py-2">
        <div className="text-sm font-semibold text-amber-300">
          Mixture load failed{state.status ? ` (HTTP ${state.status})` : ""}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </div>
    );
  }
  const mixtures = state.data.mixtures;
  if (mixtures.length === 0) {
    return (
      <p className="text-[12px] text-[var(--fg-3)]">
        No mixtures were reported by the HDF5 inspection endpoint.
      </p>
    );
  }
  return (
    <div className="grid max-h-72 gap-2 overflow-auto rounded-md border border-[var(--edge)] bg-black/10 p-2 sm:grid-cols-2 lg:grid-cols-3">
      {mixtures.map((mixture) => (
        <MixtureChip
          key={mixture.name}
          mixture={mixture}
          active={selected.has(mixture.name)}
          onClick={() => onToggle(mixture.name)}
        />
      ))}
    </div>
  );
}

function MixtureChip({
  mixture,
  active,
  onClick,
}: {
  mixture: MixtureSummary;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "min-w-0 rounded-md border px-3 py-2 text-left transition " +
        (active
          ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-100"
          : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)] hover:border-[var(--edge-bright)]")
      }
      aria-pressed={active}
    >
      <div className="truncate font-mono text-[12px]">{mixture.name}</div>
      <div className="mt-1 flex flex-wrap gap-1 text-[10px] uppercase tracking-wider">
        <Badge active={active} label={mixture.fissionable ? "fiss" : "non-fiss"} />
        {mixture.adf_faces.length > 0 ? (
          <Badge active={active} label={`ADF ${mixture.adf_faces.length}`} />
        ) : null}
        {mixture.sph ? <Badge active={active} label="SPH" /> : null}
      </div>
    </button>
  );
}

function Badge({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={
        "rounded border px-1.5 py-0.5 " +
        (active
          ? "border-emerald-200/25 text-emerald-100"
          : "border-[var(--edge)] text-[var(--fg-3)]")
      }
    >
      {label}
    </span>
  );
}

function fissionableMixtures(mixtures: MixtureSummary[]) {
  return mixtures.filter((mixture) => mixture.fissionable === true);
}

function toLoadError(err: unknown): Extract<LoadState, { kind: "error" }> {
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
