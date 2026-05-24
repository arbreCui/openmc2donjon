import { SphLoopSummary } from "@/lib/api";
import type { AuditTone } from "@/lib/auditStatus";
import {
  convergenceStatus,
  gateStatus,
  isPassDecision,
  shortDecision,
  shouldShowAcceptedUnconverged,
  summarizeChecks,
} from "@/lib/auditStatus";

/**
 * M6-A headline card. Six stats + a path. Convergence chart and the
 * detailed acceptance / production-audit lists live in sibling
 * components so this card stays a quick top-line read.
 *
 * The decision string is the canonical authority here - acceptance
 * and production_audit are inputs to it, but the loop has the final
 * say (e.g., it may pass acceptance but bail for a non-acceptance
 * reason).
 */
export default function AuditSummary({
  data,
  path,
}: {
  data: SphLoopSummary;
  path: string;
}) {
  const passed = isPassDecision(data.decision);
  const convergence = convergenceStatus(data);
  const acceptance = gateStatus(
    data.acceptance.enabled,
    data.acceptance.passed,
    summarizeChecks(data.acceptance.checks),
  );
  const showAcceptedUnconverged = shouldShowAcceptedUnconverged(data);
  return (
    <div className="glass rounded-xl p-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
            Path
          </div>
          <div className="font-mono text-sm break-all">{path}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <StatusTile
          label="Decision"
          value={shortDecision(data.decision)}
          tone={passed ? "pass" : "fail"}
          detail={data.decision}
        />
        <StatusTile
          label="Acceptance"
          value={acceptance.value}
          tone={acceptance.tone}
          detail={acceptance.detail}
        />
        <StatusTile
          label="Convergence"
          value={convergence.value}
          tone={convergence.tone}
          detail={convergence.detail}
        />
      </div>

      {showAcceptedUnconverged ? (
        <div className="mt-4 rounded-md border border-amber-400/30 bg-amber-400/10 p-3 text-[12px] text-amber-100">
          Accepted by production gates; SPH convergence target was not reached.
        </div>
      ) : null}

      <dl className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-4 tab-num text-sm">
        <Stat
          label="Iterations"
          value={`${data.completed_iterations} / ${data.iterations}`}
        />
        <Stat label="Stop reason" value={data.stop_reason || "—"} />
        <GateStat
          label="Production audit"
          enabled
          passed={data.production_audit.passed}
          counts={summarizeChecks(data.production_audit.checks)}
        />
        <Stat label="Version" value={data.package_version} />
      </dl>
    </div>
  );
}

function StatusTile({
  label,
  value,
  tone,
  detail,
}: {
  label: string;
  value: string;
  tone: AuditTone;
  detail: string;
}) {
  return (
    <div className={`rounded-md border p-3 ${toneClasses(tone)}`}>
      <div className="text-[11px] uppercase tracking-wider opacity-75">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold tab-num">{value}</div>
      <div className="mt-0.5 text-[11px] opacity-75 break-all tab-num">
        {detail}
      </div>
    </div>
  );
}

function toneClasses(tone: AuditTone): string {
  if (tone === "pass") return "border-emerald-400/40 bg-emerald-400/10 text-emerald-200";
  if (tone === "fail") return "border-rose-400/40 bg-rose-400/10 text-rose-200";
  if (tone === "warn") return "border-amber-400/40 bg-amber-400/10 text-amber-200";
  return "border-[var(--edge-bright)] bg-white/5 text-[var(--fg-2)]";
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold break-all">{value}</div>
    </div>
  );
}

function GateStat({
  label,
  enabled,
  passed,
  counts,
}: {
  label: string;
  enabled: boolean;
  passed: boolean;
  counts: { failed: number; total: number };
}) {
  if (!enabled) {
    return <Stat label={label} value="disabled" />;
  }
  const tone = passed
    ? "text-emerald-300"
    : counts.failed > 0
      ? "text-rose-300"
      : "text-amber-300";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-semibold ${tone}`}>
        {passed ? "pass" : "fail"}
      </div>
      <div className="text-[11px] text-[var(--fg-3)] tab-num">
        {counts.failed} / {counts.total} failed
      </div>
    </div>
  );
}
