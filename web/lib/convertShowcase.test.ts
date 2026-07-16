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

  it("surfaces production check mode and known-mesh strictness", () => {
    const gates = convertShowcaseFacts({
      format: "multicompo",
      check: true,
      production: true,
      requireKnownMesh: true,
      input: null,
    }).find((fact) => fact.id === "gates");
    expect(gates?.badge).toBe("strict mesh + production");
    expect(gates?.tone).toBe("pass");
    // Labels show the flag they map to.
    expect(gates?.title).toBe("Production checks (--production)");
  });

  it("labels standard checks with the --check flag", () => {
    const gates = convertShowcaseFacts({
      format: "multicompo",
      check: true,
      production: false,
      requireKnownMesh: false,
      input: null,
    }).find((fact) => fact.id === "gates");
    expect(gates?.title).toBe("Preflight (--check)");
  });

  it("reports SPH carry-through after preflight", () => {
    const equivalence = convertShowcaseFacts({
      format: "multicompo",
      check: true,
      production: true,
      requireKnownMesh: false,
      input: input({ adf_mixtures: 9, adf_faces: ["north", "south"], sph_calculations: 9 }),
    }).find((fact) => fact.id === "equivalence");
    expect(equivalence?.badge).toBe("9 calculation record(s)");
    expect(equivalence?.body).toContain("NSPH");
  });

  it("accepts direct XS when no SPH contract was selected", () => {
    const equivalence = convertShowcaseFacts({
      format: "macrolib",
      check: false,
      production: false,
      requireKnownMesh: false,
      input: input({ adf_mixtures: 0, adf_faces: [], sph_calculations: 0 }),
    }).find((fact) => fact.id === "equivalence");
    expect(equivalence?.badge).toBe("direct cross sections");
    expect(equivalence?.tone).toBe("neutral");
  });

  it("recognizes apply-sph provenance without active NSPH records", () => {
    const equivalence = convertShowcaseFacts({
      format: "multicompo",
      check: true,
      production: false,
      requireKnownMesh: false,
      input: input({
        sph_calculations: 0,
        sph_applied: true,
        sph_kind: "openmc-ce-mg-global",
      }),
    }).find((fact) => fact.id === "equivalence");
    expect(equivalence?.title).toBe("SPH already applied");
    expect(equivalence?.badge).toBe("openmc-ce-mg-global");
    expect(equivalence?.tone).toBe("pass");
  });

  it("keeps the explanatory section collapsed for the guided workflow", () => {
    expect(convertShowcaseDefaultOpen("idle")).toBe(false);
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
