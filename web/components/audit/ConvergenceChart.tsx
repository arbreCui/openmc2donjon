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
  const plot = useMemo(
    () => buildPlot(sorted, sphTolerance, fluxTolerance),
    [sorted, sphTolerance, fluxTolerance],
  );
  const ref = usePlotlyPlot(
    () => {
      if (plot.traces.length === 0) return null;
      return { traces: plot.traces, layout: plot.layout };
    },
    [plot],
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
            Raw SPH-loop diagnostics. The upper panel is the maximum
            OpenMC/DONJON flux-ratio residual; the lower panel is the maximum
            SPH update size.
          </p>
        </div>
        <div className="text-[12px] text-[var(--fg-2)] tab-num">
          final flux{" "}
          <span className="text-[var(--fg-0)]">
            {formatNumber(final.flux_ratio_max_residual)}
          </span>
          <span className="mx-2 text-[var(--fg-3)]">/</span>
          final SPH update{" "}
          <span className="text-[var(--fg-0)]">
            {formatNumber(final.sph_max_rel_change)}
          </span>
        </div>
      </div>
      <div ref={ref} className="mt-3 h-[430px] w-full" />
      <p className="mt-2 text-[12px] text-[var(--fg-3)]">
        Values are raw dimensionless residuals from the SPH summary, not
        normalized or percent-scaled. Flux residual is max |low-order flux /
        OpenMC reference flux - 1|. SPH update is max
        |NSPH(new) / NSPH(old) - 1|. Downward movement is good; a flat or rising
        curve means the SPH loop is not reducing that diagnostic. Dashed lines,
        when visible, are configured convergence targets rather than acceptance
        gates.
      </p>
      {plot.offScaleNotes.length > 0 ? (
        <p className="mt-1 text-[12px] text-[var(--fg-3)] tab-num">
          Off-scale configured convergence target: {plot.offScaleNotes.join("; ")}.
        </p>
      ) : null}
    </section>
  );
}

function buildPlot(
  points: SphLoopConvergencePoint[],
  sphTolerance: number | null,
  fluxTolerance: number | null,
): { traces: Data[]; layout: Partial<Layout>; offScaleNotes: string[] } {
  const iterations = points.map((point) => point.iteration);
  const statusColors = points.map((point) =>
    point.converged ? COLORS.converged : COLORS.notConverged,
  );
  const flux = finiteSeries(points.map((point) => point.flux_ratio_max_residual));
  const sph = finiteSeries(points.map((point) => point.sph_max_rel_change));
  const clipped = finiteSeries(points.map((point) => point.clipped_fraction));
  const fluxRange = valueRange(flux, fluxTolerance);
  const sphRange = valueRange(sph, sphTolerance, clipped);
  const traces: Data[] = [];
  const offScaleNotes: string[] = [];

  if (hasValues(flux)) {
    traces.push({
      x: iterations,
      y: flux,
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      name: "Flux residual",
      xaxis: "x",
      yaxis: "y",
      line: { color: COLORS.flux, width: 2 },
      marker: {
        color: statusColors,
        size: 8,
        line: { color: COLORS.flux, width: 1 },
      },
      customdata: points.map((point) => [
        formatNumber(point.flux_ratio_max_residual),
        worstBinLabel(point),
      ]),
      hovertemplate:
        "iteration %{x}<br>" +
        "flux residual = %{customdata[0]}<br>" +
        "%{customdata[1]}<extra></extra>",
    });
  }
  addToleranceTrace(
    traces,
    offScaleNotes,
    iterations,
    fluxTolerance,
    fluxRange,
    "Flux target",
    COLORS.flux,
    "x",
    "y",
  );

  if (hasValues(sph)) {
    traces.push({
      x: iterations,
      y: sph,
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      name: "SPH update",
      xaxis: "x2",
      yaxis: "y2",
      line: { color: COLORS.sph, width: 2 },
      marker: {
        color: statusColors,
        size: 8,
        line: { color: COLORS.sph, width: 1 },
      },
      customdata: points.map((point) => [
        formatNumber(point.sph_max_rel_change),
        statusLabel(point),
      ]),
      hovertemplate:
        "iteration %{x}<br>" +
        "SPH update = %{customdata[0]}<br>" +
        "%{customdata[1]}<extra></extra>",
    });
  }
  addToleranceTrace(
    traces,
    offScaleNotes,
    iterations,
    sphTolerance,
    sphRange,
    "SPH target",
    COLORS.sph,
    "x2",
    "y2",
  );

  if (hasPositiveValues(clipped) || points.some((point) => point.clipped_count > 0)) {
    traces.push({
      x: iterations,
      y: clipped,
      type: "scatter",
      mode: "lines+markers",
      connectgaps: false,
      name: "Clipped bins",
      xaxis: "x2",
      yaxis: "y2",
      line: { color: COLORS.clipped, width: 2, dash: "dot" },
      marker: { color: COLORS.clipped, size: 6 },
      hovertemplate:
        "iteration %{x}<br>" +
        "clipped bins = %{customdata}<br>" +
        "clipped fraction = %{y:.4g}<extra></extra>",
      customdata: points.map((point) => point.clipped_count),
    });
  }

  return {
    traces,
    layout: buildLayout(fluxRange, sphRange),
    offScaleNotes,
  };
}

function buildLayout(
  fluxRange: [number, number],
  sphRange: [number, number],
): Partial<Layout> {
  return {
    autosize: true,
    margin: { l: 62, r: 20, t: 26, b: 48 },
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
    legend: {
      orientation: "h",
      x: 0,
      y: 1.08,
      bgcolor: "rgba(0,0,0,0)",
    },
    xaxis: {
      domain: [0, 1],
      anchor: "y",
      dtick: 1,
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
      showticklabels: false,
    },
    xaxis2: {
      title: { text: "Iteration", font: { color: "#8b90a3", size: 11 } },
      domain: [0, 1],
      anchor: "y2",
      dtick: 1,
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
    },
    yaxis: {
      title: {
        text: "Flux residual",
        font: { color: "#8b90a3", size: 11 },
      },
      domain: [0.5, 1],
      range: fluxRange,
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
    },
    yaxis2: {
      title: {
        text: "SPH update",
        font: { color: "#8b90a3", size: 11 },
      },
      domain: [0, 0.36],
      range: sphRange,
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
    },
  };
}

function finiteSeries(values: readonly (number | null)[]): (number | null)[] {
  return values.map((value) => {
    if (value == null || !Number.isFinite(value)) return null;
    return value;
  });
}

function valueRange(
  primary: readonly (number | null)[],
  tolerance: number | null,
  secondary: readonly (number | null)[] = [],
): [number, number] {
  const values = [...primary, ...secondary]
    .filter((value): value is number => value != null && Number.isFinite(value))
    .map((value) => Math.abs(value));
  if (tolerance != null && tolerance > 0 && shouldIncludeTolerance(values, tolerance)) {
    values.push(tolerance);
  }
  const max = values.length === 0 ? 1 : Math.max(...values);
  return [0, niceUpperBound(max)];
}

function shouldIncludeTolerance(values: readonly number[], tolerance: number): boolean {
  if (values.length === 0) return true;
  const max = Math.max(...values);
  return tolerance >= max / 20.0 && tolerance <= max * 1.2;
}

function niceUpperBound(value: number): number {
  const exponent = Math.floor(Math.log10(value));
  const base = 10 ** exponent;
  const scaled = value / base;
  const nice =
    scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return nice * base;
}

function addToleranceTrace(
  traces: Data[],
  offScaleNotes: string[],
  iterations: number[],
  tolerance: number | null,
  yRange: [number, number],
  name: string,
  color: string,
  xaxis: string,
  yaxis: string,
) {
  if (tolerance == null || tolerance <= 0 || iterations.length === 0) return;
  if (tolerance < yRange[0] || tolerance > yRange[1]) {
    offScaleNotes.push(`${name} ${formatNumber(tolerance)} is outside the visible range`);
    return;
  }
  traces.push({
    x: [Math.min(...iterations), Math.max(...iterations)],
    y: [tolerance, tolerance],
    type: "scatter",
    mode: "lines",
    name,
    xaxis,
    yaxis,
    line: { color, width: 1, dash: "dash" },
    hovertemplate: `${name} = ${formatNumber(tolerance)}<extra></extra>`,
  });
}

function hasValues(values: readonly (number | null)[]): boolean {
  return values.some((value) => value != null);
}

function hasPositiveValues(values: readonly (number | null)[]): boolean {
  return values.some((value) => value != null && value > 0);
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
  if (abs >= 1.0e-2 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}
