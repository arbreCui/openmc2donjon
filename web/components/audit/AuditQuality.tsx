import type { SphLoopQuality, SphLoopResidualBin } from "@/lib/api";

export interface AuditQualityProps {
  quality: SphLoopQuality;
}

export default function AuditQuality({ quality }: AuditQualityProps) {
  const finalWorst = quality.final_worst_residual_bin;
  return (
    <section className="glass rounded-xl p-4">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            SPH loop quality
          </h2>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            Final residual quality, clipping, and the worst OpenMC/DONJON
            flux-ratio bin.
          </p>
        </div>
        <ImprovementPill improved={quality.flux_residual_improved} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <Metric
          label="Flux residual"
          value={`${formatNumber(quality.initial_flux_ratio_max_residual)} → ${formatNumber(
            quality.final_flux_ratio_max_residual,
          )}`}
          detail={`ratio ${formatNumber(quality.final_to_initial_flux_residual_ratio)}`}
        />
        <Metric
          label="Final SPH range"
          value={formatRange(quality.final_sph_minimum, quality.final_sph_maximum)}
          detail="min / max"
        />
        <Metric
          label="Final clipped"
          value={formatCountFraction(
            quality.final_clipped_count,
            quality.final_clipped_fraction,
          )}
          detail="count / fraction"
        />
        <Metric
          label="Max clipped"
          value={formatCountFraction(
            quality.maximum_clipped_count,
            quality.maximum_clipped_fraction,
          )}
          detail={
            quality.clipping_observed === true
              ? "clipping occurred"
              : quality.clipping_observed === false
                ? "no clipping"
                : "unknown"
          }
        />
      </dl>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <WorstBinCard title="Final worst bin" bin={finalWorst} />
        <WorstBinsTable bins={quality.final_worst_residual_bins} />
      </div>

      {quality.final_clipped_bins.length > 0 ? (
        <div className="mt-3 rounded-md border border-amber-400/30 bg-amber-400/10 p-3">
          <div className="text-[12px] font-semibold text-amber-200">
            Final clipped bins ({quality.final_clipped_bins.length})
          </div>
          <ul className="mt-1 space-y-1 text-[12px] text-[var(--fg-1)]">
            {quality.final_clipped_bins.slice(0, 6).map((bin, index) => (
              <li key={`${bin.mixture ?? "bin"}-${bin.group ?? "g"}-${index}`}>
                {formatBin(bin)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--edge)] bg-white/[0.025] p-3">
      <dt className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </dt>
      <dd className="mt-1 break-all text-lg font-semibold tab-num">{value}</dd>
      <dd className="mt-0.5 text-[11px] text-[var(--fg-3)] tab-num">
        {detail}
      </dd>
    </div>
  );
}

function ImprovementPill({ improved }: { improved: boolean | null }) {
  if (improved == null) {
    return (
      <span className="rounded-md border border-[var(--edge-bright)] bg-white/5 px-2.5 py-1 text-[12px] font-semibold text-[var(--fg-2)]">
        UNKNOWN
      </span>
    );
  }
  return (
    <span
      className={
        "rounded-md border px-2.5 py-1 text-[12px] font-semibold " +
        (improved
          ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
          : "border-rose-400/40 bg-rose-400/10 text-rose-200")
      }
    >
      {improved ? "IMPROVED" : "NOT IMPROVED"}
    </span>
  );
}

function WorstBinCard({
  title,
  bin,
}: {
  title: string;
  bin: SphLoopResidualBin | null;
}) {
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/10 p-3">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {title}
      </div>
      {bin == null ? (
        <p className="mt-2 text-sm text-[var(--fg-3)]">
          No worst-bin diagnostic was recorded.
        </p>
      ) : (
        <dl className="mt-2 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1 text-[12px]">
          <KeyValue label="bin" value={formatBinLabel(bin)} />
          <KeyValue label="residual" value={formatNumber(bin.residual ?? null)} />
          <KeyValue label="raw update" value={formatNumber(bin.raw_update ?? null)} />
          <KeyValue label="SPH" value={formatNumber(bin.sph ?? null)} />
          <KeyValue label="reference flux" value={formatNumber(bin.reference_flux ?? null)} />
          <KeyValue label="low-order flux" value={formatNumber(bin.low_order_flux ?? null)} />
        </dl>
      )}
    </div>
  );
}

function WorstBinsTable({ bins }: { bins: SphLoopResidualBin[] }) {
  if (bins.length === 0) {
    return (
      <div className="rounded-md border border-[var(--edge)] bg-black/10 p-3 text-sm text-[var(--fg-3)]">
        No final worst-bin list was recorded.
      </div>
    );
  }
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex items-baseline justify-between gap-4">
        <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
          Final worst bins
        </div>
        <div className="text-[11px] text-[var(--fg-3)] tab-num">
          top {Math.min(4, bins.length)} / {bins.length}
        </div>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[500px] border-collapse text-left text-[12px]">
          <thead className="text-[var(--fg-3)]">
            <tr className="border-b border-[var(--edge)]">
              <th className="py-1.5 pr-3 font-medium">Bin</th>
              <th className="py-1.5 pr-3 font-medium">Residual</th>
              <th className="py-1.5 pr-3 font-medium">Raw update</th>
              <th className="py-1.5 pr-3 font-medium">SPH</th>
            </tr>
          </thead>
          <tbody>
            {bins.slice(0, 4).map((bin, index) => (
              <tr
                key={`${bin.mixture ?? "bin"}-${bin.group ?? "g"}-${index}`}
                className="border-b border-[var(--edge)] last:border-0"
              >
                <td className="py-1.5 pr-3 text-[var(--fg-1)]">
                  {formatBinLabel(bin)}
                </td>
                <td className="py-1.5 pr-3 tab-num text-[var(--fg-2)]">
                  {formatNumber(bin.residual ?? null)}
                </td>
                <td className="py-1.5 pr-3 tab-num text-[var(--fg-2)]">
                  {formatNumber(bin.raw_update ?? null)}
                </td>
                <td className="py-1.5 pr-3 tab-num text-[var(--fg-2)]">
                  {formatNumber(bin.sph ?? null)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="contents">
      <dt className="text-[var(--fg-3)]">{label}</dt>
      <dd className="min-w-0 break-all font-mono text-[var(--fg-1)]">{value}</dd>
    </div>
  );
}

function formatBin(bin: SphLoopResidualBin): string {
  return `${formatBinLabel(bin)} residual=${formatNumber(
    bin.residual ?? null,
  )} raw=${formatNumber(bin.raw_update ?? null)} sph=${formatNumber(
    bin.sph ?? null,
  )}`;
}

function formatBinLabel(bin: SphLoopResidualBin): string {
  const mixture = bin.mixture ?? "unknown";
  const group = bin.group == null ? "?" : String(bin.group);
  return `${mixture} g${group}`;
}

function formatRange(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  return `${formatNumber(min)} / ${formatNumber(max)}`;
}

function formatCountFraction(
  count: number | null,
  fraction: number | null,
): string {
  return `${count == null ? "—" : String(count)} / ${formatNumber(fraction)}`;
}

function formatNumber(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e-3 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}
