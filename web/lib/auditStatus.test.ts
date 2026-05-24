import { describe, expect, it } from "vitest";
import type { SphLoopSummary } from "./api";
import {
  convergenceStatus,
  gateStatus,
  isPassDecision,
  shouldShowAcceptedUnconverged,
  summarizeChecks,
} from "./auditStatus";

function acceptedButUnconverged(): SphLoopSummary {
  return {
    schema: "openmc2donjon.sph-loop.v1",
    decision: "openmc2donjon_sph_loop_passed",
    package_version: "0.1.2",
    iterations: 10,
    completed_iterations: 10,
    converged: false,
    convergence_enabled: true,
    stop_reason: "max_iterations",
    sph_change_tolerance: 1.0e-12,
    flux_ratio_tolerance: 1.0e-12,
    min_iterations: 10,
    convergence: [],
    acceptance: {
      enabled: true,
      passed: true,
      decision: "openmc2donjon_sph_loop_acceptance_passed",
      fail_on_violation: false,
      checks: [
        {
          name: "min_completed_iterations",
          passed: true,
          actual: 10,
          limit: 10,
          units: "iterations",
          message: "actual 10 >= limit 10 iterations",
        },
      ],
    },
    production_audit: {
      passed: true,
      errors: [],
      checks: [],
    },
    quality: {
      initial_flux_ratio_max_residual: 0.36,
      final_flux_ratio_max_residual: 0.14,
      final_to_initial_flux_residual_ratio: 0.4,
      flux_residual_improved: true,
      final_clipped_count: 0,
      final_clipped_fraction: 0,
      maximum_clipped_count: 0,
      maximum_clipped_fraction: 0,
      clipping_observed: false,
      final_sph_minimum: 0.87,
      final_sph_maximum: 1.23,
      initial_worst_residual_bin: null,
      final_worst_residual_bin: null,
      final_worst_residual_bins: [],
      final_clipped_bins: [],
    },
    audit_rows: [],
    solves: [],
  };
}

describe("audit status helpers", () => {
  it("distinguishes accepted runs from converged SPH loops", () => {
    const summary = acceptedButUnconverged();

    expect(isPassDecision(summary.decision)).toBe(true);
    expect(gateStatus(true, summary.acceptance.passed, summarizeChecks(summary.acceptance.checks))).toMatchObject({
      value: "pass",
      tone: "pass",
    });
    expect(convergenceStatus(summary)).toMatchObject({
      value: "not reached",
      tone: "warn",
    });
    expect(shouldShowAcceptedUnconverged(summary)).toBe(true);
  });
});
