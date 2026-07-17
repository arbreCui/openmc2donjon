"use client";

import { formatEnergy } from "./formatEnergy";

export interface GroupVectorSeries {
  key: string;
  label: string;
  description: string;
  units: string;
  values: number[] | null | undefined;
  standardDeviations?: number[] | null;
}

export interface GroupVectorRow {
  group: number;
  lower: number | null;
  upper: number | null;
  value: number;
  standardDeviation: number | null;
  relativePercent: number | null;
}

export default function GroupVectorTable({
  energyBounds,
  series,
}: {
  energyBounds: readonly number[];
  series: readonly GroupVectorSeries[];
}) {
  const available = series.flatMap((item) => {
    const rows = buildGroupVectorRows(
      energyBounds,
      item.values,
      item.standardDeviations,
    );
    return rows.length > 0 ? [{ item, rows }] : [];
  });
  if (available.length === 0) return null;

  return (
    <section
      className="glass rounded-xl p-4"
      aria-labelledby="additional-group-data-heading"
    >
      <div className="mb-3">
        <h3
          id="additional-group-data-heading"
          className="text-sm font-semibold text-[var(--fg-1)]"
        >
          Additional group data
        </h3>
        <p className="mt-1 text-[12px] leading-relaxed text-[var(--fg-3)]">
          Groupwise values are tabulated rather than overlaid on the
          macroscopic-cross-section axis. This keeps quantities with different
          dimensions physically separate; an unavailable or invalid energy
          mesh is shown as an em dash without hiding the raw group values.
        </p>
      </div>

      <div className="space-y-2">
        {available.map(({ item, rows }) => {
          const uncertaintyRows = rows.filter(
            (row) => row.standardDeviation != null,
          ).length;
          return (
            <details
              key={item.key}
              className="rounded-lg border border-[var(--edge)] bg-black/10 px-3 py-2"
            >
              <summary className="cursor-pointer list-none">
                <span className="flex flex-wrap items-baseline justify-between gap-2">
                  <span>
                    <span className="text-sm font-medium text-[var(--fg-1)]">
                      {item.label}
                    </span>{" "}
                    <span className="text-[11px] text-[var(--fg-3)]">
                      · {item.units}
                    </span>
                  </span>
                  <span className="text-[11px] tab-num text-[var(--fg-3)]">
                    {rows.length} groups
                    {uncertaintyRows > 0
                      ? ` · uncertainty ${uncertaintyRows}/${rows.length}`
                      : " · no uncertainty dataset"}
                  </span>
                </span>
                <span className="mt-1 block text-[12px] text-[var(--fg-3)]">
                  {item.description}
                </span>
              </summary>

              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[620px] text-left text-[12px] tab-num">
                  <thead className="text-[10px] uppercase tracking-wider text-[var(--fg-3)]">
                    <tr>
                      <th className="pb-2 pr-4 font-medium">Group</th>
                      <th className="pb-2 pr-4 font-medium">Energy interval</th>
                      <th className="pb-2 pr-4 font-medium">Mean</th>
                      <th className="pb-2 pr-4 font-medium">Std. dev.</th>
                      <th className="pb-2 font-medium">Relative</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--edge)] text-[var(--fg-1)]">
                    {rows.map((row) => (
                      <tr key={row.group}>
                        <td className="py-1.5 pr-4 font-mono">g{row.group}</td>
                        <td className="py-1.5 pr-4 font-mono text-[var(--fg-2)]">
                          {row.lower == null || row.upper == null
                            ? "—"
                            : `${formatEnergy(row.upper)} → ${formatEnergy(row.lower)}`}
                        </td>
                        <td className="py-1.5 pr-4 font-mono">
                          {formatValue(row.value)}
                        </td>
                        <td className="py-1.5 pr-4 font-mono">
                          {row.standardDeviation == null
                            ? "—"
                            : formatValue(row.standardDeviation)}
                        </td>
                        <td className="py-1.5 font-mono">
                          {row.relativePercent == null
                            ? "—"
                            : `${row.relativePercent.toFixed(2)}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}

export function buildGroupVectorRows(
  energyBounds: readonly number[],
  values: readonly number[] | null | undefined,
  standardDeviations?: readonly number[] | null,
): GroupVectorRow[] {
  if (values == null || values.length === 0) return [];
  const boundsAreValid =
    energyBounds.length === values.length + 1 &&
    energyBounds.every((value) => Number.isFinite(value) && value > 0) &&
    energyBounds.every(
      (value, index) => index === 0 || value > energyBounds[index - 1],
    );
  const uncertainty =
    standardDeviations != null && standardDeviations.length === values.length
      ? standardDeviations
      : null;
  const groups = values.length;
  return values.map((value, index) => {
    const lower = boundsAreValid ? energyBounds[groups - index - 1] : null;
    const upper = boundsAreValid ? energyBounds[groups - index] : null;
    const sigma = uncertainty?.[index];
    const standardDeviation =
      sigma != null && Number.isFinite(sigma) && sigma >= 0 ? sigma : null;
    return {
      group: index + 1,
      lower,
      upper,
      value,
      standardDeviation,
      relativePercent:
        standardDeviation == null || value === 0
          ? null
          : (standardDeviation / Math.abs(value)) * 100,
    };
  });
}

function formatValue(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 1.0e4 || magnitude < 1.0e-3) {
    return value.toExponential(5);
  }
  return value.toPrecision(6);
}
