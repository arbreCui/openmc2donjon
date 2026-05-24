import type { SphLoopSummary } from "@/lib/api";
import { formatNumber } from "@/lib/auditStatus";

export default function LoopConfiguration({ data }: { data: SphLoopSummary }) {
  const rows = [
    {
      label: "Convergence enabled",
      value: formatBoolean(data.convergence_enabled),
    },
    {
      label: "Flux-ratio target",
      value: formatNumber(data.flux_ratio_tolerance),
    },
    {
      label: "SPH-change target",
      value: formatNumber(data.sph_change_tolerance),
    },
    {
      label: "Minimum iterations",
      value: data.min_iterations == null ? "—" : String(data.min_iterations),
    },
    {
      label: "Fail on nonconvergence",
      value:
        data.fail_on_nonconvergence == null
          ? "not recorded"
          : formatBoolean(data.fail_on_nonconvergence),
    },
    {
      label: "Stop reason",
      value: data.stop_reason || "—",
    },
  ];

  return (
    <section className="glass rounded-xl p-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Loop configuration
          </h2>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            Convergence targets are numerical stopping conditions. Acceptance
            and production-audit gates decide whether the recorded run is usable.
          </p>
        </div>
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((row) => (
          <div
            key={row.label}
            className="min-w-0 rounded-md border border-[var(--edge)] bg-white/[0.025] p-3"
          >
            <dt className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              {row.label}
            </dt>
            <dd className="mt-1 break-all font-mono text-[var(--fg-1)]">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function formatBoolean(value: boolean): string {
  return value ? "true" : "false";
}
