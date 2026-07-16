"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ConvertFormat, ConvertPreflightInput } from "@/lib/api";
import {
  convertShowcaseFacts,
  convertShowcaseObjectLabel,
} from "@/lib/convertShowcase";

interface Props {
  format: ConvertFormat;
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
  outputPath: string;
  input: ConvertPreflightInput | null;
  defaultOpen: boolean;
  sphHref?: string;
}

export default function ConvertShowcase({
  format,
  check,
  production,
  requireKnownMesh,
  outputPath,
  input,
  defaultOpen,
  sphHref,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const objectLabel = convertShowcaseObjectLabel(format);
  const facts = convertShowcaseFacts({
    format,
    check,
    production,
    requireKnownMesh,
    input,
  });
  const trimmedOutput = outputPath.trim();

  useEffect(() => {
    setOpen(defaultOpen);
  }, [defaultOpen]);

  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="mb-5 rounded-xl border border-[var(--edge)] bg-white/[0.018] p-4 [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="list-none cursor-pointer">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--accent-2)]">
                What will be written
              </p>
              <span className="rounded border border-[var(--edge)] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] text-[var(--fg-3)]">
                {open ? "expanded" : "details"}
              </span>
            </div>
            <h2 className="mt-1 text-base font-semibold tracking-tight">
              {objectLabel} ASCII output for DONJON
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
              Dry run reads the same inputs without writing. Converter creates
              the selected ASCII object and preserves OpenMC mixture ordering.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {sphHref ? (
              <Link
                href={sphHref}
                className="btn btn-secondary"
                onClick={(event) => event.stopPropagation()}
              >
                Review required SPH handoff
              </Link>
            ) : null}
            <span className="text-[13px] text-[var(--fg-3)]">
              {open ? "Click to collapse" : "Click to expand"}
            </span>
          </div>
        </div>
      </summary>

      <div className="mt-4">
        {trimmedOutput ? (
          <div className="truncate rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-[12px] text-[var(--fg-1)]">
            {trimmedOutput}
          </div>
        ) : null}

        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {facts.map((fact) => (
            <article
              key={fact.id}
              className={"rounded-lg border px-3 py-2 " + factClass(fact.tone)}
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-sm font-semibold tracking-tight">
                  {fact.title}
                </h3>
                <span className="shrink-0 rounded border border-current/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] opacity-85">
                  {fact.badge}
                </span>
              </div>
              <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
                {fact.body}
              </p>
            </article>
          ))}
        </div>
      </div>
    </details>
  );
}

function factClass(tone: "neutral" | "accent" | "pass" | "warn"): string {
  if (tone === "accent") {
    return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-50";
  }
  if (tone === "pass") {
    return "border-emerald-300/20 bg-emerald-300/[0.045] text-emerald-50";
  }
  if (tone === "warn") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-50";
  }
  return "border-[var(--edge)] bg-black/10 text-[var(--fg-0)]";
}
