"use client";

import { useId, useMemo } from "react";
import type { Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "../../lib/usePlotlyPlot";
import {
  buildChiTraces,
  validEnergyBounds,
} from "./groupConstantPlot";

export interface ChiPlotProps {
  energyBounds: number[];
  /** Dimensionless group fractions, ordered g1 (high energy) → gG (low). */
  values: number[];
  /** Optional one-standard-deviation array in the same group order. */
  standardDeviations?: number[] | null;
  mixtureName: string;
  className?: string;
}

export default function ChiPlot({
  energyBounds,
  values,
  standardDeviations,
  mixtureName,
  className,
}: ChiPlotProps) {
  const headingId = useId();
  const traces = useMemo(
    () => buildChiTraces(energyBounds, values, standardDeviations),
    [energyBounds, values, standardDeviations],
  );
  const normalization = useMemo(
    () => values.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0),
    [values],
  );
  const boundsAreValid = validEnergyBounds(energyBounds);
  const ref = usePlotlyPlot(
    () => {
      if (!boundsAreValid || traces.length === 0) return null;
      return {
        traces,
        layout: buildChiLayout(energyBounds, values, standardDeviations),
      };
    },
    [boundsAreValid, traces, energyBounds, values, standardDeviations],
  );

  if (!boundsAreValid || traces.length === 0) return null;

  return (
    <section
      className={className ?? "glass rounded-xl p-3"}
      aria-labelledby={headingId}
    >
      <h3
        id={headingId}
        className="px-2 pt-1 text-sm font-semibold text-[var(--fg-1)]"
      >
        Fission spectrum χ — <span className="font-mono">{mixtureName}</span>
      </h3>
      <div
        ref={ref}
        className="h-64 w-full"
        role="img"
        aria-label={`Dimensionless fission spectrum for ${mixtureName}`}
      />
      <p className="px-2 pt-2 text-[12px] leading-relaxed text-[var(--fg-3)]">
        χ<sub>g</sub> is a dimensionless groupwise fission-spectrum fraction,
        so it is shown separately from macroscopic constants. Values follow
        the file&apos;s true energy boundaries; Σχ<sub>g</sub> ={" "}
        <span className="tab-num">{normalization.toPrecision(6)}</span>.
        {traces.length > 1
          ? " Error bars show one standard deviation (1σ). The χ axis begins at zero, so any symmetric lower 1σ arm that extends below zero is clipped at the physical plotting boundary."
          : ""}
      </p>
    </section>
  );
}

function buildChiLayout(
  energyBounds: readonly number[],
  values: readonly number[],
  standardDeviations?: readonly number[] | null,
): Partial<Layout> {
  const upperValues = values.map((value, index) => {
    const error = standardDeviations?.[index];
    return value + (error != null && Number.isFinite(error) && error >= 0 ? error : 0);
  });
  const maximum = Math.max(0, ...upperValues.filter(Number.isFinite));
  return {
    autosize: true,
    margin: { l: 62, r: 16, t: 14, b: 50 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#c8cbd6", size: 11 },
    hovermode: "closest",
    hoverlabel: {
      bgcolor: "rgba(14,16,22,0.96)",
      bordercolor: "rgba(255,255,255,0.16)",
      font: { color: "#f1f2f6", size: 11 },
    },
    showlegend: false,
    xaxis: {
      type: "log",
      range: [
        Math.log10(energyBounds[0]),
        Math.log10(energyBounds[energyBounds.length - 1]),
      ],
      title: { text: "Energy E (eV)", font: { color: "#8b90a3", size: 11 } },
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
    },
    yaxis: {
      type: "linear",
      range: [0, maximum > 0 ? maximum * 1.08 : 1],
      title: { text: "χg (dimensionless)", font: { color: "#8b90a3", size: 11 } },
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: true,
      zerolinecolor: "rgba(255,255,255,0.16)",
      color: "#8b90a3",
    },
  };
}
