"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import {
  OpenmcSphDemoPreset,
  openmcSphFluxExportHref,
} from "@/lib/openmcSphDemo";

export default function OpenmcSphQuickFillCard({
  preset,
  mode,
  onApply,
}: {
  preset: OpenmcSphDemoPreset;
  mode: "mock" | "live";
  onApply: () => void;
}) {
  return (
    <section
      className={
        "mb-5 rounded-xl border p-4 " +
        (mode === "mock"
          ? "border-amber-300/25 bg-amber-300/[0.055]"
          : "border-emerald-300/25 bg-emerald-300/[0.055]")
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            {mode === "mock" ? "mock minicase" : "live minicase"}
          </div>
          <h2 className="mt-1 text-sm font-semibold tracking-tight">
            {preset.label}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {preset.description}
          </p>
        </div>
        <button type="button" onClick={onApply} className="btn btn-primary">
          Fill SPH planner
        </button>
      </div>

      {mode === "live" ? (
        <div className="mt-3 rounded-md border border-[var(--edge)] bg-black/20 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                prepare files first
              </div>
              <p className="mt-1 text-[12px] text-[var(--fg-2)]">
                Run the smoke once, then use the generated paths below.
              </p>
            </div>
            <CopyCliButton value={preset.command} compact />
          </div>
          <pre className="mt-2 overflow-x-auto rounded border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
            {preset.command}
          </pre>
        </div>
      ) : null}

      <div className="mt-4 grid gap-2 md:grid-cols-4">
        <QuickLink
          label={mode === "mock" ? "CE flux export" : "CE flux file"}
          href={fluxHref(preset, "ce", mode)}
          path={preset.ceFlux}
        />
        <QuickLink
          label={mode === "mock" ? "MG flux export" : "MG flux file"}
          href={fluxHref(preset, "mg", mode)}
          path={preset.mgFlux}
        />
        <QuickLink
          label="Corrected HDF5"
          href={`/inspect?path=${encodeURIComponent(preset.augmentedH5)}`}
          path={preset.augmentedH5}
        />
        <QuickLink
          label="Physics summary"
          href={`/openmc?workflow=two-step&equivalence=sph&summary=${encodeURIComponent(
            preset.physicsSummary,
          )}`}
          path={preset.physicsSummary}
        />
      </div>
    </section>
  );
}

function fluxHref(
  preset: OpenmcSphDemoPreset,
  side: "ce" | "mg",
  mode: "mock" | "live",
): string {
  if (mode === "mock") return openmcSphFluxExportHref(preset, side);
  const path = side === "ce" ? preset.ceFlux : preset.mgFlux;
  return `/inspect?path=${encodeURIComponent(path)}`;
}

function QuickLink({
  label,
  href,
  path,
}: {
  label: string;
  href: string;
  path: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-md border border-[var(--edge)] bg-black/15 p-3 transition hover:border-[var(--edge-bright)] hover:bg-white/[0.04]"
    >
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-2 truncate font-mono text-[11px] text-[var(--fg-1)]" title={path}>
        {path}
      </div>
    </Link>
  );
}
