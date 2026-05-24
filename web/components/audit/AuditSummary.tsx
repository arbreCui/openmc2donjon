import { SphLoopSummary } from "@/lib/api";

/**
 * M6-A headline card. Six stats + a path. Convergence chart,
 * per-iteration audit rows table, and the detailed acceptance /
 * production-audit lists are deliberately deferred to later slices.
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
  return (
    <div className="glass rounded-xl p-5">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
            Path
          </div>
          <div className="font-mono text-sm break-all">{path}</div>
        </div>
        <DecisionBadge decision={data.decision} passed={passed} />
      </div>

      <dl className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-4 tab-num text-sm">
        <Stat
          label="Iterations"
          value={`${data.completed_iterations} / ${data.iterations}`}
        />
        <Stat
          label="Converged"
          value={
            data.convergence_enabled
              ? data.converged ? "yes" : "no"
              : "disabled"
          }
        />
        <Stat label="Stop reason" value={data.stop_reason || "—"} />
        <GateStat
          label="Acceptance"
          enabled={data.acceptance.enabled}
          passed={data.acceptance.passed}
          counts={summarizeChecks(data.acceptance.checks)}
        />
        <GateStat
          label="Production audit"
          enabled
          passed={data.production_audit.passed}
          counts={summarizeChecks(data.production_audit.checks)}
        />
        <Stat label="Version" value={data.package_version} />
      </dl>

      {data.production_audit.errors.length > 0 ? (
        <div className="mt-5 text-[13px]">
          <div className="text-rose-300 font-semibold mb-1">
            Production audit errors ({data.production_audit.errors.length})
          </div>
          <ul className="list-disc pl-5 space-y-0.5 text-[var(--fg-1)]">
            {data.production_audit.errors.map((err, index) => (
              <li key={index}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function isPassDecision(decision: string): boolean {
  return decision === "openmc2donjon_sph_loop_passed";
}

function summarizeChecks(
  checks: { passed: boolean }[],
): { failed: number; total: number } {
  const failed = checks.filter((c) => !c.passed).length;
  return { failed, total: checks.length };
}

function DecisionBadge({
  decision,
  passed,
}: {
  decision: string;
  passed: boolean;
}) {
  return (
    <span
      className={
        "px-3 py-1 rounded-md border text-sm font-semibold tab-num " +
        (passed
          ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
          : "border-rose-400/40 bg-rose-400/10 text-rose-200")
      }
      title={decision}
    >
      {passed ? "PASSED" : "FAILED"}
    </span>
  );
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
