"use client";

import type { OpenmcWorkflowPlan } from "@/lib/api";

export default function OpenmcWorkflowSummary({
  plan,
}: {
  plan: OpenmcWorkflowPlan;
}) {
  return (
    <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
      <SummaryTile label="workflow" value={plan.workflow_label} tone="pass" />
      <SummaryTile label="equivalence" value={equivalenceLabel(plan.equivalence)} />
      <SummaryTile label="artifacts" value={String(plan.artifacts.length)} />
      <SummaryTile label="commands" value={String(plan.commands.length)} />
    </section>
  );
}

function SummaryTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "pass" | "neutral";
}) {
  return (
    <div
      className={
        "rounded-md border px-3 py-2 " +
        (tone === "pass"
          ? "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100"
          : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]")
      }
    >
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-[13px]" title={value}>
        {value}
      </div>
    </div>
  );
}

function equivalenceLabel(value: OpenmcWorkflowPlan["equivalence"]): string {
  if (value === "flux-ratio-adf") return "flux-ratio ADF";
  if (value === "adf") return "ADF/DF";
  if (value === "sph") return "SPH";
  return "direct";
}
