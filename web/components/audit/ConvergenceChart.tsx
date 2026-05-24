"use client";

import { useMemo } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "@/lib/usePlotlyPlot";
import type { SphLoopConvergencePoint } from "@/lib/api";

export interface ConvergenceChartProps {
  points: SphLoopConvergencePoint[];
  sphTolerance: number | null;
  fluxTolerance: number | null;
}

const COLORS = {
  sph: "#22d3ee",
  flux: "#10b981",
  clipped: "#f97316",
  converged: "#84cc16",
  notConverged: "#f43f5e",
} as const;

export default function ConvergenceChart({
  points,
  sphTolerance,
  fluxTolerance,
}: ConvergenceChartProps) {
  const sorted = useMemo(
    () => [...points].sort((a, b) => a.iteration - b.iteration),
    [points],
  );
  const displayFloor = useMemo(
    () => convergenceDisplayFloor(sorted, sphTolerance, fluxTolerance),
    [sorted, sphTolerance, fluxTolerance],
  );
  const traces = useMemo(
    () => buildTraces(sorted, displayFloor, sphTolerance, fluxTolerance),
    [sorted, displayFloor, sphTolerance, fluxTolerance],
  );
  const yRange = useMemo(
    () => residualLogRange(sorted, displayFloor, sphTolerance, fluxTolerance),
    [sorted, displayFloor, sphTolerance, fluxTolerance],
  );
  const ref = usePlotlyPlot(
    () => {
      if (traces.length === 0) return null;
      return { traces, layout: buildLayout(yRange) };
    },
    [traces, yRange],
  );

  if (sorted.length === 0) {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]">
        No convergence history is present in this SPH loop summary.
      </section>
    );
  }

  const final = sorted[sorted.length - 1];
  return (
    <section className="glass rounded-xl p-4">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Convergence history
          </h2>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            Lines should move downward; dashed lines are acceptance tolerances.
          </p>
        </div>
        <div className="text-[12px] text-[var(--fg-2)] tab-num">
          final residual{" "}
          <span className="text-[var(--fg-0)]">
            {formatNumber(final.flux_ratio_max_residual)}
          </span>
        </div>
      </div>
      <div ref={ref} className="mt-3 h-80 w-full" />
      <p className="mt-2 text-[12px] text-[var(--fg-3)]">
        Y is the raw residual on a log scale. A drop from 1e-2 to 1e-4
        means the error is 100x smaller. Exact zeros are drawn just below
        tolerance while hover text keeps the raw value.
      </p>
    </section>
  );
}

function buildTraces(
  points: SphLoopConvergencePoint[],
  displayFloor: number,
  sphTolerance: number | null,
  fluxTolerance: number | null,
): Data[] {
  const iterations = points.map((p) => p.iteration);
  const statusColors = points.map((p) =>
    p.converged ? COLORS.converged : COLORS.notConverged,
  );
  const traces: Data[] = [];
  const sph = residualSeries(
    points,
    (p) => p.sph_max_rel_change,
    displayFloor,
  );
  const flux = residualSeries(
    points,
    (p) => p.flux_ratio_max_residual,
    displayFloor,
  );
  const clipped = nullableSeries(points, (p) => p.clipped_fraction);

  if (hasValues(sph)) {
    traces.push({
      x: iterations,
      y: sph,
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      name: "SPH max rel change",
      line: { color: COLORS.sph, width: 2 },
      marker: {
        color: statusColors,
        size: 8,
        line: { color: COLORS.sph, width: 1 },
      },
      hovertemplate:
        "iteration %{x}<br>" +
        "SPH max rel change = %{customdata[0]}<br>" +
        "%{customdata[1]}<extra></extra>",
      customdata: points.map((p) => [
        formatNumber(p.sph_max_rel_change),
        statusLabel(p),
      ]),
    });
  }
  if (hasValues(flux)) {
    traces.push({
      x: iterations,
      y: flux,
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      name: "Flux residual",
      line: { color: COLORS.flux, width: 2 },
      marker: {
        color: statusColors,
        size: 8,
        line: { color: COLORS.flux, width: 1 },
      },
      hovertemplate:
        "iteration %{x}<br>" +
        "flux residual = %{customdata[0]}<br>" +
        "%{customdata[1]}<extra></extra>",
      customdata: points.map((p) => [
        formatNumber(p.flux_ratio_max_residual),
        worstBinLabel(p),
      ]),
    });
  }
  addToleranceTrace(traces, iterations, sphTolerance, "SPH tolerance", COLORS.sph);
  addToleranceTrace(traces, iterations, fluxTolerance, "Flux tolerance", COLORS.flux);
  if (hasPositiveValues(clipped) || points.some((p) => p.clipped_count > 0)) {
    traces.push({
      x: iterations,
      y: clipped,
      yaxis: "y2",
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      name: "Clipped fraction",
      line: { color: COLORS.clipped, width: 2, dash: "dot" },
      marker: { color: COLORS.clipped, size: 6 },
      hovertemplate:
        "iteration %{x}<br>" +
        "clipped fraction = %{y:.4g}<br>" +
        "clipped bins = %{customdata}<extra></extra>",
      customdata: points.map((p) => p.clipped_count),
    });
  }
  return traces;
}

function buildLayout(yRange: [number, number]): Partial<Layout> {
  return {
    autosize: true,
    margin: { l: 58, r: 18, t: 14, b: 44 },
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
      title: { text: "Iteration", font: { color: "#8b90a3", size: 11 } },
      dtick: 1,
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
    },
    yaxis: {
      title: {
        text: "Residual (log scale)",
        font: { color: "#8b90a3", size: 11 },
      },
      type: "log",
      range: yRange,
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
      exponentformat: "power",
    },
    yaxis2: {
      title: {
        text: "Clipped fraction",
        font: { color: "#8b90a3", size: 11 },
      },
      overlaying: "y",
      side: "right",
      rangemode: "tozero",
      gridcolor: "rgba(255,255,255,0)",
      zeroline: false,
      color: "#8b90a3",
    },
  };
}

function residualSeries(
  points: SphLoopConvergencePoint[],
  pick: (point: SphLoopConvergencePoint) => number | null,
  displayFloor: number,
): (number | null)[] {
  return points.map((point) => residualDisplayValue(pick(point), displayFloor));
}

function residualDisplayValue(
  value: number | null,
  displayFloor: number,
): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return value > 0 ? value : displayFloor;
}

function nullableSeries(
  points: SphLoopConvergencePoint[],
  pick: (point: SphLoopConvergencePoint) => number | null,
): (number | null)[] {
  return points.map((point) => finiteOrNull(pick(point)));
}

function finiteOrNull(value: number | null): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

function hasValues(values: readonly (number | null)[]): boolean {
  return values.some((value) => value != null);
}

function hasPositiveValues(values: readonly (number | null)[]): boolean {
  return values.some((value) => value != null && value > 0);
}

function addToleranceTrace(
  traces: Data[],
  iterations: number[],
  tolerance: number | null,
  name: string,
  color: string,
) {
  if (tolerance == null || tolerance <= 0 || iterations.length === 0) return;
  const x0 = Math.min(...iterations);
  const x1 = Math.max(...iterations);
  traces.push({
    x: [x0, x1],
    y: [tolerance, tolerance],
    type: "scatter",
    mode: "lines",
    name,
    line: { color, width: 1, dash: "dash" },
    hovertemplate: `${name} = ${formatNumber(tolerance)}<extra></extra>`,
  });
}

function convergenceDisplayFloor(
  points: SphLoopConvergencePoint[],
  sphTolerance: number | null,
  fluxTolerance: number | null,
): number {
  const positives = [
    sphTolerance,
    fluxTolerance,
    ...points.flatMap((point) => [
      point.sph_max_rel_change,
      point.flux_ratio_max_residual,
    ]),
  ].filter(
    (value): value is number =>
      value != null && Number.isFinite(value) && value > 0,
  );
  if (positives.length === 0) return 1.0e-16;
  return Math.min(...positives) / 10.0;
}

function residualLogRange(
  points: SphLoopConvergencePoint[],
  displayFloor: number,
  sphTolerance: number | null,
  fluxTolerance: number | null,
): [number, number] {
  const values = [
    displayFloor,
    sphTolerance,
    fluxTolerance,
    ...points.flatMap((point) => [
      point.sph_max_rel_change,
      point.flux_ratio_max_residual,
    ]),
  ].filter(
    (value): value is number =>
      value != null && Number.isFinite(value) && value > 0,
  );
  const min = Math.min(...values);
  const max = Math.max(...values);
  return [Math.log10(min) - 0.25, Math.log10(max) + 0.25];
}

function statusLabel(point: SphLoopConvergencePoint): string {
  return point.converged ? "converged" : "not converged";
}

function worstBinLabel(point: SphLoopConvergencePoint): string {
  const [bin] = point.worst_residual_bins;
  if (!bin) return statusLabel(point);
  const mixture = bin.mixture ?? "unknown";
  const group = bin.group == null ? "?" : String(bin.group);
  const residual = formatNumber(bin.residual ?? null);
  return `worst bin ${mixture} g${group}, residual ${residual}`;
}

function formatNumber(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e-3 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}
