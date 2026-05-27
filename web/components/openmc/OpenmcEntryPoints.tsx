"use client";

import Link from "next/link";
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
    <section className="mb-5 grid gap-3 lg:grid-cols-2">
      {OPENMC_ENTRY_POINTS.map((entry) => (
        <article
          key={entry.id}
          className={
            "rounded-xl border p-4 " +
            (active === entry.id
              ? "border-emerald-300/30 bg-emerald-300/[0.07]"
              : "border-[var(--edge)] bg-black/15")
          }
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
          <p className="mt-3 min-h-[4.25rem] text-sm leading-relaxed text-[var(--fg-2)]">
            {entry.body}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onSelect(entry)}
              className="btn btn-primary"
            >
              {entry.primaryLabel}
            </button>
            <Link href={entry.secondaryHref} className="btn btn-secondary">
              {entry.secondaryLabel}
            </Link>
          </div>
        </article>
      ))}
    </section>
  );
}
