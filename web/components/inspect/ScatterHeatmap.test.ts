import { describe, expect, it } from "vitest";
import type { ScatterMoment } from "../../lib/api";
import {
  buildScatterGroupLabels,
  buildScatterLayout,
  buildScatterTraces,
  scatterStatisticalResolution,
} from "./ScatterHeatmap";

const BOUNDS = [0.625, 4, 5_530, 821_000, 20_000_000] as const;

function scatter(moment: number, values: number[][]): ScatterMoment {
  return {
    axes: "from,to",
    shape: [values.length, values.length],
    moment_index: moment,
    values,
    std_dev_shape: null,
    std_dev_values: null,
  };
}

type HeatmapTrace = {
  z: Array<Array<number | null>>;
  x: string[];
  y: string[];
  customdata: string[][];
  colorscale: string | Array<[number, string]>;
  zmin?: number;
  zmax?: number;
  zmid?: number;
  showscale: boolean;
};

describe("buildScatterGroupLabels", () => {
  it("maps ascending boundaries to g1 as the highest-energy interval", () => {
    const labels = buildScatterGroupLabels(BOUNDS, 4);

    expect(labels.map((label) => label.range)).toEqual([
      "0.821–20 MeV",
      "5.53–821 keV",
      "0.004–5.53 keV",
      "0.625–4 eV",
    ]);
    expect(labels[0].axis).toBe("g1<br>0.821–20 MeV");
    expect(labels[3].hover).toBe("g4 [0.625–4 eV]");
  });

  it("falls back to unambiguous group ids for malformed boundaries", () => {
    expect(buildScatterGroupLabels([20, 1, 0], 2)).toEqual([
      { id: "g1", axis: "g1", hover: "g1", range: null },
      { id: "g2", axis: "g2", hover: "g2", range: null },
    ]);
  });
});

describe("buildScatterTraces", () => {
  it("renders P0 positive values with Viridis and exact zeros separately", () => {
    const traces = buildScatterTraces(
      scatter(0, [
        [1, 0],
        [0.1, 0.2],
      ]),
      [0.625, 4, 20_000_000],
      "linear",
      [
        [0.01, 0],
        [0.002, 0.003],
      ],
    ) as unknown as HeatmapTrace[];

    expect(traces).toHaveLength(2);
    expect(traces[0].z).toEqual([
      [null, 0],
      [null, null],
    ]);
    expect(traces[0].showscale).toBe(false);
    expect(traces[1].colorscale).toBe("Viridis");
    expect(traces[1].z).toEqual([
      [1, null],
      [0.1, 0.2],
    ]);
    expect(traces[1].zmin).toBe(0);
    expect(traces[1].zmax).toBe(1);
    expect(traces[1].x[0]).toContain("g1<br>");
    expect(traces[0].customdata[0][1]).toContain("(zero estimate)");
    expect(traces[1].customdata[0][0]).toContain("± 1.0000e-2 (1σ)");
  });

  it("applies log10 only to positive P0 cells", () => {
    const traces = buildScatterTraces(
      scatter(0, [
        [1e-2, 0],
        [1e-4, 1],
      ]),
      [0.625, 4, 20_000_000],
      "log10",
    ) as unknown as HeatmapTrace[];

    expect(traces).toHaveLength(2);
    expect(traces[1].colorscale).toBe("Viridis");
    expect(traces[1].z).toEqual([
      [-2, null],
      [-4, 0],
    ]);
    expect(traces[1].customdata[0][0]).toContain("log₁₀ = -2.000");
    expect(traces[0].customdata[0][1]).not.toContain("log₁₀");
  });

  it("uses one constant colour without a fabricated range for equal positive P0 log data", () => {
    const traces = buildScatterTraces(
      scatter(0, [
        [1, 0],
        [0, 1],
      ]),
      [0.625, 4, 20_000_000],
      "log10",
    ) as unknown as HeatmapTrace[];

    expect(traces).toHaveLength(2);
    expect(traces[1].showscale).toBe(false);
    expect(traces[1].zmin).toBeUndefined();
    expect(traces[1].zmax).toBeUndefined();
    expect(traces[1].colorscale).toEqual([
      [0, "#2f7f86"],
      [1, "#2f7f86"],
    ]);
  });

  it("preserves signed P1+ values on a symmetric diverging scale", () => {
    const values = [
      [0.2, -0.1],
      [0, 0.05],
    ];
    // A stale controlled log10 selection must not logarithmically transform
    // a signed higher Legendre moment.
    const traces = buildScatterTraces(
      scatter(1, values),
      [0.625, 4, 20_000_000],
      "log10",
    ) as unknown as HeatmapTrace[];

    expect(traces).toHaveLength(1);
    expect(traces[0].z).toEqual(values);
    expect(traces[0].zmin).toBe(-0.2);
    expect(traces[0].zmid).toBe(0);
    expect(traces[0].zmax).toBe(0.2);
    expect(traces[0].colorscale).toEqual([
      [0, "#2563eb"],
      [0.5, "#f5f5f4"],
      [1, "#dc2626"],
    ]);
    expect(traces[0].customdata[0][1]).toContain("P1 scatter = -1.0000e-1");
    expect(traces[0].customdata[0][1]).not.toContain("log₁₀");
  });

  it("renders an all-zero higher moment neutrally without a colour bar", () => {
    const traces = buildScatterTraces(
      scatter(2, [
        [0, 0],
        [0, 0],
      ]),
      [0.625, 4, 20_000_000],
      "linear",
    ) as unknown as HeatmapTrace[];

    expect(traces).toHaveLength(1);
    expect(traces[0].showscale).toBe(false);
    expect(traces[0].zmin).toBeUndefined();
    expect(traces[0].zmax).toBeUndefined();
    expect(traces[0].colorscale).toEqual([
      [0, "#2a2d3a"],
      [1, "#2a2d3a"],
    ]);
  });

  it("rejects ragged or non-finite matrices rather than plotting them", () => {
    expect(
      buildScatterTraces(scatter(0, [[1], [2, 3]]), [0, 1, 2], "linear"),
    ).toEqual([]);
    expect(
      buildScatterTraces(scatter(1, [[Number.NaN]]), [0, 1], "linear"),
    ).toEqual([]);
  });
});

describe("buildScatterLayout", () => {
  it("keeps from on rows, to on columns, and g1 at the top", () => {
    const layout = buildScatterLayout();

    expect(layout.xaxis).toMatchObject({
      title: { text: "to group (outgoing)" },
    });
    expect(layout.yaxis).toMatchObject({
      autorange: "reversed",
      title: { text: "from group (incoming)" },
    });
  });
});

describe("scatterStatisticalResolution", () => {
  it("reports both resolved-cell count and L2 importance", () => {
    const result = scatterStatisticalResolution(
      [
        [1, 0.1],
        [0, 0.2],
      ],
      [
        [0.1, 0.1],
        [0, 0.1],
      ],
    );

    expect(result).toMatchObject({
      cellsWithUncertainty: 3,
      resolvedCells: 1,
      zeroSigmaNonzeroCells: 0,
    });
    expect(result?.resolvedL2Fraction).toBeCloseTo(1 / 1.05, 12);
  });

  it("uses the full matrix norm and reports nonzero zero-sigma cells separately", () => {
    const result = scatterStatisticalResolution(
      [
        [10, 1],
        [0, 0],
      ],
      [
        [0, 1],
        [0, 0],
      ],
    );

    expect(result).toEqual({
      cellsWithUncertainty: 1,
      resolvedCells: 0,
      resolvedL2Fraction: 0,
      zeroSigmaNonzeroCells: 1,
    });
  });

  it("does not invent a statistic without a valid uncertainty matrix", () => {
    expect(scatterStatisticalResolution([[1]], null)).toBeNull();
    expect(scatterStatisticalResolution([[1]], [[-1]])).toBeNull();
  });
});
