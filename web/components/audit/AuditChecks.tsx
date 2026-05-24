import type {
  JsonValue,
  SphLoopAcceptance,
  SphLoopAcceptanceCheck,
  SphLoopProductionAudit,
} from "@/lib/api";

export interface AuditChecksProps {
  acceptance: SphLoopAcceptance;
  productionAudit: SphLoopProductionAudit;
}

export default function AuditChecks({
  acceptance,
  productionAudit,
}: AuditChecksProps) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      <ChecklistCard
        title="Acceptance checklist"
        subtitle={acceptanceSubtitle(acceptance)}
        enabled={acceptance.enabled}
        passed={acceptance.passed}
        checks={acceptance.checks}
      />
      <ProductionAuditCard productionAudit={productionAudit} />
    </div>
  );
}

function ChecklistCard({
  title,
  subtitle,
  enabled,
  passed,
  checks,
}: {
  title: string;
  subtitle: string;
  enabled: boolean;
  passed: boolean;
  checks: SphLoopAcceptanceCheck[];
}) {
  const counts = summarizeChecks(checks);
  return (
    <section className="glass rounded-xl p-4 min-w-0">
      <Header
        title={title}
        subtitle={subtitle}
        badge={enabled ? (passed ? "PASS" : "FAIL") : "DISABLED"}
        tone={!enabled ? "neutral" : passed ? "pass" : "fail"}
      />
      <div className="mt-3 text-[12px] text-[var(--fg-3)] tab-num">
        {counts.failed} failed / {counts.total} total
      </div>
      <CheckTable checks={checks} emptyText="No acceptance checks were recorded." />
    </section>
  );
}

function ProductionAuditCard({
  productionAudit,
}: {
  productionAudit: SphLoopProductionAudit;
}) {
  const counts = summarizeChecks(productionAudit.checks);
  const metrics = productionMetrics(productionAudit);
  return (
    <section className="glass rounded-xl p-4 min-w-0">
      <Header
        title="Production audit"
        subtitle={productionAudit.openmc_xs_policy ?? "Workflow and MGXS handoff checks"}
        badge={productionAudit.passed ? "PASS" : "FAIL"}
        tone={productionAudit.passed ? "pass" : "fail"}
      />
      {productionAudit.errors.length > 0 ? (
        <div className="mt-3 rounded-md border border-rose-400/30 bg-rose-400/10 p-3 text-[12px] text-rose-100">
          <div className="font-semibold">
            Errors ({productionAudit.errors.length})
          </div>
          <ul className="mt-1 list-disc pl-4 space-y-0.5">
            {productionAudit.errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        {metrics.map((metric) => (
          <div key={metric.label} className="min-w-0">
            <dt className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              {metric.label}
            </dt>
            <dd className="mt-0.5 tab-num text-[var(--fg-0)] break-all">
              {metric.value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 text-[12px] text-[var(--fg-3)] tab-num">
        {counts.failed} failed / {counts.total} total audit checks
      </div>
      <CheckTable
        checks={productionAudit.checks}
        emptyText="No production-audit checks were recorded."
        compact
      />
    </section>
  );
}

function Header({
  title,
  subtitle,
  badge,
  tone,
}: {
  title: string;
  subtitle: string;
  badge: string;
  tone: "pass" | "fail" | "neutral";
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        <p className="mt-1 text-[12px] text-[var(--fg-3)] break-words">
          {subtitle}
        </p>
      </div>
      <span
        className={
          "shrink-0 rounded-md border px-2.5 py-1 text-[12px] font-semibold tab-num " +
          (tone === "pass"
            ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
            : tone === "fail"
              ? "border-rose-400/40 bg-rose-400/10 text-rose-200"
              : "border-[var(--edge-bright)] bg-white/5 text-[var(--fg-2)]")
        }
      >
        {badge}
      </span>
    </div>
  );
}

function CheckTable({
  checks,
  emptyText,
  compact = false,
}: {
  checks: SphLoopAcceptanceCheck[];
  emptyText: string;
  compact?: boolean;
}) {
  if (checks.length === 0) {
    return <p className="mt-4 text-sm text-[var(--fg-3)]">{emptyText}</p>;
  }
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[680px] border-collapse text-left text-[12px]">
        <thead className="text-[var(--fg-3)]">
          <tr className="border-b border-[var(--edge)]">
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Check</th>
            {!compact ? <th className="py-2 pr-3 font-medium">Actual</th> : null}
            {!compact ? <th className="py-2 pr-3 font-medium">Limit</th> : null}
            <th className="py-2 pr-3 font-medium">Message</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((check, index) => (
            <tr key={`${check.name}-${index}`} className="border-b border-[var(--edge)] last:border-0">
              <td className="py-2 pr-3 align-top">
                <StatusPill passed={check.passed} />
              </td>
              <td className="py-2 pr-3 align-top font-mono text-[var(--fg-1)]">
                {check.name}
              </td>
              {!compact ? (
                <td className="py-2 pr-3 align-top tab-num text-[var(--fg-2)]">
                  {formatValue(check.actual, check.units)}
                </td>
              ) : null}
              {!compact ? (
                <td className="py-2 pr-3 align-top tab-num text-[var(--fg-2)]">
                  {formatValue(check.limit, check.units)}
                </td>
              ) : null}
              <td className="py-2 pr-3 align-top text-[var(--fg-2)]">
                {check.message ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ passed }: { passed: boolean }) {
  return (
    <span
      className={
        "inline-flex min-w-14 justify-center rounded border px-2 py-0.5 font-semibold " +
        (passed
          ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
          : "border-rose-400/30 bg-rose-400/10 text-rose-200")
      }
    >
      {passed ? "pass" : "fail"}
    </span>
  );
}

function acceptanceSubtitle(acceptance: SphLoopAcceptance): string {
  if (!acceptance.enabled) return "Acceptance gates were disabled for this run.";
  const decision = acceptance.decision ? `decision: ${acceptance.decision}` : null;
  const failMode =
    acceptance.fail_on_violation == null
      ? null
      : acceptance.fail_on_violation
        ? "fail-on-violation"
        : "report-only";
  return [decision, failMode].filter(Boolean).join(" · ") || "Acceptance gates";
}

function summarizeChecks(checks: SphLoopAcceptanceCheck[]) {
  return {
    failed: checks.filter((check) => !check.passed).length,
    total: checks.length,
  };
}

function productionMetrics(productionAudit: SphLoopProductionAudit) {
  const flux = productionAudit.flux_map ?? {};
  const reference = productionAudit.reference ?? {};
  const artifactCounts = productionAudit.artifact_counts ?? {};
  return [
    {
      label: "Reference groups",
      value: formatJsonValue(reference.energy_groups),
    },
    {
      label: "Group order",
      value: formatJsonValue(reference.group_order),
    },
    {
      label: "MGXS calcs",
      value: formatJsonValue(flux.mgxs_calculations),
    },
    {
      label: "Mesh ID",
      value: formatJsonValue(flux.mgxs_energy_mesh_id),
    },
    {
      label: "Solves",
      value: formatJsonValue(artifactCounts.solves),
    },
    {
      label: "Postprocesses",
      value: formatJsonValue(artifactCounts.postprocesses),
    },
    {
      label: "Scatter balance",
      value: formatJsonValue(flux.mgxs_scatter_row_balance_max_rel),
    },
    {
      label: "NU warnings",
      value: formatJsonValue(flux.mgxs_nu_ratio_warning_count),
    },
  ];
}

function formatValue(
  value: SphLoopAcceptanceCheck["actual"],
  units: string | null | undefined,
): string {
  if (value == null) return "—";
  const text = typeof value === "number" ? formatNumber(value) : String(value);
  return units ? `${text} ${units}` : text;
}

function formatJsonValue(value: JsonValue | undefined): string {
  if (value == null) return "—";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "string" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  return "object";
}

function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e-3 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}
