import { describe, expect, it } from "vitest";
import {
  parseConvertIntent,
  parseConvertFormat,
  parseOpenmcEquivalence,
  parseOpenmcWorkflow,
  queryFlag,
} from "./workflowQuery";

describe("queryFlag", () => {
  it("uses the fallback when the key is absent or unknown", () => {
    const params = new URLSearchParams("production=maybe");
    expect(queryFlag(params, "check", true)).toBe(true);
    expect(queryFlag(params, "production", false)).toBe(false);
  });

  it("accepts common truthy and falsey flag spellings", () => {
    expect(queryFlag(new URLSearchParams("x=1"), "x", false)).toBe(true);
    expect(queryFlag(new URLSearchParams("x=true"), "x", false)).toBe(true);
    expect(queryFlag(new URLSearchParams("x=on"), "x", false)).toBe(true);
    expect(queryFlag(new URLSearchParams("x=0"), "x", true)).toBe(false);
    expect(queryFlag(new URLSearchParams("x=false"), "x", true)).toBe(false);
    expect(queryFlag(new URLSearchParams("x=off"), "x", true)).toBe(false);
  });
});

describe("workflow query parsers", () => {
  it("parses converter format with a safe default", () => {
    expect(parseConvertFormat("macrolib")).toBe("macrolib");
    expect(parseConvertFormat("multicompo")).toBe("multicompo");
    expect(parseConvertFormat("bad")).toBe("multicompo");
  });

  it("parses converter intent with a generic fallback", () => {
    expect(parseConvertIntent("direct-convert")).toBe("direct-convert");
    expect(parseConvertIntent("check")).toBe("check");
    expect(parseConvertIntent("openmc-sph")).toBe("openmc-sph");
    expect(parseConvertIntent("bad")).toBe("generic");
  });

  it("parses OpenMC workflow and equivalence values with safe defaults", () => {
    expect(parseOpenmcWorkflow("two-step")).toBe("two-step");
    expect(parseOpenmcWorkflow("one-step")).toBe("one-step");
    expect(parseOpenmcWorkflow("bad")).toBe("two-step");
    expect(parseOpenmcWorkflow(null)).toBe("two-step");

    expect(parseOpenmcEquivalence("adf")).toBe("adf");
    expect(parseOpenmcEquivalence("sph")).toBe("sph");
    expect(parseOpenmcEquivalence("flux-ratio-adf")).toBe("flux-ratio-adf");
    expect(parseOpenmcEquivalence("bad")).toBe("direct");
  });
});
