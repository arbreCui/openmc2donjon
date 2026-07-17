"use client";

import { useId, useMemo } from "react";
import type { Layout } from "plotly.js-dist-min";
import { usePlotlyPlot } from "../../lib/usePlotlyPlot";
import ChiPlot from "./ChiPlot";
import {
  buildMacroscopicTraces,
  MACROSCOPIC_SERIES,
  validEnergyBounds,
  type CrossSectionUncertainties,
  type PlottableCrossSections,
} from "./groupConstantPlot";

export type {
  CrossSectionUncertainties,
  PlottableCrossSections,
} from "./groupConstantPlot";

export interface CrossSectionPlotProps {
  /**
   * Strictly ascending group boundaries in eV (low → high), with length
   * ``ngroups + 1``. The value arrays remain in reactor-physics order:
   * ``g1`` (highest energy) through ``gG`` (lowest energy).
   */
  energyBounds: number[];
  crossSections: PlottableCrossSections;
  /** Optional one-standard-deviation arrays, in the same g1 → gG order. */
  standardDeviations?: CrossSectionUncertainties | null;
  mixtureName: string;
  /** Explicit material classification from the calculation/mixture attrs. */
  fissionable?: boolean | null;
  className?: string;
}

export interface InvalidGroupConstant {
  field: string;
  group: number;
  value: number;
}

export interface FissionDeclarationConflict {
  declared: boolean;
  fields: string[];
}

export default function CrossSectionPlot({
  energyBounds,
  crossSections,
  standardDeviations,
  mixtureName,
  fissionable,
  className,
}: CrossSectionPlotProps) {
  const headingId = useId();
  const fissionConflict = useMemo(
    () => fissionDeclarationConflict(crossSections, fissionable),
    [crossSections, fissionable],
  );
  const invalidConstants = useMemo(
    () => invalidGroupConstants(crossSections),
    [crossSections],
  );
  const boundsAreValid = useMemo(
    () => validEnergyBounds(energyBounds),
    [energyBounds],
  );
  const traces = useMemo(
    () =>
      buildMacroscopicTraces(
        energyBounds,
        crossSections,
        standardDeviations,
      ),
    [energyBounds, crossSections, standardDeviations],
  );

  const ref = usePlotlyPlot(
    () => {
      if (traces.length === 0 || !boundsAreValid) return null;
      return { traces, layout: buildLayout(energyBounds) };
    },
    [traces, energyBounds, boundsAreValid],
  );

  if (!boundsAreValid) {
    return (
      <div className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]" role="status">
        Cannot plot multigroup constants: <code>energy_bounds</code> must be
        finite, positive, and strictly ascending from low to high energy.
      </div>
    );
  }

  const hasUncertainty = traces.some(
    (trace) => typeof trace.name === "string" && trace.name.includes("±1σ"),
  );
  const uncertaintyLowerArmClipped = MACROSCOPIC_SERIES.some((series) => {
    const values = crossSections[series.key];
    const deviations = standardDeviations?.[series.key];
    return (
      values != null &&
      deviations != null &&
      values.length === energyBounds.length - 1 &&
      deviations.length === values.length &&
      values.some(
        (value, index) =>
          Number.isFinite(value) &&
          value > 0 &&
          Number.isFinite(deviations[index]) &&
          deviations[index] >= value,
      )
    );
  });

  return (
    <div className="space-y-3">
      {fissionConflict ? (
        <div className="rounded-lg border border-rose-300/25 bg-rose-300/[0.06] px-4 py-3 text-[12px] leading-5 text-rose-100">
          <strong className="block">Contradictory fission declaration</strong>
          This calculation is declared{" "}
          <code>fissionable={String(fissionConflict.declared)}</code>, but{" "}
          <span className="font-mono">{fissionConflict.fields.join(", ")}</span>{" "}
          {fissionConflict.declared
            ? "does not contain a nonzero source vector."
            : "contains nonzero raw data."}{" "}
          Inspect keeps showing the raw HDF5 values; Converter rejects this
          contradiction instead of silently erasing or reclassifying it.
        </div>
      ) : null}
      {invalidConstants.length > 0 ? (
        <div className="rounded-lg border border-rose-300/25 bg-rose-300/[0.06] px-4 py-3 text-[12px] leading-5 text-rose-100">
          <strong className="block">Invalid raw group constants</strong>
          {invalidConstants.slice(0, 6).map((item) => (
            <span key={`${item.field}-${item.group}`} className="mr-3 font-mono">
              {item.field} g{item.group}={item.value.toExponential(4)}
            </span>
          ))}
          {invalidConstants.length > 6
            ? ` +${invalidConstants.length - 6} more`
            : ""}
          <span className="mt-1 block text-rose-100/75">
            Non-positive total/transport or negative reaction constants cannot
            be represented honestly on the logarithmic plot and are not
            silently repaired.
          </span>
        </div>
      ) : null}
      <section
        className={className ?? "glass rounded-xl p-3"}
        aria-labelledby={headingId}
      >
        <h3
          id={headingId}
          className="px-2 pt-1 text-sm font-semibold text-[var(--fg-1)]"
        >
          Macroscopic multigroup constants —{" "}
          <span className="font-mono">{mixtureName}</span>
        </h3>
        {traces.length === 0 ? (
          <div className="px-2 py-5 text-sm text-[var(--fg-3)]" role="status">
            No positive macroscopic multigroup constants are available for{" "}
            <span className="font-mono">{mixtureName}</span>.
          </div>
        ) : (
          <div
            ref={ref}
            className="h-80 w-full"
            role="img"
            aria-label={`Macroscopic multigroup constants for ${mixtureName}`}
          />
        )}
        <p className="px-2 pt-2 text-[12px] leading-relaxed text-[var(--fg-3)]">
          Each line is constant between the file&apos;s true energy boundaries;
          transitions occur at those boundaries. <code>g1</code> is the
          highest-energy group. Energy is in eV; macroscopic constants use the
          Converter macroscopic-XS contract (cm⁻¹), but this view has not
          verified a dataset-level unit declaration.
          {hasUncertainty ? " Error bars show one standard deviation (1σ)." : ""}
          {uncertaintyLowerArmClipped
            ? " A 1σ lower arm that reaches zero or below is clipped by the physical logarithmic axis; hover retains the reported σ."
            : ""}
        </p>
      </section>

      {crossSections.chi != null &&
      crossSections.chi.length > 0 &&
      crossSections.chi.some((value) => value !== 0) ? (
        <ChiPlot
          energyBounds={energyBounds}
          values={crossSections.chi}
          standardDeviations={standardDeviations?.chi}
          mixtureName={mixtureName}
        />
      ) : null}
    </div>
  );
}

export function fissionDeclarationConflict(
  crossSections: PlottableCrossSections,
  fissionable: boolean | null | undefined,
): FissionDeclarationConflict | null {
  if (fissionable == null) return null;
  const family = [
    ["fission", crossSections.fission],
    ["nu_fission", crossSections.nu_fission],
    ["chi", crossSections.chi],
  ] as const;
  const fields = family
    .filter(([, values]) =>
      fissionable
        ? values == null || !values.some((value) => value > 0)
        : values != null && values.some((value) => value !== 0),
    )
    .map(([field]) => field);
  return fields.length > 0 ? { declared: fissionable, fields } : null;
}

export function invalidGroupConstants(
  crossSections: PlottableCrossSections,
): InvalidGroupConstant[] {
  const invalid: InvalidGroupConstant[] = [];
  for (const field of ["total", "transport_total"] as const) {
    crossSections[field]?.forEach((value, index) => {
      if (!Number.isFinite(value) || value <= 0) {
        invalid.push({ field, group: index + 1, value });
      }
    });
  }
  for (const field of ["absorption", "fission", "nu_fission", "chi"] as const) {
    crossSections[field]?.forEach((value, index) => {
      if (!Number.isFinite(value) || value < 0) {
        invalid.push({ field, group: index + 1, value });
      }
    });
  }
  return invalid;
}

function buildLayout(energyBounds: readonly number[]): Partial<Layout> {
  return {
    autosize: true,
    margin: { l: 62, r: 16, t: 48, b: 50 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#c8cbd6", size: 11 },
    hovermode: "closest",
    hoverlabel: {
      bgcolor: "rgba(14,16,22,0.96)",
      bordercolor: "rgba(255,255,255,0.16)",
      font: { color: "#f1f2f6", size: 11 },
    },
    showlegend: true,
    legend: { orientation: "h", x: 0, y: 1.02, xanchor: "left", yanchor: "bottom" },
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
      type: "log",
      title: {
        text: "Macroscopic group constant (contract units)",
        font: { color: "#8b90a3", size: 11 },
      },
      gridcolor: "rgba(255,255,255,0.05)",
      zeroline: false,
      color: "#8b90a3",
      exponentformat: "power",
    },
  };
}
