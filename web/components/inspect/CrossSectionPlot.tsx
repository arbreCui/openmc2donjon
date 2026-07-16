"use client";

import { useMemo } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "@/lib/usePlotlyPlot";
import type { CrossSections } from "@/lib/api";

export interface CrossSectionPlotProps {
  /**
   * Energy group boundaries in eV, descending (high → low). Length
   * ``ngroups + 1``. Pulled from the inspect summary's
   * ``energy_bounds`` field; required for the log-log X axis.
   */
  energyBounds: number[];
  crossSections: CrossSections;
  mixtureName: string;
  className?: string;
}

type Series = {
  key: keyof CrossSections;
  label: string;
  color: string;
};

// The four standard reaction-rate cross sections to overlay on one
// log-log plot. ``chi`` lives on a different physical axis (fission
// spectrum, dimensionless probability) so it gets its own card later
// rather than being mixed in here.
const SERIES: readonly Series[] = [
  { key: "total", label: "σ total", color: "#22d3ee" },
  { key: "absorption", label: "σ absorption", color: "#f97316" },
  { key: "fission", label: "σ fission", color: "#f43f5e" },
  { key: "nu_fission", label: "ν σ fission", color: "#10b981" },
];

export default function CrossSectionPlot({
  energyBounds,
  crossSections,
  mixtureName,
  className,
}: CrossSectionPlotProps) {
  const midpoints = useMemo(
    () => groupMidpoints(energyBounds),
    [energyBounds],
  );

  const traces = useMemo(
    () => buildTraces(midpoints, crossSections),
    [midpoints, crossSections],
  );

  const ref = usePlotlyPlot(
    () => {
      if (traces.length === 0) return null;
      return { traces, layout: buildLayout(mixtureName) };
    },
    [traces, mixtureName],
  );

  if (midpoints.length === 0) {
    return (
      <div className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]">
        Cannot plot: the handoff has no <code>energy_bounds</code>.
      </div>
    );
  }
  if (traces.length === 0) {
    return (
      <div className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]">
        No reaction cross sections to plot for{" "}
        <span className="font-mono">{mixtureName}</span>.
      </div>
    );
  }
  return (
    <div className={className ?? "glass rounded-xl p-3"}>
      <div ref={ref} className="h-80 w-full" />
      <p className="px-2 pt-2 text-[11px] leading-4 text-[var(--fg-3)]">
        Energy is shown in eV. Cross-section units are those recorded by the
        MGXS handoff contract (normally cm⁻¹ for macroscopic data); this file
        does not carry a separate per-dataset unit label.
      </p>
    </div>
  );
}

function groupMidpoints(bounds: number[]): number[] {
  if (bounds.length < 2) return [];
  // Sort ascending for predictable pairing; ``energy_bounds`` arrives
  // descending from the contract.
  const ascending = [...bounds].sort((a, b) => a - b);
  const mids: number[] = [];
  for (let i = 0; i < ascending.length - 1; i++) {
    const lo = ascending[i];
    const hi = ascending[i + 1];
    if (lo <= 0 || hi <= 0) {
      // Cannot take a geometric mean across non-positive energies.
      // Skip the group rather than feed NaN into the log axis.
      continue;
    }
    mids.push(Math.sqrt(lo * hi));
  }
  // Restore the high→low order the cross-section arrays use: group 1
  // is the fastest, group G is the thermal cut-off.
  return mids.reverse();
}

function buildTraces(midpoints: number[], xs: CrossSections): Data[] {
  return SERIES.flatMap((series): Data[] => {
    const values = xs[series.key];
    if (values == null || values.length === 0) return [];
    if (values.length !== midpoints.length) return [];
    // Log Y can't render <= 0. Moderator / guide-tube mixtures very
    // often have fission and nu-fission identically zero, and even
    // legitimate small XS may underflow to 0 from rounded output.
    // Convert non-positive samples to ``null`` so Plotly draws gaps
    // instead of dropping points silently with a console warning; if
    // the entire series is non-positive, omit it from the chart.
    const sanitized = values.map((v) => (v > 0 ? v : null));
    if (sanitized.every((v) => v === null)) return [];
    return [
      {
        x: midpoints,
        y: sanitized,
        type: "scatter",
        mode: "lines+markers",
        connectgaps: false,
        name: series.label,
        line: { color: series.color, width: 2, shape: "hv" },
        marker: { color: series.color, size: 5 },
        hovertemplate:
          `<b>${series.label}</b><br>` +
          "E = %{x:.3e} eV<br>" +
          "σ = %{y:.4g}<extra></extra>",
      },
    ];
  });
}

function buildLayout(mixtureName: string): Partial<Layout> {
  return {
    title: {
      text: `Cross sections — ${mixtureName}`,
      font: { color: "#c8cbd6", size: 13 },
    },
    autosize: true,
    margin: { l: 56, r: 16, t: 36, b: 44 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#c8cbd6", size: 11 },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "rgba(14,16,22,0.96)",
      bordercolor: "rgba(255,255,255,0.16)",
      font: { color: "#f1f2f6", size: 11 },
    },
    showlegend: true,
    xaxis: {
      type: "log",
      title: { text: "Energy (eV)", font: { color: "#8b90a3", size: 11 } },
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
    },
    yaxis: {
      type: "log",
      title: { text: "Cross section (contract units)", font: { color: "#8b90a3", size: 11 } },
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
      exponentformat: "power",
    },
  };
}
