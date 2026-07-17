"use client";

import { useMemo } from "react";
import type { Data, Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "../../lib/usePlotlyPlot";
import type { ScatterMoment } from "../../lib/api";

export type Scale = "linear" | "log10";

export interface ScatterHeatmapProps {
  scatter: ScatterMoment;
  /**
   * Strictly ascending energy-group boundaries in eV. Length must be one
   * greater than the scatter-matrix dimension. The scatter convention keeps
   * g1 as the highest-energy group, so labels are built from the bounds in
   * reverse interval order.
   */
  energyBounds: readonly number[];
  /** Optional 1-sigma uncertainty matrix, with the same shape as ``values``. */
  scatterStdDev?: readonly (readonly number[])[] | null;
  mixtureName: string;
  /** Currently selected moment (== ``scatter.moment_index`` when the parent's
   * fetch has settled; passed through so the selector reflects the requested
   * value even mid-fetch). */
  moment: number;
  scale: Scale;
  /** Allowed moment indices, derived from ``handoff.legendre_order``. */
  availableMoments: readonly number[];
  onMomentChange: (moment: number) => void;
  onScaleChange: (scale: Scale) => void;
  /** When non-null, an ``api.inspectMixture`` request for this moment is
   * in flight. The chart keeps showing the previous moment's data and
   * the header gets a ``loading P{loadingMoment}…`` indicator so the
   * user can tell which moment they're waiting on. */
  loadingMoment?: number | null;
  className?: string;
}

const ZERO_CELL_COLOR = "#2a2d3a";
const INVALID_P0_COLOR = "#ef4444";
const CONSTANT_POSITIVE_P0_COLOR = "#2f7f86";
const SIGNED_DIVERGING_COLORSCALE: Array<[number, string]> = [
  [0, "#2563eb"],
  [0.5, "#f5f5f4"],
  [1, "#dc2626"],
];

/**
 * Controlled heatmap: parent owns ``moment`` / ``scale``. Triggering a
 * moment change refetches in the parent; switching scale is a pure
 * client-side re-render.
 *
 * Scale handling
 * --------------
 * P0 linear/log10 modes use Viridis only for strictly-positive values and
 * render exact zeros as neutral grey. A negative P0 entry is physically
 * invalid and gets a separate red warning cell. P1 and higher moments retain
 * their signed values on a symmetric, zero-centred diverging scale; ordinary
 * log10 is intentionally unavailable for those moments.
 *
 * Hover
 * -----
 * Every cell names both group energy intervals. When supplied, the optional
 * standard-deviation matrix is appended as a 1-sigma uncertainty.
 */
export default function ScatterHeatmap({
  scatter,
  energyBounds,
  scatterStdDev = null,
  mixtureName,
  moment,
  scale,
  availableMoments,
  onMomentChange,
  onScaleChange,
  loadingMoment = null,
  className,
}: ScatterHeatmapProps) {
  const signedMoment = scatter.moment_index > 0;
  const allCoefficientsZero = scatter.values.every((row) =>
    row.every((value) => value === 0),
  );
  const positiveP0Values = signedMoment
    ? []
    : scatter.values.flat().filter((value) => value > 0);
  const constantPositiveP0Log =
    !signedMoment &&
    scale === "log10" &&
    positiveP0Values.length > 0 &&
    positiveP0Values.every((value) => value === positiveP0Values[0]);
  const effectiveScale: Scale = signedMoment ? "linear" : scale;
  const traces = useMemo(
    () =>
      buildScatterTraces(
        scatter,
        energyBounds,
        effectiveScale,
        scatterStdDev,
      ),
    [scatter, energyBounds, effectiveScale, scatterStdDev],
  );
  const statisticalResolution = useMemo(
    () => scatterStatisticalResolution(scatter.values, scatterStdDev),
    [scatter.values, scatterStdDev],
  );

  const ref = usePlotlyPlot(
    () => {
      if (traces.length === 0) return null;
      return { traces, layout: buildScatterLayout() };
    },
    [traces, mixtureName, scatter.moment_index, effectiveScale],
  );

  return (
    <div className={className ?? "glass rounded-xl p-3"}>
      <div className="flex items-center justify-between gap-3 px-2 pt-1 pb-2 flex-wrap">
        <h3 className="text-sm font-semibold text-[var(--fg-1)] flex items-center gap-2 flex-wrap">
          <span>
            Scatter matrix (P{scatter.moment_index}) —{" "}
            <span className="font-mono">{mixtureName}</span>
          </span>
          {loadingMoment != null ? (
            <span
              className="text-[11px] font-normal text-[var(--fg-3)] tab-num"
              aria-live="polite"
            >
              · loading P{loadingMoment}…
            </span>
          ) : null}
        </h3>
        <div className="flex items-center gap-2 flex-wrap">
          {availableMoments.length > 1 ? (
            <MomentSelector
              moments={availableMoments}
              selected={moment}
              onChange={onMomentChange}
            />
          ) : null}
          {signedMoment ? (
            <span
              className="rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-2.5 py-1 text-[12px] text-[var(--fg-2)] tab-num"
              title="P1 and higher Legendre moments can be negative, so an ordinary logarithmic colour scale is not defined."
            >
              Signed linear · zero-centred
            </span>
          ) : (
            <ScaleToggle scale={scale} onChange={onScaleChange} />
          )}
        </div>
      </div>
      {statisticalResolution ? (
        <div className="mx-2 mb-2 rounded-md border border-[var(--edge)] bg-black/15 px-3 py-2 text-[11px] leading-4 text-[var(--fg-2)] tab-num">
          <span className="font-semibold text-[var(--fg-1)]">
            Statistical resolution (3σ):
          </span>{" "}
          {statisticalResolution.cellsWithUncertainty > 0
            ? `${statisticalResolution.resolvedCells}/${statisticalResolution.cellsWithUncertainty} cells with a positive reported σ are individually resolved`
            : "No cells have a positive reported σ"}
          {statisticalResolution.resolvedL2Fraction == null
            ? "."
            : `; the resolved subset carries ${(statisticalResolution.resolvedL2Fraction * 100).toFixed(3)}% of the full matrix's unweighted ΣPℓ².`}
          {statisticalResolution.zeroSigmaNonzeroCells > 0
            ? ` ${statisticalResolution.zeroSigmaNonzeroCells} nonzero coefficient(s) report σ=0 and are not classified by this statistic.`
            : ""}{" "}
          This coefficient-norm diagnostic is not flux- or reaction-rate
          importance and does not include covariance.
        </div>
      ) : null}
      {traces.length === 0 ? (
        <div className="px-2 pb-2 text-sm text-[var(--fg-3)]">
          No scatter matrix available for{" "}
          <span className="font-mono">{mixtureName}</span>.
        </div>
      ) : (
        <div ref={ref} className="h-96 w-full" />
      )}
      <p className="px-2 pt-3 text-[12px] text-[var(--fg-3)] leading-relaxed">
        Rows are incoming (<code className="font-mono">from</code>) groups;
        columns are outgoing (<code className="font-mono">to</code>) groups.{" "}
        <code className="font-mono">g1</code> is the highest-energy group.{" "}
        Converter interprets scatter as macroscopic cross section; this view
        has not verified a dataset-level unit declaration. Hover uncertainty is
        marginal 1σ; covariance is not available. {" "}
        {signedMoment
          ? allCoefficientsZero
            ? `Every reported P${scatter.moment_index} coefficient is exactly zero; the heatmap is neutral and no arbitrary non-zero colour range is invented.`
            : `P${scatter.moment_index} is a signed Legendre moment: negative and positive values use a symmetric, zero-centred diverging scale. log₁₀ is unavailable because it cannot preserve sign.`
          : effectiveScale === "log10"
            ? constantPositiveP0Log
              ? "All positive P0 estimates are equal, so they use one constant colour without an invented numerical colour range; zero estimates remain neutral grey and invalid negative estimates red."
              : "P0 uses log₁₀ colour over strictly positive estimates; zero estimates are neutral grey and invalid negative estimates are red."
            : "P0 uses a linear Viridis scale over positive estimates; zero estimates are neutral grey and invalid negative estimates are red."}
      </p>
    </div>
  );
}

function MomentSelector({
  moments,
  selected,
  onChange,
}: {
  moments: readonly number[];
  selected: number;
  onChange: (m: number) => void;
}) {
  return (
    <div
      className="inline-flex rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] p-0.5 text-[12px] tab-num"
      role="group"
      aria-label="Scatter moment"
    >
      {moments.map((m) => {
        const active = selected === m;
        return (
          <button
            key={m}
            type="button"
            onClick={() => onChange(m)}
            aria-pressed={active}
            className={
              "control-segment px-2.5 py-1 rounded transition " +
              (active
                ? "bg-[var(--accent)]/15 text-[var(--fg-0)]"
                : "text-[var(--fg-2)] hover:text-[var(--fg-0)]")
            }
          >
            P{m}
          </button>
        );
      })}
    </div>
  );
}

function ScaleToggle({
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
              "control-segment px-2.5 py-1 rounded transition " +
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

type ScatterMatrix = readonly (readonly number[])[];

export interface ScatterStatisticalResolution {
  cellsWithUncertainty: number;
  resolvedCells: number;
  resolvedL2Fraction: number | null;
  /** Nonzero means whose explicitly reported sigma is exactly zero. Their
   * interpretation is ambiguous (exact vs unavailable), so the 3-sigma
   * diagnostic reports but does not classify them. */
  zeroSigmaNonzeroCells: number;
}

/** Summarize cellwise 3σ resolution without hiding any measured coefficient. */
export function scatterStatisticalResolution(
  values: ScatterMatrix,
  stdDev: ScatterMatrix | null,
): ScatterStatisticalResolution | null {
  const ngroups = values.length;
  if (
    ngroups === 0 ||
    values.some(
      (row) =>
        row.length !== ngroups || row.some((value) => !Number.isFinite(value)),
    ) ||
    !validStdDev(stdDev, ngroups)
  ) {
    return null;
  }
  let cellsWithUncertainty = 0;
  let resolvedCells = 0;
  let totalL2 = 0;
  let resolvedL2 = 0;
  let zeroSigmaNonzeroCells = 0;
  values.forEach((row, fromIndex) => {
    row.forEach((value, toIndex) => {
      const sigma = stdDev[fromIndex][toIndex];
      const strength = value * value;
      // The denominator describes the complete displayed matrix, not merely
      // the subset that happens to have a positive reported uncertainty.
      totalL2 += strength;
      if (sigma === 0) {
        if (value !== 0) zeroSigmaNonzeroCells += 1;
        return;
      }
      cellsWithUncertainty += 1;
      if (Math.abs(value) >= 3 * sigma) {
        resolvedCells += 1;
        resolvedL2 += strength;
      }
    });
  });
  if (cellsWithUncertainty === 0 && zeroSigmaNonzeroCells === 0) return null;
  return {
    cellsWithUncertainty,
    resolvedCells,
    resolvedL2Fraction: totalL2 > 0 ? resolvedL2 / totalL2 : null,
    zeroSigmaNonzeroCells,
  };
}

export interface ScatterGroupLabel {
  id: string;
  /** Plotly category label (two lines when a valid energy range exists). */
  axis: string;
  /** Plain-text label used in hover content. */
  hover: string;
  range: string | null;
}

/**
 * Map ascending boundaries onto the reactor-physics group convention:
 * g1 spans the final (highest-energy) interval, and gG spans the first.
 */
export function buildScatterGroupLabels(
  energyBounds: readonly number[],
  ngroups: number,
): ScatterGroupLabel[] {
  const validBounds =
    energyBounds.length === ngroups + 1 &&
    energyBounds.every((value) => Number.isFinite(value) && value >= 0) &&
    energyBounds.every(
      (value, index) => index === 0 || value > energyBounds[index - 1],
    );

  return Array.from({ length: ngroups }, (_, index) => {
    const id = `g${index + 1}`;
    if (!validBounds) return { id, axis: id, hover: id, range: null };
    const lowerIndex = ngroups - index - 1;
    const range = formatEnergyRange(
      energyBounds[lowerIndex],
      energyBounds[lowerIndex + 1],
    );
    return {
      id,
      axis: `${id}<br>${range}`,
      hover: `${id} [${range}]`,
      range,
    };
  });
}

export function buildScatterTraces(
  scatter: ScatterMoment,
  energyBounds: readonly number[],
  scale: Scale,
  scatterStdDev: ScatterMatrix | null = null,
): Data[] {
  const values = scatter.values;
  const ngroups = values.length;
  if (ngroups === 0) return [];
  // Reject ragged matrices defensively; ``mgxs_physics_checks`` should
  // never emit one, but a bad fixture or future endpoint could.
  if (
    values.some(
      (row) =>
        row.length !== ngroups || row.some((value) => !Number.isFinite(value)),
    )
  ) {
    return [];
  }
  const labels = buildScatterGroupLabels(energyBounds, ngroups);
  const usableStdDev = validStdDev(scatterStdDev, ngroups)
    ? scatterStdDev
    : null;

  // P1+ data are signed. Enforce linear rendering here as well as in the UI
  // so callers cannot accidentally erase negative values by requesting log10.
  if (scatter.moment_index > 0) {
    return [
      buildSignedTrace(
        values,
        labels,
        scatter.moment_index,
        usableStdDev,
      ),
    ];
  }
  return buildP0Traces(values, labels, scale, usableStdDev);
}

function buildP0Traces(
  values: number[][],
  labels: ScatterGroupLabel[],
  scale: Scale,
  stdDev: ScatterMatrix | null,
): Data[] {
  const hover = buildHoverMatrix(values, labels, 0, stdDev, scale);
  const traces: Data[] = [];
  if (values.some((row) => row.some((value) => value === 0))) {
    traces.push(
      buildConstantCellTrace(
        values,
        labels,
        hover,
        (value) => value === 0,
        ZERO_CELL_COLOR,
      ),
    );
  }
  if (values.some((row) => row.some((value) => value < 0))) {
    traces.push(
      buildConstantCellTrace(
        values,
        labels,
        hover,
        (value) => value < 0,
        INVALID_P0_COLOR,
      ),
    );
  }

  const positives = values.flat().filter((value) => value > 0);
  if (positives.length === 0) return traces;
  if (
    scale === "log10" &&
    positives.every((value) => value === positives[0])
  ) {
    traces.push(
      buildConstantCellTrace(
        values,
        labels,
        hover,
        (value) => value > 0,
        CONSTANT_POSITIVE_P0_COLOR,
      ),
    );
    return traces;
  }
  traces.push(
    scale === "log10"
      ? buildP0LogTrace(values, labels, hover, positives)
      : buildP0LinearTrace(values, labels, hover, positives),
  );
  return traces;
}

function buildConstantCellTrace(
  values: number[][],
  labels: ScatterGroupLabel[],
  hover: string[][],
  include: (value: number) => boolean,
  color: string,
): Data {
  return {
    type: "heatmap",
    z: values.map((row) => row.map((value) => (include(value) ? 0 : null))),
    x: labels.map((label) => label.axis),
    y: labels.map((label) => label.axis),
    customdata: hover,
    colorscale: [
      [0, color],
      [1, color],
    ],
    showscale: false,
    hoverongaps: false,
    hovertemplate: "%{customdata}<extra></extra>",
  };
}

function buildP0LinearTrace(
  values: number[][],
  labels: ScatterGroupLabel[],
  hover: string[][],
  positives: number[],
): Data {
  return {
    type: "heatmap",
    z: values.map((row) => row.map((value) => (value > 0 ? value : null))),
    x: labels.map((label) => label.axis),
    y: labels.map((label) => label.axis),
    customdata: hover,
    colorscale: "Viridis",
    zmin: 0,
    zmax: Math.max(...positives),
    showscale: true,
    hoverongaps: false,
    colorbar: standardColorbar("P0"),
    hovertemplate: "%{customdata}<extra></extra>",
  };
}

function buildP0LogTrace(
  values: number[][],
  labels: ScatterGroupLabel[],
  hover: string[][],
  positives: number[],
): Data {
  const logged = values.map((row) =>
    row.map((value) => (value > 0 ? Math.log10(value) : null)),
  );
  const logMin = Math.log10(Math.min(...positives));
  const logMax = Math.log10(Math.max(...positives));
  const tickvals = integerTicksInRange(logMin, logMax);
  return {
    type: "heatmap",
    z: logged,
    x: labels.map((label) => label.axis),
    y: labels.map((label) => label.axis),
    customdata: hover,
    colorscale: "Viridis",
    zmin: logMin,
    zmax: logMax,
    showscale: true,
    hoverongaps: false,
    colorbar: {
      ...standardColorbar("P0 log₁₀"),
      tickvals,
      ticktext: tickvals.map(formatExponent),
    },
    hovertemplate: "%{customdata}<extra></extra>",
  };
}

function buildSignedTrace(
  values: number[][],
  labels: ScatterGroupLabel[],
  moment: number,
  stdDev: ScatterMatrix | null,
): Data {
  const maxAbs = Math.max(...values.flat().map((value) => Math.abs(value)));
  if (maxAbs === 0) {
    return {
      type: "heatmap",
      z: values,
      x: labels.map((label) => label.axis),
      y: labels.map((label) => label.axis),
      customdata: buildHoverMatrix(values, labels, moment, stdDev, "linear"),
      colorscale: [
        [0, ZERO_CELL_COLOR],
        [1, ZERO_CELL_COLOR],
      ],
      showscale: false,
      hoverongaps: false,
      hovertemplate: "%{customdata}<extra></extra>",
    };
  }
  const trace: Data = {
    type: "heatmap",
    z: values,
    x: labels.map((label) => label.axis),
    y: labels.map((label) => label.axis),
    customdata: buildHoverMatrix(values, labels, moment, stdDev, "linear"),
    colorscale: SIGNED_DIVERGING_COLORSCALE,
    zmid: 0,
    showscale: true,
    hoverongaps: false,
    colorbar: standardColorbar(`P${moment}`),
    hovertemplate: "%{customdata}<extra></extra>",
  };
  // A symmetric range makes equal-magnitude positive and negative moments
  // equally saturated.
  trace.zmin = -maxAbs;
  trace.zmax = maxAbs;
  return trace;
}

function standardColorbar(title: string) {
  return {
    thickness: 10,
    outlinewidth: 0,
    tickfont: { color: "#8b90a3", size: 10 },
    title: {
      text: title,
      side: "right" as const,
      font: { color: "#8b90a3", size: 10 },
    },
  };
}

function buildHoverMatrix(
  values: number[][],
  labels: ScatterGroupLabel[],
  moment: number,
  stdDev: ScatterMatrix | null,
  scale: Scale,
): string[][] {
  return values.map((row, fromIndex) =>
    row.map((value, toIndex) => {
      const uncertainty = stdDev?.[fromIndex]?.[toIndex];
      const uncertaintyText =
        uncertainty != null
          ? ` ± ${formatScatterNumber(uncertainty)} (1σ)`
          : "";
      const logText =
        scale === "log10" && value > 0
          ? `<br>log₁₀ = ${Math.log10(value).toFixed(3)}`
          : "";
      const qualifier =
        moment === 0 && value === 0
          ? " (zero estimate)"
          : moment === 0 && value < 0
            ? " (invalid negative P0)"
            : "";
      return (
        `from ${labels[fromIndex].hover} → to ${labels[toIndex].hover}` +
        `<br>P${moment} scatter = ${formatScatterNumber(value)}` +
        uncertaintyText +
        qualifier +
        logText
      );
    }),
  );
}

function validStdDev(
  stdDev: ScatterMatrix | null,
  ngroups: number,
): stdDev is ScatterMatrix {
  return (
    stdDev != null &&
    stdDev.length === ngroups &&
    stdDev.every(
      (row) =>
        row.length === ngroups &&
        row.every((value) => Number.isFinite(value) && value >= 0),
    )
  );
}

function formatScatterNumber(value: number): string {
  if (value === 0) return "0";
  return value.toExponential(4);
}

function formatEnergyRange(lowerEv: number, upperEv: number): string {
  const { scale, unit } = energyUnit(upperEv);
  return `${formatCompact(lowerEv / scale)}–${formatCompact(upperEv / scale)} ${unit}`;
}

function energyUnit(upperEv: number): { scale: number; unit: string } {
  if (upperEv >= 1e6) return { scale: 1e6, unit: "MeV" };
  if (upperEv >= 1e3) return { scale: 1e3, unit: "keV" };
  if (upperEv > 0 && upperEv < 1e-3) {
    return { scale: 1e-3, unit: "meV" };
  }
  return { scale: 1, unit: "eV" };
}

function formatCompact(value: number): string {
  if (value === 0) return "0";
  const absolute = Math.abs(value);
  if (absolute >= 1e4 || absolute < 1e-3) return value.toExponential(2);
  return Number(value.toPrecision(3)).toString();
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
  if (ticks.length <= 7) return ticks;
  // Thin to at most 7 ticks but ALWAYS keep the first and last so the
  // colour bar's reported range matches the data's. Without this guard
  // a 12-decade range thinned by stride=2 could stop at ``-2`` and lie
  // about the maximum.
  const stride = Math.ceil(ticks.length / 7);
  const thinned = ticks.filter((_, i) => i % stride === 0);
  const last = ticks[ticks.length - 1];
  if (thinned[thinned.length - 1] !== last) {
    thinned.push(last);
  }
  return thinned;
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

export function buildScatterLayout(): Partial<Layout> {
  return {
    autosize: true,
    margin: { l: 92, r: 16, t: 12, b: 72 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#c8cbd6", size: 11 },
    hoverlabel: {
      bgcolor: "rgba(14,16,22,0.96)",
      bordercolor: "rgba(255,255,255,0.16)",
      font: { color: "#f1f2f6", size: 11 },
    },
    xaxis: {
      type: "category",
      title: {
        text: "to group (outgoing)",
        font: { color: "#8b90a3", size: 11 },
      },
      color: "#8b90a3",
      ticks: "outside",
      tickfont: { size: 9 },
      automargin: true,
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
      tickfont: { size: 9 },
      automargin: true,
    },
  };
}
