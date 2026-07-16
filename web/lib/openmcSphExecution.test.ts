import { describe, expect, it } from "vitest";
import {
  OPENMC_SPH_FIXED_POLICY,
  OPENMC_SPH_UPDATE_GATE,
  parseOpenmcSphDamping,
} from "./openmcSphExecution";

describe("OpenMC-side SPH execution policy", () => {
  it("exposes the fixed 2% update gate without calling it final acceptance", () => {
    expect(OPENMC_SPH_UPDATE_GATE).toBe(0.02);
    expect(OPENMC_SPH_FIXED_POLICY).toContainEqual([
      "Numerical exemptions",
      "None: no clipping, floors, or frozen groups",
    ]);
  });

  it("fails closed on missing, non-finite, or out-of-range damping", () => {
    for (const value of ["", "abc", "NaN", "Infinity", "-0.1", "1.01"]) {
      expect(parseOpenmcSphDamping(value).ok, value).toBe(false);
    }
    expect(parseOpenmcSphDamping("0")).toEqual({ ok: true, value: 0 });
    expect(parseOpenmcSphDamping("0.6")).toEqual({ ok: true, value: 0.6 });
    expect(parseOpenmcSphDamping("1")).toEqual({ ok: true, value: 1 });
  });
});
