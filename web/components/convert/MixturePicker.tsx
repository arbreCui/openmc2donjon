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
          {state.kind === "loading" ? "Inspecting HDF5…" : "Inspect HDF5"}
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
        Inspect the selected HDF5 to review the handoff summary and choose a
        mixture subset visually.
      </p>
    );
  }
  if (state.kind === "loading") {
    return (
      <p className="text-[12px] text-[var(--fg-2)] tab-num">
        Reading HDF5 inspection payload…
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
      <div className="space-y-3">
        <InspectionMiniSummary data={state.data} />
        <p className="text-[12px] text-[var(--fg-3)]">
          No mixtures were reported by the HDF5 inspection endpoint.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <InspectionMiniSummary data={state.data} />
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
    </div>
  );
}

function InspectionMiniSummary({ data }: { data: HandoffInspection }) {
  const denominator = data.calculation_count || data.mixture_count;
  const mesh = meshLabel(data);
  return (
    <div className="rounded-md border border-[var(--edge)] bg-white/[0.025] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--fg-3)]">
            Input inspection
          </div>
          <div className="mt-1 break-all font-mono text-[12px] text-[var(--fg-1)]">
            {data.path}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <StatusPill ok={data.ok} />
          <span className="rounded border border-cyan-300/25 bg-cyan-300/[0.08] px-2 py-1 text-[11px] font-medium text-cyan-200">
            {mesh}
          </span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        <MiniStat label="groups" value={formatNullable(data.energy_groups)} />
        <MiniStat label="moments" value={momentLabel(data.legendre_order)} />
        <MiniStat label="mixtures" value={formatNullable(data.mixture_count)} />
        <MiniStat
          label="fissionable"
          value={coverage(data.fissionable_mixtures, data.mixture_count)}
        />
        <MiniStat label="ADF" value={coverage(data.adf_mixtures, denominator)} />
        <MiniStat label="SPH" value={coverage(data.sph_calculations, denominator)} />
        <MiniStat label="H-factor" value={coverage(data.h_factor, denominator)} />
        <MiniStat
          label="transport"
          value={coverage(data.transport_total, denominator)}
        />
      </div>

      <div className="mt-3 grid gap-2 text-[12px] sm:grid-cols-2">
        <MiniDetail label="Scatter" value={scatterShapeLabel(data.scatter_shapes)} />
        <MiniDetail
          label="Issues"
          value={data.issues.length === 0 ? "none" : String(data.issues.length)}
          tone={data.issues.length === 0 ? "normal" : data.ok ? "warn" : "fail"}
        />
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-[var(--fg-3)]">
        Uncertainty and std_dev checks are run by the dry run / production
        acceptance; this card shows the quick HDF5 inspection payload.
      </p>

      {data.issues.length > 0 ? (
        <ul className="mt-2 space-y-1 rounded border border-amber-300/20 bg-amber-300/[0.05] p-2 text-[12px] text-amber-100">
          {data.issues.slice(0, 4).map((issue) => (
            <li key={issue}>- {issue}</li>
          ))}
          {data.issues.length > 4 ? (
            <li className="text-amber-200/70">
              + {data.issues.length - 4} more issue(s)
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

function StatusPill({ ok }: { ok: boolean }) {
  return (
    <span
      className={
        "rounded border px-2 py-1 text-[11px] font-semibold " +
        (ok
          ? "border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-200"
          : "border-rose-300/25 bg-rose-300/[0.08] text-rose-200")
      }
    >
      {ok ? "OK" : "CHECK"}
    </span>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-[var(--edge)] bg-black/10 px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-[13px] text-[var(--fg-0)]">{value}</div>
    </div>
  );
}

function MiniDetail({
  label,
  value,
  tone = "normal",
}: {
  label: string;
  value: string;
  tone?: "normal" | "warn" | "fail";
}) {
  const color =
    tone === "fail"
      ? "text-rose-200"
      : tone === "warn"
        ? "text-amber-200"
        : "text-[var(--fg-1)]";
  return (
    <div className="min-w-0 rounded border border-[var(--edge)] bg-black/10 px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className={`mt-1 truncate font-mono text-[12px] ${color}`}>{value}</div>
    </div>
  );
}

function meshLabel(data: HandoffInspection): string {
  if (!data.mesh_match) return "unknown mesh";
  return (
    data.mesh_match.short ??
    data.mesh_match.name ??
    data.mesh_match.id ??
    "known mesh"
  );
}

function momentLabel(order: number | null): string {
  if (order === null) return "-";
  return order === 0 ? "P0" : `P0-P${order}`;
}

function formatNullable(value: number | null): string | number {
  return value ?? "-";
}

function coverage(count: number, denominator: number): string {
  return denominator > 0 ? `${count}/${denominator}` : `${count}/?`;
}

function scatterShapeLabel(shapes: number[][]): string {
  if (shapes.length === 0) return "-";
  return shapes.map((shape) => `[${shape.join(",")}]`).join(" ");
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
