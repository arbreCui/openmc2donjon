"use client";

import type { OpenmcEntryPoint, OpenmcEntryPointId } from "@/lib/openmcEntryPoints";
import { OPENMC_ENTRY_POINTS } from "@/lib/openmcEntryPoints";

export default function OpenmcEntryPoints({
  active,
  onSelect,
}: {
  active: OpenmcEntryPointId;
  onSelect: (entry: OpenmcEntryPoint) => void;
}) {
  return (
    <section className="mb-5">
      <div className="mb-3">
        <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
          Choose this page&apos;s job
        </div>
        <p className="mt-1 text-[12px] text-[var(--fg-2)]">
          Pick one route; the form below updates to show only the inputs it needs.
        </p>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
      {OPENMC_ENTRY_POINTS.map((entry) => (
        <button
          type="button"
          key={entry.id}
          onClick={() => onSelect(entry)}
          className={
            "rounded-xl border p-4 text-left transition " +
            (active === entry.id
              ? "border-emerald-300/35 bg-emerald-300/[0.08] shadow-[0_10px_30px_rgba(47,201,133,0.08)]"
              : "border-[var(--edge)] bg-black/15 hover:border-[var(--edge-bright)] hover:bg-white/[0.035]")
          }
          aria-pressed={active === entry.id}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                {entry.eyebrow}
              </div>
              <h2 className="mt-1 text-base font-semibold tracking-tight">
                {entry.title}
              </h2>
            </div>
            {active === entry.id ? (
              <span className="rounded border border-emerald-300/25 bg-emerald-300/[0.08] px-2 py-0.5 text-[11px] uppercase tracking-wider text-emerald-100">
                selected
              </span>
            ) : null}
          </div>
          <p className="mt-3 text-[12px] leading-5 text-[var(--fg-2)]">
            {entry.body}
          </p>
          <div className="mt-3 text-[11px] font-bold text-[var(--accent)]">
            {active === entry.id ? "Selected" : entry.primaryLabel}
          </div>
        </button>
      ))}
      </div>
    </section>
  );
}
