"use client";

import type { OpenmcWorkflowArtifact, OpenmcWorkflowPlan } from "@/lib/api";

interface PipelineStage {
  id: string;
  eyebrow: string;
  title: string;
  status: string;
  detail: string;
  path?: string;
  tone: "pass" | "warn" | "neutral";
}

export default function OpenmcWorkflowSummary({
  plan,
}: {
  plan: OpenmcWorkflowPlan;
}) {
  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <SummaryTile label="workflow" value={plan.workflow_label} tone="pass" />
        <SummaryTile label="equivalence" value={equivalenceLabel(plan.equivalence)} />
        <SummaryTile label="artifacts" value={String(plan.artifacts.length)} />
        <SummaryTile label="commands" value={String(plan.commands.length)} />
      </section>

      <section className="glass rounded-xl p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight">
              Workflow pipeline
            </h2>
            <p className="mt-1 text-sm text-[var(--fg-2)]">
              Planned production path from OpenMC reference data to the DONJON handoff.
            </p>
          </div>
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            DONJON ASCII
          </span>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {pipelineStages(plan).map((stage) => (
            <article
              key={stage.id}
              className={"rounded-lg border p-4 " + stageClass(stage.tone)}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
                    {stage.eyebrow}
                  </div>
                  <h3 className="mt-1 text-sm font-semibold tracking-tight">
                    {stage.title}
                  </h3>
                </div>
                <span
                  className={
                    "rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                    badgeClass(stage.tone)
                  }
                >
                  {stage.status}
                </span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-[var(--fg-2)]">
                {stage.detail}
              </p>
              {stage.path ? (
                <div
                  className="mt-3 truncate rounded border border-[var(--edge)] bg-black/20 px-2 py-1 font-mono text-[12px] text-[var(--fg-1)]"
                  title={stage.path}
                >
                  {stage.path}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </div>
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

function pipelineStages(plan: OpenmcWorkflowPlan): PipelineStage[] {
  const hdf5 = firstArtifact(plan.artifacts, "hdf5");
  const ascii = firstArtifact(plan.artifacts, "ascii");
  const augmented = augmentedArtifact(plan.artifacts);
  return [
    {
      id: "openmc",
      eyebrow: "OpenMC reference",
      title: plan.workflow === "one-step" ? "Recipe + statepoint" : "Export recipe",
      status: plan.workflow === "one-step" ? "managed" : "export",
      detail:
        plan.workflow === "one-step"
          ? "The one-step command exports, checks, converts, and bundles the handoff in one managed run."
          : "The first command exports the MGXS HDF5 contract, leaving conversion as an explicit second step.",
      tone: "pass",
    },
    {
      id: "hdf5",
      eyebrow: "Intermediate handoff",
      title: augmented ? "Augmented MGXS HDF5" : "MGXS HDF5 contract",
      status: augmented ? "equivalence" : "handoff",
      detail: augmented
        ? `${equivalenceLabel(plan.equivalence)} factors are injected before conversion.`
        : "This HDF5 is the converter-facing contract that can be inspected or archived.",
      path: augmented?.path ?? hdf5?.path,
      tone: augmented ? "warn" : "pass",
    },
    {
      id: "ascii",
      eyebrow: "DONJON artifact",
      title: ascii?.label ?? "DONJON ASCII output",
      status: "output",
      detail:
        plan.workflow === "two-step"
          ? "The final command converts the selected HDF5 handoff to the deterministic ASCII library."
          : "The managed command writes the deterministic ASCII library after export and checks.",
      path: ascii?.path,
      tone: "pass",
    },
  ];
}

function firstArtifact(
  artifacts: OpenmcWorkflowArtifact[],
  kind: string,
): OpenmcWorkflowArtifact | undefined {
  return artifacts.find((artifact) => artifact.kind === kind);
}

function augmentedArtifact(
  artifacts: OpenmcWorkflowArtifact[],
): OpenmcWorkflowArtifact | undefined {
  return artifacts.find((artifact) => artifact.label.toLowerCase().includes("augmented"));
}

function equivalenceLabel(value: OpenmcWorkflowPlan["equivalence"]): string {
  if (value === "flux-ratio-adf") return "flux-ratio ADF";
  if (value === "adf") return "ADF/DF";
  if (value === "sph") return "SPH";
  return "direct";
}

function stageClass(tone: "pass" | "warn" | "neutral"): string {
  if (tone === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06]";
  if (tone === "warn") return "border-amber-400/25 bg-amber-400/[0.06]";
  return "border-[var(--edge)] bg-white/[0.02]";
}

function badgeClass(tone: "pass" | "warn" | "neutral"): string {
  if (tone === "pass") return "border-emerald-400/30 text-emerald-300";
  if (tone === "warn") return "border-amber-400/30 text-amber-300";
  return "border-[var(--edge-bright)] text-[var(--fg-2)]";
}
