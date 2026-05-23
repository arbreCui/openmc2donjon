"use client";

import { useMemo } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "@/lib/usePlotlyPlot";
import type { ScatterMoment } from "@/lib/api";

export interface ScatterHeatmapProps {
  scatter: ScatterMoment;
  mixtureName: string;
  className?: string;
}

/**
 * Render one scatter moment as a heatmap.
 *
 * The matrix follows the canonical ``moment,from,to`` axis order the
 * Python backend produces, so ``z[i][j]`` is the scattering cross
 * section from group ``i+1`` to group ``j+1``. The Y axis is reversed
 * so group 1 (fastest) sits at the top, matching the reactor-physics
 * convention readers expect.
 *
 * M2-A scope: linear Viridis colourscale, no moment selector, no
 * controls. Moment selector + log colour scale + explicit zero
 * treatment land in M2-B.
 */
export default function ScatterHeatmap({
  scatter,
  mixtureName,
  className,
}: ScatterHeatmapProps) {
  const trace = useMemo(() => buildTrace(scatter), [scatter]);

  const ref = usePlotlyPlot(
    () => {
      if (!trace) return null;
      return { traces: [trace], layout: buildLayout(mixtureName, scatter) };
    },
    [trace, mixtureName, scatter.moment_index],
  );

  if (!trace) {
    return (
      <div className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]">
        No scatter matrix available for{" "}
        <span className="font-mono">{mixtureName}</span>.
      </div>
    );
  }

  return (
    <div className={className ?? "glass rounded-xl p-3"}>
      <div ref={ref} className="h-96 w-full" />
    </div>
  );
}

function buildTrace(scatter: ScatterMoment): Data | null {
  const values = scatter.values;
  const ngroups = values.length;
  if (ngroups === 0) return null;
  // Reject ragged matrices defensively; ``mgxs_physics_checks`` should
  // never emit one, but a bad fixture or future endpoint could.
  if (values.some((row) => row.length !== ngroups)) return null;
  const labels = Array.from({ length: ngroups }, (_, i) => `g${i + 1}`);
  return {
    type: "heatmap",
    z: values,
    x: labels,
    y: labels,
    colorscale: "Viridis",
    showscale: true,
    colorbar: {
      thickness: 10,
      outlinewidth: 0,
      tickfont: { color: "#8b90a3", size: 10 },
    },
    hovertemplate:
      "from %{y} → to %{x}<br>σ = %{z:.4g}<extra></extra>",
  };
}

function buildLayout(
  mixtureName: string,
  scatter: ScatterMoment,
): Partial<Layout> {
  return {
    title: {
      text: `Scatter matrix (P${scatter.moment_index}) — ${mixtureName}`,
      font: { color: "#c8cbd6", size: 13 },
    },
    autosize: true,
    margin: { l: 56, r: 16, t: 36, b: 50 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#c8cbd6", size: 11 },
    xaxis: {
      type: "category",
      title: {
        text: "to group (outgoing)",
        font: { color: "#8b90a3", size: 11 },
      },
      color: "#8b90a3",
      ticks: "outside",
    },
    yaxis: {
      type: "category",
      // Plotly defaults to y growing upward; reverse so group 1
      // sits at the top, matching the reactor-physics scatter matrix
      // convention (fastest at top, thermal at bottom).
      autorange: "reversed",
      title: {
        text: "from group (incoming)",
        font: { color: "#8b90a3", size: 11 },
      },
      color: "#8b90a3",
      ticks: "outside",
    },
  };
}
