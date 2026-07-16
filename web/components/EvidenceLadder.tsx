import {
  evidenceStatusLabel,
  type EvidenceStage,
  type EvidenceStageStatus,
} from "@/lib/evidenceLadder";

export default function EvidenceLadder({
  stages,
  title = "Evidence scope",
  compact = false,
}: {
  stages: readonly EvidenceStage[];
  title?: string;
  compact?: boolean;
}) {
  return (
    <section
      aria-label={title}
      className={
        "rounded-xl border border-[var(--edge)] bg-black/15 " +
        (compact ? "mt-3 p-3" : "mt-4 p-4")
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
            {title}
          </p>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
            Each verdict applies only to its named layer. Green never implies a
            downstream physics or reactor acceptance result.
          </p>
        </div>
        <span className="rounded border border-amber-300/20 bg-amber-300/[0.055] px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-amber-100">
          no inferred physics
        </span>
      </div>

      <ol className={"mt-3 grid gap-2 " + (compact ? "md:grid-cols-2 xl:grid-cols-5" : "lg:grid-cols-5")}>
        {stages.map((stage, index) => (
          <li
            key={stage.id}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.02] p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <span className="font-mono text-[9px] text-[var(--fg-3)]">
                  {index + 1}
                </span>
                <h3 className="mt-0.5 text-[11px] font-bold tracking-tight text-[var(--fg-0)]">
                  {stage.label}
                </h3>
              </div>
              <span
                className={
                  "shrink-0 rounded border px-1.5 py-0.5 font-mono text-[8px] font-bold uppercase tracking-[0.08em] " +
                  statusClass(stage.status)
                }
              >
                {evidenceStatusLabel(stage.status)}
              </span>
            </div>
            <p className="mt-2 text-[10px] leading-4 text-[var(--fg-3)]">
              {stage.summary}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function statusClass(status: EvidenceStageStatus): string {
  if (status === "passed") {
    return "border-emerald-300/25 bg-emerald-300/[0.07] text-emerald-100";
  }
  if (status === "failed") {
    return "border-rose-300/25 bg-rose-300/[0.07] text-rose-100";
  }
  if (status === "pending") {
    return "border-cyan-300/25 bg-cyan-300/[0.07] text-cyan-100";
  }
  if (status === "evidence-present") {
    return "border-amber-300/25 bg-amber-300/[0.07] text-amber-100";
  }
  return "border-white/15 bg-white/[0.025] text-[var(--fg-3)]";
}
