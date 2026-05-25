import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput } from "./api";
import {
  convertShowcaseDefaultOpen,
  convertShowcaseFacts,
  convertShowcaseObjectLabel,
} from "./convertShowcase";

describe("convert showcase", () => {
  it("describes MULTICOMPO and MACROLIB output objects", () => {
    expect(convertShowcaseObjectLabel("multicompo")).toBe("L_MULTICOMPO");
    expect(convertShowcaseObjectLabel("macrolib")).toBe("L_MACROLIB");
    expect(
      convertShowcaseFacts({
        format: "multicompo",
        check: true,
        production: true,
        requireKnownMesh: false,
        input: null,
      })[0].body,
    ).toContain("ordered mixture slots");
  });

  it("surfaces production gate mode and known-mesh strictness", () => {
    const gates = convertShowcaseFacts({
      format: "multicompo",
      check: true,
      production: true,
      requireKnownMesh: true,
      input: null,
    }).find((fact) => fact.id === "gates");
    expect(gates?.badge).toBe("strict mesh + production");
    expect(gates?.tone).toBe("pass");
  });

  it("reports ADF and SPH carry-through after preflight", () => {
    const equivalence = convertShowcaseFacts({
      format: "multicompo",
      check: true,
      production: true,
      requireKnownMesh: false,
      input: input({ adf_mixtures: 9, adf_faces: ["north", "south"], sph_calculations: 9 }),
    }).find((fact) => fact.id === "equivalence");
    expect(equivalence?.badge).toBe("9 ADF mix · 9 SPH");
    expect(equivalence?.body).toContain("2 face type");
  });

  it("warns when preflight reports direct XS only", () => {
    const equivalence = convertShowcaseFacts({
      format: "macrolib",
      check: false,
      production: false,
      requireKnownMesh: false,
      input: input({ adf_mixtures: 0, adf_faces: [], sph_calculations: 0 }),
    }).find((fact) => fact.id === "equivalence");
    expect(equivalence?.badge).toBe("direct XS only");
    expect(equivalence?.tone).toBe("warn");
  });

  it("only expands the explanatory section before a run result exists", () => {
    expect(convertShowcaseDefaultOpen("idle")).toBe(true);
    expect(convertShowcaseDefaultOpen("loading")).toBe(false);
    expect(convertShowcaseDefaultOpen("ok")).toBe(false);
    expect(convertShowcaseDefaultOpen("error")).toBe(false);
  });
});

function input(
  partial: Partial<ConvertPreflightInput> = {},
): ConvertPreflightInput {
  return {
    path: "/mock/handoff.h5",
    ok: true,
    energy_groups: 7,
    legendre_order: 1,
    mixtures: 9,
    calculations: 9,
    state_points: 1,
    issues: [],
    warnings: [],
    ...partial,
  };
}
