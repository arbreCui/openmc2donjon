"use client";

import Link from "next/link";
import type { OpenmcSphDemoPreset } from "@/lib/openmcSphDemo";
import {
  openmcSphBundleHref,
  openmcSphConvertHref,
  openmcSphEvidenceHref,
} from "@/lib/openmcSphDemo";

export default function OpenmcSphMainlineCard({
  preset,
  mode,
  onReview,
}: {
  preset: OpenmcSphDemoPreset;
  mode: "mock" | "live";
  onReview: () => void;
}) {
  return (
    <section className="mb-5 rounded-xl border border-emerald-300/25 bg-emerald-300/[0.045] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-300">
            recommended demo path
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            OpenMC-SPH evidence → converter → DONJON handoff
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Use the {mode === "mock" ? "bundled mock" : "live production"}{" "}
            two-region minicase to show the full route. First review the
            OpenMC CE/MG SPH evidence, then convert the corrected HDF5 into the
            validated MACROLIB NSPH handoff.
          </p>
        </div>
        <span className="rounded border border-emerald-300/30 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-emerald-300">
          {mode}
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <MainlineButton
          label="01"
          title="Review SPH evidence"
          body="Load physics_summary.json and check flux uncertainty, SPH range, reaction-rate preservation, and DONJON NSPH consume smoke."
          href={openmcSphEvidenceHref(preset)}
          onClick={onReview}
          primary
        />
        <MainlineButton
          label="02"
          title="Send corrected MGXS to Convert"
          body="Open /convert with mgxs_with_openmc_sph.h5, MACROLIB output, production checks, and ASCII writer already selected."
          href={openmcSphConvertHref(preset)}
        />
        <MainlineButton
          label="03"
          title="Preview / bundle DONJON handoff"
          body="After conversion, collect the corrected HDF5, MACROLIB ASCII, summaries, and logs as a delivery bundle."
          href={openmcSphBundleHref(preset)}
        />
      </div>
    </section>
  );
}

function MainlineButton({
  label,
  title,
  body,
  href,
  onClick,
  primary = false,
}: {
  label: string;
  title: string;
  body: string;
  href: string;
  onClick?: () => void;
  primary?: boolean;
}) {
  const className =
    "block rounded-lg border p-3 text-left transition " +
    (primary
      ? "border-emerald-300/30 bg-emerald-300/[0.075] hover:bg-emerald-300/[0.11]"
      : "border-[var(--edge)] bg-black/15 hover:border-[var(--edge-bright)] hover:bg-white/[0.04]");
  return (
    <Link href={href} className={className} onClick={onClick}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-[var(--fg-3)]">{label}</span>
        <span className="text-[11px] text-[var(--accent-2)]">Open</span>
      </div>
      <h3 className="mt-2 text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
    </Link>
  );
}

