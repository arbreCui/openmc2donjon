"use client";

import { useState } from "react";
import { ApiError, OpenmcSphPhysicsSummary, api } from "@/lib/api";
import {
  formatScatterTreatment,
  formatPhysicsNumber,
  summaryStatus,
  topSphDeviationRows,
} from "@/lib/openmcSphSummary";

type SummaryState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: OpenmcSphPhysicsSummary }
  | { kind: "error"; message: string; status?: number };

export default function OpenmcSphPhysicsSummaryCard({
  path,
  onPathChange,
  onBrowse,
}: {
  path: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
}) {
  const [state, setState] = useState<SummaryState>({ kind: "idle" });

  async function load() {
    const trimmed = path.trim();
    if (!trimmed) {
      setState({
        kind: "error",
        message: "Choose a physics_summary.json file first.",
      });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await api.openmcSphSummary(trimmed);
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  return (
    <section className="mt-4 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.04] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-300">
            OpenMC-side SPH physics summary
          </div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            Review CE/MG flux agreement and exported NSPH factors
          </h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            Load the `physics_summary.json` written by the CE/MG 33g minicase.
            It summarizes OpenMC CE reference flux, OpenMC MG flux, SPH
            factors, and the corrected DONJON handoff.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-2 lg:grid-cols-[1fr_auto_auto]">
        <input
          value={path}
          onChange={(event) => onPathChange(event.target.value)}
          className="w-full min-w-0 rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-[12px] text-[var(--fg-0)]"
          placeholder="/path/to/handoff/physics_summary.json"
        />
        <button type="button" className="btn btn-secondary" onClick={onBrowse}>
          Browse
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={load}
          disabled={state.kind === "loading"}
        >
          {state.kind === "loading" ? "Loading…" : "Load summary"}
        </button>
      </div>

      <div className="mt-4">
        <SummaryBody state={state} />
      </div>
    </section>
  );
}

function SummaryBody({ state }: { state: SummaryState }) {
  if (state.kind === "idle") {
    return (
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3 text-[12px] text-[var(--fg-2)]">
        After running the CE/MG 33g workflow, load the summary to confirm
        `NSPH` is present and inspect the SPH factor range.
      </div>
    );
  }
  if (state.kind === "loading") {
    return (
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3 text-[12px] text-[var(--fg-2)]">
        Reading physics summary…
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="rounded-md border border-rose-400/25 bg-rose-400/[0.06] p-3">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Load failed"}
        </div>
        <div className="mt-1 text-[12px] text-[var(--fg-1)]">{state.message}</div>
      </div>
    );
  }

  const summary = state.data;
  const status = summaryStatus(summary);
  const rows = topSphDeviationRows(summary);
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {summary.route}
            </div>
            <div className="mt-1 text-sm font-semibold tracking-tight">
              {summary.mixture_count} mixtures · {summary.energy_groups} groups ·{" "}
              {formatScatterTreatment(summary)}
            </div>
          </div>
          <span
            className={
              "rounded border px-2 py-1 text-[10px] uppercase tracking-[0.14em] " +
              (status.tone === "pass"
                ? "border-emerald-300/30 text-emerald-300"
                : "border-amber-300/30 text-amber-300")
            }
          >
            {status.label}
          </span>
        </div>
        <p className="mt-2 text-[12px] text-[var(--fg-2)]">{status.detail}</p>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        <Stat label="SPH range" value={`${formatPhysicsNumber(summary.sph.minimum)} .. ${formatPhysicsNumber(summary.sph.maximum)}`} />
        <Stat label="max |SPH-1|" value={formatPhysicsNumber(summary.sph.max_abs_delta_from_unity)} />
        <Stat label="CE flux σ/μ max" value={formatPhysicsNumber(summary.flux_uncertainty.ce_max_relative_std_dev)} />
        <Stat label="MG flux σ/μ max" value={formatPhysicsNumber(summary.flux_uncertainty.mg_max_relative_std_dev)} />
      </div>

      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
        <div className="mb-2 text-[11px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
          largest SPH corrections
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          {rows.map((row) => (
            <div key={row.mixture} className="rounded border border-[var(--edge)] bg-white/[0.02] p-2">
              <div className="font-mono text-[12px] text-[var(--fg-1)]">
                {row.mixture}
              </div>
              <div className="mt-1 text-[11px] text-[var(--fg-2)]">
                range {formatPhysicsNumber(row.sph_min)} .. {formatPhysicsNumber(row.sph_max)}
              </div>
              <div className="text-[11px] text-[var(--fg-3)]">
                max |SPH-1| = {formatPhysicsNumber(row.max_abs_sph_minus_1)}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3 text-[12px] text-[var(--fg-2)]">
        SPH is carried as DONJON `NSPH` equivalence factors. The report says
        `applied_to_xs = {String(summary.sph.applied_to_xs)}`, so the macro
        cross sections were not silently multiplied in the HDF5.
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/15 p-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm text-[var(--fg-0)]">{value}</div>
    </div>
  );
}

function toErrorState(err: unknown): SummaryState {
  if (err instanceof ApiError) {
    return {
      kind: "error",
      message: err.detail ?? err.message,
      status: err.status,
    };
  }
  if (err instanceof Error) return { kind: "error", message: err.message };
  return { kind: "error", message: "Unknown error" };
}
