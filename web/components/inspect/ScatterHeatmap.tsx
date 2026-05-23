"use client";

import { useMemo, useState } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "@/lib/usePlotlyPlot";
import type { ScatterMoment } from "@/lib/api";

export interface ScatterHeatmapProps {
  scatter: ScatterMoment;
  mixtureName: string;
  className?: string;
}

type Scale = "linear" | "log10";

/**
 * Render one scatter moment as a heatmap with a Linear / log10 colour
 * toggle and a direction caption.
 *
 * The matrix follows the canonical ``moment,from,to`` axis order the
 * Python backend produces, so ``z[i][j]`` is the scattering cross
 * section from group ``i+1`` to group ``j+1``. The Y axis is reversed
 * so group 1 (fastest) sits at the top, matching the reactor-physics
 * convention readers expect.
 *
 * Scale handling
 * --------------
 * Linear mode plots the raw values; log10 mode plots ``log10(z)`` and
 * carries the original value through ``customdata`` so the hover label
 * still shows the real cross section. Cells with ``z <= 0`` render as
 * gaps under log10 (Plotly skips ``null`` z entries).
 *
 * Moment selector + finer zero-cell handling land in M2-C.
 */
export default function ScatterHeatmap({
  scatter,
  mixtureName,
  className,
}: ScatterHeatmapProps) {
  const [scale, setScale] = useState<Scale>("linear");
  const trace = useMemo(() => buildTrace(scatter, scale), [scatter, scale]);

  const ref = usePlotlyPlot(
    () => {
      if (!trace) return null;
      return { traces: [trace], layout: buildLayout() };
    },
    [trace, mixtureName, scatter.moment_index, scale],
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
      <div className="flex items-center justify-between gap-3 px-2 pt-1 pb-2 flex-wrap">
        <h3 className="text-sm font-semibold text-[var(--fg-1)]">
          Scatter matrix (P{scatter.moment_index}) —{" "}
          <span className="font-mono">{mixtureName}</span>
        </h3>
        <SegmentedControl scale={scale} onChange={setScale} />
      </div>
      <div ref={ref} className="h-96 w-full" />
      <p className="px-2 pt-3 text-[12px] text-[var(--fg-3)] leading-relaxed">
        Rows are incoming (<code className="font-mono">from</code>) groups;
        columns are outgoing (<code className="font-mono">to</code>) groups.{" "}
        <code className="font-mono">g1</code> is the highest-energy group.{" "}
        {scale === "log10"
          ? "Colour bar shows log₁₀(σ); cells with zero scatter render as gaps."
          : "Colour bar shows σ directly; switch to log₁₀ to see weak couplings off the diagonal."}
      </p>
    </div>
  );
}

function SegmentedControl({
  scale,
  onChange,
}: {
  scale: Scale;
  onChange: (s: Scale) => void;
}) {
  const options: { value: Scale; label: string }[] = [
    { value: "linear", label: "Linear" },
    { value: "log10", label: "log₁₀" },
  ];
  return (
    <div
      className="inline-flex rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] p-0.5 text-[12px] tab-num"
      role="group"
      aria-label="Colour scale"
    >
      {options.map((option) => {
        const active = scale === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            aria-pressed={active}
            className={
              "px-2.5 py-1 rounded transition " +
              (active
                ? "bg-[var(--accent)]/15 text-[var(--fg-0)]"
                : "text-[var(--fg-2)] hover:text-[var(--fg-0)]")
            }
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function buildTrace(scatter: ScatterMoment, scale: Scale): Data | null {
  const values = scatter.values;
  const ngroups = values.length;
  if (ngroups === 0) return null;
  // Reject ragged matrices defensively; ``mgxs_physics_checks`` should
  // never emit one, but a bad fixture or future endpoint could.
  if (values.some((row) => row.length !== ngroups)) return null;
  const labels = Array.from({ length: ngroups }, (_, i) => `g${i + 1}`);

  if (scale === "log10") {
    const logged: (number | null)[][] = values.map((row) =>
      row.map((v) => (v > 0 ? Math.log10(v) : null)),
    );
    return {
      type: "heatmap",
      z: logged,
      x: labels,
      y: labels,
      customdata: values,
      colorscale: "Viridis",
      showscale: true,
      colorbar: {
        thickness: 10,
        outlinewidth: 0,
        tickfont: { color: "#8b90a3", size: 10 },
        title: {
          text: "log₁₀(σ)",
          side: "right",
          font: { color: "#8b90a3", size: 10 },
        },
      },
      hovertemplate:
        "from %{y} → to %{x}<br>" +
        "σ = %{customdata:.4g} (log₁₀ = %{z:.2f})" +
        "<extra></extra>",
    };
  }

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

function buildLayout(): Partial<Layout> {
  return {
    autosize: true,
    margin: { l: 56, r: 16, t: 12, b: 50 },
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
      // Reverse so group 1 sits at the top, matching the
      // reactor-physics scatter-matrix convention.
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

