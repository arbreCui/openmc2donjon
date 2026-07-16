import { describe, expect, it } from "vitest";
import {
  inspectConvertHref,
  inspectDiffHref,
  inspectProductionStats,
  stdDevCoverageLabel,
  type InspectProductionInput,
} from "./inspectSummary";

const BASE: InspectProductionInput = {
  mesh_match: {
    id: "shem-361",
    name: "SHEM-361",
    short: "SHEM361",
    n_groups: 361,
    purpose: null,
    description: null,
  },
  calculation_count: 4,
  mixture_count: 4,
  transport_total: 4,
  h_factor: 2,
  fissionable_mixtures: 2,
  std_dev_datasets: 8,
  std_dev_expected_datasets: 8,
};

describe("inspect production stats", () => {
  it("marks a fully covered production file as pass on all four stats", () => {
    const stats = inspectProductionStats(BASE);
    expect(stats.mesh).toEqual({
      value: "SHEM361 (361g)",
      tone: "pass",
      detail: "Root energy_bounds match a bundled standard mesh.",
    });
    expect(stats.transport).toEqual({
      value: "4 / 4",
      tone: "pass",
      detail:
        "Explicit transport_total supports the deterministic diffusion/SPN route.",
    });
    expect(stats.hFactor).toEqual({
      value: "2 / 4",
      tone: "pass",
      detail: "Needed for power normalization in fissionable mixtures.",
    });
    expect(stats.stdDev).toEqual({
      value: "8 / 8",
      tone: "pass",
      detail:
        "Tally uncertainty is optional by default but important for production audits.",
    });
  });

  it("warns on an unknown mesh with the preflight rationale", () => {
    const stats = inspectProductionStats({ ...BASE, mesh_match: null });
    expect(stats.mesh).toEqual({
      value: "unknown mesh",
      tone: "warn",
      detail:
        "Production preflight will warn unless this custom mesh is expected.",
    });
  });

  it("warns on incomplete transport, H-factor, and std_dev coverage", () => {
    const stats = inspectProductionStats({
      ...BASE,
      transport_total: 3,
      h_factor: 1,
      std_dev_datasets: 2,
    });
    expect(stats.transport).toMatchObject({ value: "3 / 4", tone: "warn" });
    expect(stats.hFactor).toMatchObject({ value: "1 / 4", tone: "warn" });
    expect(stats.stdDev).toMatchObject({ value: "2 / 8", tone: "warn" });
  });

  it("falls back to mixture count when calculation_count is zero", () => {
    const stats = inspectProductionStats({
      ...BASE,
      calculation_count: 0,
      transport_total: 4,
    });
    expect(stats.transport).toMatchObject({ value: "4 / 4", tone: "pass" });
  });

  it("treats absent std_dev counters as pass with an em-dash value", () => {
    const stats = inspectProductionStats({
      ...BASE,
      std_dev_datasets: undefined,
      std_dev_expected_datasets: undefined,
    });
    expect(stats.stdDev).toMatchObject({ value: "—", tone: "pass" });
    expect(stdDevCoverageLabel({})).toBe("—");
    expect(stdDevCoverageLabel({ std_dev_datasets: 3 })).toBe("—");
  });
});

describe("inspect exits", () => {
  it("links to the converter with the inspected path prefilled", () => {
    expect(inspectConvertHref("/runs/case/handoff.h5", 0)).toBe(
      "/convert?input=%2Fruns%2Fcase%2Fhandoff.h5",
    );
  });

  it("preselects MACROLIB when the file carries SPH factors", () => {
    expect(inspectConvertHref("/runs/case/handoff.h5", 3)).toBe(
      "/convert?input=%2Fruns%2Fcase%2Fhandoff.h5&format=macrolib",
    );
  });

  it("uses the direct MULTICOMPO route when SPH is already applied", () => {
    expect(inspectConvertHref("/runs/case/handoff.h5", 0, true)).toBe(
      "/convert?input=%2Fruns%2Fcase%2Fhandoff.h5&intent=openmc-sph&format=multicompo",
    );
  });

  it("links to the diff builder with the inspected file as candidate", () => {
    expect(inspectDiffHref("/runs/case/handoff.h5")).toBe(
      "/builder?command=diff&candidate_h5=%2Fruns%2Fcase%2Fhandoff.h5",
    );
  });
});
