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

const ZERO_CELL_COLOR = "#2a2d3a";

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
 * Linear mode plots the raw values; log10 mode plots ``log10(z)`` on
 * top of a grey background, with the original value carried through
 * ``customdata`` so the hover label still reports the real cross
 * section. Cells where ``z == 0`` (typically the upper triangle in a
 * down-scatter-only matrix) render as explicit grey rather than as
 * transparent gaps; this distinguishes "physical zero" from "missing
 * data" and matches the caption.
 *
 * Moment selector lands in M2-D.
 */
export default function ScatterHeatmap({
  scatter,
  mixtureName,
  className,
}: ScatterHeatmapProps) {
  const [scale, setScale] = useState<Scale>("linear");
  const traces = useMemo(() => buildTraces(scatter, scale), [scatter, scale]);

  const ref = usePlotlyPlot(
    () => {
      if (traces.length === 0) return null;
      return { traces, layout: buildLayout() };
    },
    [traces, mixtureName, scatter.moment_index, scale],
  );

  if (traces.length === 0) {
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
          ? "Colour bar shows σ on a log₁₀ scale; cells with zero scatter are shown in grey."
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

function buildTraces(scatter: ScatterMoment, scale: Scale): Data[] {
  const values = scatter.values;
  const ngroups = values.length;
  if (ngroups === 0) return [];
  // Reject ragged matrices defensively; ``mgxs_physics_checks`` should
  // never emit one, but a bad fixture or future endpoint could.
  if (values.some((row) => row.length !== ngroups)) return [];
  const labels = Array.from({ length: ngroups }, (_, i) => `g${i + 1}`);

  if (scale === "log10") {
    return buildLogTraces(values, labels);
  }
  return [buildLinearTrace(values, labels)];
}

function buildLinearTrace(values: number[][], labels: string[]): Data {
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

function buildLogTraces(values: number[][], labels: string[]): Data[] {
  // Trace 1: a grey heatmap that fills only the zero cells. We mask
  // non-zero cells with null so the log trace above paints over them.
  const greyZ: (number | null)[][] = values.map((row) =>
    row.map((v) => (v === 0 ? 0 : null)),
  );
  const greyTrace: Data = {
    type: "heatmap",
    z: greyZ,
    x: labels,
    y: labels,
    colorscale: [
      [0.0, ZERO_CELL_COLOR],
      [1.0, ZERO_CELL_COLOR],
    ],
    showscale: false,
    hovertemplate:
      "from %{y} → to %{x}<br>σ = 0 (no scatter)<extra></extra>",
  };

  // Trace 2: log10 of positive cells; zeros are null so the grey
  // background shows through.
  const positives = values.flat().filter((v) => v > 0);
  if (positives.length === 0) {
    // Degenerate case: nothing positive to log. Just show grey.
    return [greyTrace];
  }
  const logged: (number | null)[][] = values.map((row) =>
    row.map((v) => (v > 0 ? Math.log10(v) : null)),
  );
  const logMin = Math.log10(Math.min(...positives));
  const logMax = Math.log10(Math.max(...positives));
  const tickvals = integerTicksInRange(logMin, logMax);

  const customdata: string[][] = values.map((row) =>
    row.map((v) =>
      v > 0
        ? `σ = ${v.toExponential(3)} (log₁₀ = ${Math.log10(v).toFixed(2)})`
        : "σ = 0 (no scatter)",
    ),
  );

  const logTrace: Data = {
    type: "heatmap",
    z: logged,
    x: labels,
    y: labels,
    customdata,
    colorscale: "Viridis",
    showscale: true,
    colorbar: {
      thickness: 10,
      outlinewidth: 0,
      tickfont: { color: "#8b90a3", size: 10 },
      tickvals,
      ticktext: tickvals.map(formatExponent),
      title: {
        text: "σ",
        side: "right",
        font: { color: "#8b90a3", size: 10 },
      },
    },
    hovertemplate: "from %{y} → to %{x}<br>%{customdata}<extra></extra>",
  };

  // Order matters: grey first so the log trace renders on top of it;
  // log's null cells let the grey show through.
  return [greyTrace, logTrace];
}

function integerTicksInRange(min: number, max: number): number[] {
  // Bracket the range to the nearest integer log10 marks so each tick
  // is a clean power of ten.
  const lo = Math.floor(min);
  const hi = Math.ceil(max);
  const ticks: number[] = [];
  for (let k = lo; k <= hi; k++) {
    ticks.push(k);
  }
  // If the range spans many decades, thin out so the colorbar isn't
  // crowded; aim for at most 7 visible ticks.
  if (ticks.length <= 7) return ticks;
  const stride = Math.ceil(ticks.length / 7);
  return ticks.filter((_, i) => i % stride === 0);
}

const SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹";

function formatExponent(n: number): string {
  const digits = Math.abs(n)
    .toString()
    .split("")
    .map((c) => SUPERSCRIPT_DIGITS[parseInt(c, 10)])
    .join("");
  const sign = n < 0 ? "⁻" : "";
  return `10${sign}${digits}`;
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
