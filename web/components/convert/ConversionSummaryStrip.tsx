"use client";

import { ConvertPreflightInput, ConvertResponse } from "@/lib/api";

interface SummaryItem {
  label: string;
  value: string;
  tone: "neutral" | "pass" | "warn";
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
    item("groups", input?.energy_groups),
    item("mixtures", input?.mixtures),
    item("states", input?.state_points),
    item("fissile", input?.fissionable_mixtures),
    {
      label: "ADF",
      value: input?.adf_mixtures == null ? "-" : String(input.adf_mixtures),
      tone: input?.adf_mixtures ? "pass" : "neutral",
    },
    {
      label: "SPH",
      value: input?.sph_calculations == null ? "-" : String(input.sph_calculations),
      tone: input?.sph_calculations ? "pass" : "neutral",
    },
    {
      label: "std_dev",
      value: uncertaintyCoverage(input),
      tone: uncertaintyTone(input),
    },
    {
      label: "output",
      value: data.output_size == null ? (data.dry_run ? "dry-run" : "-") : formatSize(data.output_size),
      tone: data.converted && data.output_exists ? "pass" : "neutral",
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

function uncertaintyCoverage(input: ConvertPreflightInput | null): string {
  const uncertainty = input?.uncertainty;
  if (!uncertainty) return "-";
  if (uncertainty.checked === false) return "skipped";
  const datasets = uncertainty.datasets;
  const expected = uncertainty.expected_datasets;
  if (datasets == null || expected == null) return "reported";
  return `${datasets}/${expected}`;
}

function uncertaintyTone(input: ConvertPreflightInput | null): "neutral" | "pass" | "warn" {
  const uncertainty = input?.uncertainty;
  if (!uncertainty || uncertainty.checked === false) return "neutral";
  if (uncertainty.missing_datasets && uncertainty.missing_datasets > 0) return "warn";
  return "pass";
}

function itemClass(tone: "neutral" | "pass" | "warn"): string {
  if (tone === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  if (tone === "warn") return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
