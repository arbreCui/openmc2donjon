import { describe, expect, it } from "vitest";
import { buildGroupVectorRows } from "./GroupVectorTable";

describe("buildGroupVectorRows", () => {
  it("maps ascending contract bounds onto high-to-low group vectors", () => {
    const rows = buildGroupVectorRows(
      [1.0e-5, 1, 1.0e7],
      [0.3, 0.4],
      [0.003, 0.008],
    );

    expect(rows).toEqual([
      {
        group: 1,
        lower: 1,
        upper: 1.0e7,
        value: 0.3,
        standardDeviation: 0.003,
        relativePercent: 1,
      },
      {
        group: 2,
        lower: 1.0e-5,
        upper: 1,
        value: 0.4,
        standardDeviation: 0.008,
        relativePercent: 2,
      },
    ]);
  });

  it("preserves raw group values when bounds are absent, malformed, or mismatched", () => {
    for (const bounds of [[1, 1, 10], [100, 10, 1], [1, 10], []]) {
      expect(buildGroupVectorRows(bounds, [2, 3])).toMatchObject([
        { group: 1, lower: null, upper: null, value: 2 },
        { group: 2, lower: null, upper: null, value: 3 },
      ]);
    }
  });

  it("omits invalid or mismatched uncertainty values", () => {
    const mismatched = buildGroupVectorRows([1, 10, 100], [2, 3], [0.1]);
    expect(mismatched.map((row) => row.standardDeviation)).toEqual([null, null]);

    const invalid = buildGroupVectorRows([1, 10, 100], [2, 3], [-1, Number.NaN]);
    expect(invalid.map((row) => row.standardDeviation)).toEqual([null, null]);
  });
});
