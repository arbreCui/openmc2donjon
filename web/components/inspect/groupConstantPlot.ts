import type { Data } from "plotly.js-dist-min";
import type { CrossSections } from "../../lib/api";

export type MacroscopicConstantKey =
  | "total"
  | "transport_total"
  | "absorption"
  | "fission"
  | "nu_fission";

export type PlottableCrossSections = CrossSections;

export type CrossSectionUncertainties = Partial<
  Record<MacroscopicConstantKey | "chi", number[] | null>
>;

type Series = {
  key: MacroscopicConstantKey;
  label: string;
  longLabel: string;
  color: string;
};

export const MACROSCOPIC_SERIES: readonly Series[] = [
  { key: "total", label: "Σt", longLabel: "total", color: "#22d3ee" },
  {
    key: "transport_total",
    label: "Σtr",
    longLabel: "transport total",
    color: "#a78bfa",
  },
  {
    key: "absorption",
    label: "Σa",
    longLabel: "absorption",
    color: "#f97316",
  },
  {
    key: "fission",
    label: "Σf",
    longLabel: "fission",
    color: "#f43f5e",
  },
  {
    key: "nu_fission",
    label: "νΣf",
    longLabel: "nu-fission",
    color: "#10b981",
  },
];

export type GroupStepCoordinates = {
  x: number[];
  y: number[];
  groupLabels: string[];
  intervalLabels: string[];
};

/**
 * Map g1 → gG values onto an ascending energy axis and explicitly duplicate
 * each interval endpoint. Adjacent intervals therefore meet with a vertical
 * transition at the real group boundary.
 */
export function buildGroupStepCoordinates(
  energyBounds: readonly number[],
  values: readonly number[],
): GroupStepCoordinates | null {
  if (!validEnergyBounds(energyBounds)) return null;
  const groupCount = energyBounds.length - 1;
  if (
    values.length !== groupCount ||
    values.some((value) => !Number.isFinite(value))
  ) {
    return null;
  }

  const x: number[] = [];
  const y: number[] = [];
  const groupLabels: string[] = [];
  const intervalLabels: string[] = [];

  for (let lowIndex = 0; lowIndex < groupCount; lowIndex += 1) {
    const valueIndex = groupCount - 1 - lowIndex;
    const groupLabel = `g${valueIndex + 1}`;
    const low = energyBounds[lowIndex];
    const high = energyBounds[lowIndex + 1];
    const intervalLabel = `${formatEnergy(low)} ≤ E < ${formatEnergy(high)} eV`;

    x.push(low, high);
    y.push(values[valueIndex], values[valueIndex]);
    groupLabels.push(groupLabel, groupLabel);
    intervalLabels.push(intervalLabel, intervalLabel);
  }

  return { x, y, groupLabels, intervalLabels };
}

export type GroupUncertaintyPoints = {
  x: number[];
  y: number[];
  error: number[];
  groupLabels: string[];
  intervalLabels: string[];
};

/** Build one uncertainty marker per group at its logarithmic energy centre. */
export function buildGroupUncertaintyPoints(
  energyBounds: readonly number[],
  values: readonly number[],
  standardDeviations: readonly number[],
  requirePositiveValue = true,
): GroupUncertaintyPoints | null {
  if (!validEnergyBounds(energyBounds)) return null;
  const groupCount = energyBounds.length - 1;
  if (
    values.length !== groupCount ||
    standardDeviations.length !== groupCount
  ) {
    return null;
  }

  const points: GroupUncertaintyPoints = {
    x: [],
    y: [],
    error: [],
    groupLabels: [],
    intervalLabels: [],
  };

  for (let valueIndex = 0; valueIndex < groupCount; valueIndex += 1) {
    const value = values[valueIndex];
    const error = standardDeviations[valueIndex];
    if (
      !Number.isFinite(value) ||
      !Number.isFinite(error) ||
      error < 0 ||
      (requirePositiveValue ? value <= 0 : value < 0)
    ) {
      continue;
    }
    const lowIndex = groupCount - 1 - valueIndex;
    const low = energyBounds[lowIndex];
    const high = energyBounds[lowIndex + 1];
    points.x.push(Math.sqrt(low * high));
    points.y.push(value);
    points.error.push(error);
    points.groupLabels.push(`g${valueIndex + 1}`);
    points.intervalLabels.push(
      `${formatEnergy(low)} ≤ E < ${formatEnergy(high)} eV`,
    );
  }

  return points.x.length > 0 ? points : null;
}

export function validEnergyBounds(bounds: readonly number[]): boolean {
  if (bounds.length < 2) return false;
  return bounds.every(
    (bound, index) =>
      Number.isFinite(bound) &&
      bound > 0 &&
      (index === 0 || bound > bounds[index - 1]),
  );
}

export function buildMacroscopicTraces(
  energyBounds: readonly number[],
  crossSections: PlottableCrossSections,
  standardDeviations?: CrossSectionUncertainties | null,
): Data[] {
  return MACROSCOPIC_SERIES.flatMap((series): Data[] => {
    const values = crossSections[series.key];
    if (values == null || values.length === 0) return [];
    const coordinates = buildGroupStepCoordinates(energyBounds, values);
    if (coordinates == null) return [];

    // The logarithmic ordinate cannot represent non-positive constants. Keep
    // those intervals as gaps instead of inventing an arbitrary positive floor.
    const plottedY = coordinates.y.map((value) => (value > 0 ? value : null));
    if (plottedY.every((value) => value == null)) return [];

    const traces: Data[] = [
      {
        x: coordinates.x,
        y: plottedY,
        type: "scatter",
        mode: "lines",
        connectgaps: false,
        name: `${series.label} (${series.longLabel})`,
        legendgroup: series.key,
        line: { color: series.color, width: 2 },
        text: coordinates.y.map(
          (value, index) =>
            `<b>${series.label} · ${coordinates.groupLabels[index]}</b><br>` +
            `${coordinates.intervalLabels[index]}<br>` +
            `${series.label} = ${formatValue(value)}`,
        ),
        hovertemplate: "%{text}<extra></extra>",
      },
    ];

    const deviations = standardDeviations?.[series.key];
    if (deviations != null) {
      const uncertainty = buildGroupUncertaintyPoints(
        energyBounds,
        values,
        deviations,
      );
      if (uncertainty != null) {
        traces.push({
          x: uncertainty.x,
          y: uncertainty.y,
          type: "scatter",
          mode: "markers",
          name: `${series.label} ±1σ`,
          legendgroup: series.key,
          showlegend: false,
          marker: {
            color: series.color,
            size: 4,
            line: { color: "rgba(255,255,255,0.72)", width: 0.5 },
          },
          error_y: {
            type: "data",
            array: uncertainty.error,
            symmetric: true,
            visible: true,
            color: series.color,
            thickness: 1,
            width: 2,
          },
          text: uncertainty.y.map(
            (value, index) =>
              `<b>${series.label} · ${uncertainty.groupLabels[index]}</b><br>` +
              `${uncertainty.intervalLabels[index]}<br>` +
              `${series.label} = ${formatValue(value)} ± ${formatValue(
                uncertainty.error[index],
              )} (1σ)`,
          ),
          hovertemplate: "%{text}<extra></extra>",
        });
      }
    }
    return traces;
  });
}

export function buildChiTraces(
  energyBounds: readonly number[],
  values: readonly number[],
  standardDeviations?: readonly number[] | null,
): Data[] {
  const coordinates = buildGroupStepCoordinates(energyBounds, values);
  if (coordinates == null) return [];
  const nonnegativeY = coordinates.y.map((value) =>
    value >= 0 ? value : null,
  );
  if (nonnegativeY.every((value) => value == null)) return [];

  const traces: Data[] = [
    {
      x: coordinates.x,
      y: nonnegativeY,
      type: "scatter",
      mode: "lines",
      connectgaps: false,
      name: "χg",
      line: { color: "#fbbf24", width: 2 },
      text: coordinates.y.map(
        (value, index) =>
          `<b>χg · ${coordinates.groupLabels[index]}</b><br>` +
          `${coordinates.intervalLabels[index]}<br>` +
          `χg = ${formatChi(value)}`,
      ),
      hovertemplate: "%{text}<extra></extra>",
    },
  ];

  if (standardDeviations != null) {
    const uncertainty = buildGroupUncertaintyPoints(
      energyBounds,
      values,
      standardDeviations,
      false,
    );
    if (uncertainty != null) {
      traces.push({
        x: uncertainty.x,
        y: uncertainty.y,
        type: "scatter",
        mode: "markers",
        name: "χg ±1σ",
        showlegend: false,
        marker: {
          color: "#fbbf24",
          size: 4,
          line: { color: "rgba(255,255,255,0.72)", width: 0.5 },
        },
        error_y: {
          type: "data",
          array: uncertainty.error,
          symmetric: true,
          visible: true,
          color: "#fbbf24",
          thickness: 1,
          width: 2,
        },
        text: uncertainty.y.map(
          (value, index) =>
            `<b>χg · ${uncertainty.groupLabels[index]}</b><br>` +
            `${uncertainty.intervalLabels[index]}<br>` +
            `χg = ${formatChi(value)} ± ${formatChi(
              uncertainty.error[index],
            )} (1σ)`,
        ),
        hovertemplate: "%{text}<extra></extra>",
      });
    }
  }

  return traces;
}

function formatEnergy(value: number): string {
  return value.toExponential(3);
}

function formatValue(value: number): string {
  return Math.abs(value) >= 1e4 || (value !== 0 && Math.abs(value) < 1e-3)
    ? value.toExponential(4)
    : value.toPrecision(5);
}

function formatChi(value: number): string {
  return Math.abs(value) >= 1e4 || (value !== 0 && Math.abs(value) < 1e-4)
    ? value.toExponential(4)
    : value.toPrecision(5);
}
