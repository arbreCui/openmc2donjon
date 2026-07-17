import { describe, expect, it } from "vitest";
import {
  fissionDeclarationConflict,
  invalidGroupConstants,
} from "./CrossSectionPlot";
import {
  buildChiTraces,
  buildGroupStepCoordinates,
  buildGroupUncertaintyPoints,
  buildMacroscopicTraces,
  validEnergyBounds,
  type PlottableCrossSections,
} from "./groupConstantPlot";

const EMPTY_XS: PlottableCrossSections = {
  total: null,
  transport_total: null,
  absorption: null,
  fission: null,
  nu_fission: null,
  chi: null,
  kappa_fission: null,
  inverse_velocity: null,
  flux_weight: null,
  sph: null,
};

describe("multigroup plotting coordinates", () => {
  it("maps g1-high arrays onto ascending true energy boundaries", () => {
    const coordinates = buildGroupStepCoordinates(
      [1, 10, 100, 1_000],
      [30, 20, 10],
    );

    expect(coordinates).toMatchObject({
      x: [1, 10, 10, 100, 100, 1_000],
      y: [10, 10, 20, 20, 30, 30],
      groupLabels: ["g3", "g3", "g2", "g2", "g1", "g1"],
    });
  });

  it("uses the complete boundary range and transitions exactly at a boundary", () => {
    const coordinates = buildGroupStepCoordinates([0.1, 1, 20], [4, 2]);
    expect(coordinates?.x.at(0)).toBe(0.1);
    expect(coordinates?.x.at(-1)).toBe(20);
    expect(coordinates?.x.slice(1, 3)).toEqual([1, 1]);
    expect(coordinates?.y.slice(1, 3)).toEqual([2, 4]);
  });

  it("rejects descending, non-positive, repeated, or mismatched contracts", () => {
    expect(validEnergyBounds([1, 10, 100])).toBe(true);
    expect(validEnergyBounds([100, 10, 1])).toBe(false);
    expect(validEnergyBounds([0, 1, 10])).toBe(false);
    expect(validEnergyBounds([1, 1, 10])).toBe(false);
    expect(buildGroupStepCoordinates([1, 10, 100], [1])).toBeNull();
  });

  it("places uncertainty markers at logarithmic group centres in g1 order", () => {
    const points = buildGroupUncertaintyPoints(
      [1, 10, 100],
      [20, 10],
      [2, 1],
    );
    expect(points?.x[0]).toBeCloseTo(Math.sqrt(1_000));
    expect(points?.x[1]).toBeCloseTo(Math.sqrt(10));
    expect(points).toMatchObject({
      y: [20, 10],
      error: [2, 1],
      groupLabels: ["g1", "g2"],
    });
  });
});

describe("macroscopic constant traces", () => {
  it("uses macroscopic symbols and supports transport total", () => {
    const traces = buildMacroscopicTraces(
      [1, 10, 100],
      {
        ...EMPTY_XS,
        total: [2, 1],
        transport_total: [1.8, 0.9],
        absorption: [0.2, 0.1],
        fission: [0.1, 0.05],
        nu_fission: [0.24, 0.12],
      },
    );
    expect(traces.map((trace) => trace.name)).toEqual([
      "Σt (total)",
      "Σtr (transport total)",
      "Σa (absorption)",
      "Σf (fission)",
      "νΣf (nu-fission)",
    ]);
  });

  it("adds one-standard-deviation error bars without changing the step", () => {
    const traces = buildMacroscopicTraces(
      [1, 10, 100],
      { ...EMPTY_XS, total: [2, 1] },
      { total: [0.2, 0.1] },
    );
    expect(traces).toHaveLength(2);
    expect(traces[0].x).toEqual([1, 10, 10, 100]);
    expect(traces[0].y).toEqual([1, 1, 2, 2]);
    expect(traces[1].name).toBe("Σt ±1σ");
    expect(traces[1].error_y).toMatchObject({
      array: [0.2, 0.1],
      visible: true,
    });
  });

  it("does not invent positive floors for zero-valued groups", () => {
    const traces = buildMacroscopicTraces(
      [1, 10, 100],
      { ...EMPTY_XS, fission: [1, 0] },
    );
    expect(traces[0].y).toEqual([null, null, 1, 1]);
  });
});

describe("fission spectrum traces", () => {
  it("keeps chi dimensionless and separate from macroscopic traces", () => {
    const macro = buildMacroscopicTraces(
      [1, 10, 100],
      { ...EMPTY_XS, total: [2, 1], chi: [0.9, 0.1] },
    );
    const chi = buildChiTraces([1, 10, 100], [0.9, 0.1]);
    expect(macro.map((trace) => trace.name)).toEqual(["Σt (total)"]);
    expect(chi).toHaveLength(1);
    expect(chi[0].name).toBe("χg");
    expect(chi[0].x).toEqual([1, 10, 10, 100]);
    expect(chi[0].y).toEqual([0.1, 0.1, 0.9, 0.9]);
  });
});

describe("invalid group constants", () => {
  it("flags non-positive transport quantities and negative reaction data", () => {
    expect(
      invalidGroupConstants({
        ...EMPTY_XS,
        total: [1, 0],
        transport_total: [-1, 0.5],
        absorption: [0.1, -0.2],
        chi: [1, -0.1],
      }),
    ).toEqual([
      { field: "total", group: 2, value: 0 },
      { field: "transport_total", group: 1, value: -1 },
      { field: "absorption", group: 2, value: -0.2 },
      { field: "chi", group: 2, value: -0.1 },
    ]);
  });
});

describe("fission declaration consistency", () => {
  it("flags nonzero raw fission data under fissionable=false", () => {
    expect(
      fissionDeclarationConflict(
        { ...EMPTY_XS, fission: [0.01], nu_fission: [0.025], chi: [1] },
        false,
      ),
    ).toEqual({
      declared: false,
      fields: ["fission", "nu_fission", "chi"],
    });
  });

  it("flags an incomplete fission source under fissionable=true", () => {
    expect(
      fissionDeclarationConflict(
        { ...EMPTY_XS, fission: [0.01], nu_fission: [0], chi: [1] },
        true,
      ),
    ).toEqual({ declared: true, fields: ["nu_fission"] });
    expect(
      fissionDeclarationConflict(
        { ...EMPTY_XS, fission: [0.01], nu_fission: [0.025], chi: [1] },
        true,
      ),
    ).toBeNull();
  });
});
