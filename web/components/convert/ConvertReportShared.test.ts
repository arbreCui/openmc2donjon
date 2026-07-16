import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput } from "@/lib/api";
import {
  compactEquivalence,
  uncertaintyGateStatus,
} from "./ConvertReportShared";

describe("compactEquivalence", () => {
  it("reports pre-applied SPH even after active NSPH datasets are removed", () => {
    const input = {
      sph_applied: true,
      sph_calculations: 0,
      adf_mixtures: 0,
    } as ConvertPreflightInput;

    expect(compactEquivalence(input)).toBe("SPH applied");
  });
});

describe("uncertaintyGateStatus", () => {
  it("fails when missing std_dev coverage is a production issue", () => {
    const input = {
      path: "/tmp/input.h5",
      ok: false,
      energy_groups: 2,
      legendre_order: 0,
      uncertainty: {
        checked: true,
        datasets: 0,
        expected_datasets: 8,
        missing_datasets: 8,
      },
      issues: ["MGXS statistical uncertainty std_dev coverage incomplete: 0/8"],
      warnings: [],
    } as ConvertPreflightInput;

    expect(uncertaintyGateStatus(input)).toBe("fail");
  });

  it("does not show unaudited uncertainty as a pass", () => {
    const input = {
      path: "/tmp/input.h5",
      ok: true,
      energy_groups: 2,
      legendre_order: 0,
      issues: [],
      warnings: [],
    } as ConvertPreflightInput;

    expect(uncertaintyGateStatus(input)).toBe("skipped");
  });
});
