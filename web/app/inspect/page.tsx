"use client";

import { FormEvent, useState } from "react";
import {
  ApiError,
  HandoffInspection,
  MixtureSummary,
  api,
} from "@/lib/api";

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
          className="glass rounded-xl p-4 flex items-stretch gap-3"
          onSubmit={submit}
        >
          <input
            type="text"
            placeholder="/path/to/mgxs_library.h5"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="flex-1 px-3 py-2 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
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
  return <Summary data={state.data} />;
}

function Summary({ data }: { data: HandoffInspection }) {
  const okBadge = data.ok ? (
    <span className="text-emerald-300 font-semibold">OK</span>
  ) : (
    <span className="text-rose-300 font-semibold">FAIL</span>
  );
  return (
    <div className="space-y-6">
      <div className="glass rounded-xl p-5">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
              Path
            </div>
            <div className="font-mono text-sm break-all">{data.path}</div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            {okBadge}
            {data.mesh_match ? (
              <span
                className="px-2 py-0.5 rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-emerald-200 text-[12px]"
                title={data.mesh_match.description ?? undefined}
              >
                {data.mesh_match.short ??
                  data.mesh_match.name ??
                  data.mesh_match.id}
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-md border border-[var(--edge)] bg-white/[0.03] text-[var(--fg-3)] text-[12px]">
                no mesh match
              </span>
            )}
          </div>
        </div>

        <dl className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-4 tab-num text-sm">
          <Stat label="Mixtures" value={data.mixture_count} />
          <Stat
            label="Energy groups"
            value={data.energy_groups ?? "—"}
          />
          <Stat
            label="Legendre"
            value={data.legendre_order == null ? "—" : `P${data.legendre_order}`}
          />
          <Stat
            label="State points"
            value={data.state_points ?? data.calculation_count}
          />
          <Stat
            label="Fissionable"
            value={`${data.fissionable_mixtures} / ${data.mixture_count}`}
          />
          <Stat
            label="ADF mixtures"
            value={`${data.adf_mixtures} / ${data.mixture_count}`}
          />
          <Stat label="SPH calcs" value={data.sph_calculations} />
          <Stat
            label="H-factor"
            value={`${data.h_factor} / ${data.mixture_count}`}
          />
        </dl>

        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4 text-[13px] tab-num">
          <DetailRow
            label="Energy range"
            value={
              data.energy_min != null && data.energy_max != null
                ? `${formatEnergy(data.energy_min)} — ${formatEnergy(
                    data.energy_max,
                  )}`
                : "—"
            }
          />
          <DetailRow
            label="Bounds shape"
            value={
              data.energy_bounds_shape
                ? `[${data.energy_bounds_shape.join(", ")}]`
                : "—"
            }
          />
          <DetailRow
            label="ADF faces"
            value={data.adf_faces.length ? data.adf_faces.join(", ") : "—"}
          />
          <DetailRow
            label="Scatter axes"
            value={
              data.scatter_axes.length ? data.scatter_axes.join(", ") : "—"
            }
          />
        </div>

        {data.issues.length > 0 ? (
          <div className="mt-5 text-[13px]">
            <div className="text-amber-300 font-semibold mb-1">
              Issues ({data.issues.length})
            </div>
            <ul className="list-disc pl-5 space-y-0.5 text-[var(--fg-1)]">
              {data.issues.map((issue, index) => (
                <li key={index}>{issue}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <MixtureTable mixtures={data.mixtures} />
    </div>
  );
}

function MixtureTable({ mixtures }: { mixtures: MixtureSummary[] }) {
  if (mixtures.length === 0) {
    return (
      <p className="text-sm text-[var(--fg-3)]">No mixtures in this file.</p>
    );
  }
  return (
    <div className="glass rounded-xl p-1 overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
          <tr className="text-left">
            <Th>Mixture</Th>
            <Th>Fiss</Th>
            <Th align="right">Volume</Th>
            <Th align="right">Required</Th>
            <Th align="right">ADF faces</Th>
            <Th>SPH</Th>
            <Th>Scatter</Th>
          </tr>
        </thead>
        <tbody>
          {mixtures.map((m) => (
            <tr
              key={m.name}
              className="border-t border-[var(--edge)] hover:bg-white/[0.03]"
            >
              <Td>
                <span className="font-mono">{m.name}</span>
              </Td>
              <Td>
                {m.fissionable === null ? (
                  <span className="text-[var(--fg-3)]">—</span>
                ) : m.fissionable ? (
                  <span className="text-emerald-300">✓</span>
                ) : (
                  <span className="text-[var(--fg-3)]">·</span>
                )}
              </Td>
              <Td align="right" mono>
                {m.volume == null ? "—" : m.volume.toFixed(2)}
              </Td>
              <Td align="right" mono>
                {m.required_present}/{m.required_total}
              </Td>
              <Td align="right" mono>
                {m.adf_faces.length}
              </Td>
              <Td>
                {m.sph ? (
                  <span className="text-emerald-300">✓</span>
                ) : (
                  <span className="text-[var(--fg-3)]">·</span>
                )}
              </Td>
              <Td mono>
                {m.scatter_shape
                  ? `[${m.scatter_shape.join(",")}]`
                  : "—"}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold">{value}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-[var(--edge)] pb-2">
      <span className="text-[var(--fg-3)]">{label}</span>
      <span className="font-mono text-right">{value}</span>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`px-3 py-2 ${align === "right" ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  mono = false,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  mono?: boolean;
}) {
  return (
    <td
      className={
        "px-3 py-2 " +
        (align === "right" ? "text-right " : "") +
        (mono ? "font-mono " : "")
      }
    >
      {children}
    </td>
  );
}

function formatEnergy(value: number): string {
  if (value === 0) return "0 eV";
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${(value / 1e6).toPrecision(3)} MeV`;
  if (abs >= 1e3) return `${(value / 1e3).toPrecision(3)} keV`;
  if (abs >= 1) return `${value.toPrecision(3)} eV`;
  return `${value.toExponential(2)} eV`;
}
