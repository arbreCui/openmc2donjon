"use client";

import { ConvertPreflightInput, ConvertResponse } from "@/lib/api";

interface SummaryItem {
  label: string;
  value: string;
  tone: "neutral" | "pass" | "warn" | "fail" | "accent";
}

export default function ConversionSummaryStrip({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
}) {
  const items = buildSummaryItems(data, input);
  return (
    <section className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-8">
      {items.map((item) => (
        <div
          key={item.label}
          className={"rounded-md border px-3 py-2 " + itemClass(item.tone)}
        >
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            {item.label}
          </div>
          <div className="mt-1 truncate font-mono text-[13px]" title={item.value}>
            {item.value}
          </div>
        </div>
      ))}
    </section>
  );
}

function buildSummaryItems(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): SummaryItem[] {
  return [
    {
      label: "run",
      value: data.dry_run ? "dry run" : data.converted ? "converted" : "stopped",
      tone: data.dry_run ? "accent" : data.converted ? "pass" : "fail",
    },
    {
      label: "object",
      value: data.format === "macrolib" ? "MACROLIB" : "MULTICOMPO",
      tone: "neutral",
    },
    item("groups", input?.energy_groups),
    item(
      "moments",
      input?.legendre_order == null ? null : input.legendre_order + 1,
    ),
    item("mixtures", input?.mixtures),
    {
      label: "ADF",
      value: adfValue(input),
      tone: input?.adf_mixtures ? "pass" : "neutral",
    },
    {
      label: "SPH",
      value: input?.sph_calculations == null ? "-" : String(input.sph_calculations),
      tone: input?.sph_calculations ? "pass" : "neutral",
    },
    {
      label: "preflight",
      value: data.preflight ? (data.preflight_ok ? "pass" : "fail") : "skipped",
      tone: data.preflight ? (data.preflight_ok ? "pass" : "fail") : "neutral",
    },
  ];
}

function item(label: string, value: number | null | undefined): SummaryItem {
  return {
    label,
    value: value == null ? "-" : String(value),
    tone: "neutral",
  };
}

function adfValue(input: ConvertPreflightInput | null): string {
  if (input?.adf_mixtures == null) return "-";
  const faces = input.adf_faces?.length ?? 0;
  return faces > 0 ? `${input.adf_mixtures} / ${faces} faces` : String(input.adf_mixtures);
}

function itemClass(tone: "neutral" | "pass" | "warn" | "fail" | "accent"): string {
  if (tone === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  if (tone === "warn") return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  if (tone === "fail") return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  if (tone === "accent") return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]";
}
