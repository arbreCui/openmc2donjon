import { describe, expect, it } from "vitest";
import { filterAuditChecks } from "./auditCheckFilter";
import type { SphLoopAcceptanceCheck } from "./api";

const checks: SphLoopAcceptanceCheck[] = [
  {
    name: "require_reference_flux_std_dev",
    passed: true,
    actual: true,
    limit: true,
    units: null,
    message: "reference flux std_dev present",
  },
  {
    name: "max_mgxs_scatter_row_balance_rel",
    passed: false,
    actual: 0.12,
    limit: 0.05,
    units: "relative",
    message: "scatter row balance too high",
  },
  {
    name: "require_mgxs_h_factor",
    passed: true,
    actual: 9,
    limit: 9,
    units: "mixtures",
    message: "all fissionable mixtures carry H-FACTOR",
  },
];

describe("audit check filtering", () => {
  it("returns all checks for a blank query", () => {
    expect(filterAuditChecks(checks, "   ")).toHaveLength(3);
  });

  it("matches check names and messages case-insensitively", () => {
    expect(filterAuditChecks(checks, "STD_DEV")).toEqual([checks[0]]);
    expect(filterAuditChecks(checks, "h-factor")).toEqual([checks[2]]);
  });

  it("requires all search terms to match the same check", () => {
    expect(filterAuditChecks(checks, "scatter fail")).toEqual([checks[1]]);
    expect(filterAuditChecks(checks, "scatter pass")).toEqual([]);
  });

  it("matches numeric actual and limit values", () => {
    expect(filterAuditChecks(checks, "0.05")).toEqual([checks[1]]);
  });
});
