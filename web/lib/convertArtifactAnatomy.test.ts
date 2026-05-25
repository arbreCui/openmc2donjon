import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput } from "./api";
import { convertArtifactAnatomy } from "./convertArtifactAnatomy";

function input(overrides: Partial<ConvertPreflightInput> = {}): ConvertPreflightInput {
  return {
    path: "/runs/case/mgxs_library.h5",
    ok: true,
    energy_groups: 7,
    legendre_order: 1,
    mixtures: 9,
    calculations: 9,
    state_points: 1,
    adf_mixtures: 9,
    adf_faces: ["XMIN", "XMAX", "YMIN", "YMAX"],
    sph_calculations: 9,
    issues: [],
    warnings: [],
    ...overrides,
  };
}

describe("convertArtifactAnatomy", () => {
  it("describes MULTICOMPO as mapped mixture/calculation storage", () => {
    const anatomy = convertArtifactAnatomy("multicompo", input());

    expect(anatomy.label).toBe("L_MULTICOMPO");
    expect(anatomy.countLine).toContain("9 mixture(s)");
    expect(anatomy.countLine).toContain("2 Legendre moment(s)");
    expect(anatomy.sections.map((section) => section.id)).toEqual([
      "header",
      "map",
      "xs",
      "equivalence",
    ]);
    expect(anatomy.sections.flatMap((section) => section.blocks)).toEqual(
      expect.arrayContaining(["MIXTURES", "CALCULATIONS", "ISOTOPESLIST", "SCATxx"]),
    );
    expect(anatomy.sections.find((section) => section.id === "equivalence")?.body).toContain(
      "ADF",
    );
  });

  it("describes MACROLIB as compact group-major storage", () => {
    const anatomy = convertArtifactAnatomy(
      "macrolib",
      input({ adf_mixtures: 0, adf_faces: [], sph_calculations: 0 }),
    );

    expect(anatomy.label).toBe("L_MACROLIB");
    expect(anatomy.subtitle).toContain("group-major");
    expect(anatomy.sections.flatMap((section) => section.blocks)).toEqual(
      expect.arrayContaining(["GROUP", "VOLUME", "DIFF", "NJJSxx", "IJJSxx"]),
    );
    expect(anatomy.sections.find((section) => section.id === "equivalence")?.body).toContain(
      "No ADF or SPH",
    );
  });

  it("falls back cleanly when preflight metadata is missing", () => {
    const anatomy = convertArtifactAnatomy("multicompo", null);

    expect(anatomy.countLine).toContain("preflight");
    expect(anatomy.sections.find((section) => section.id === "equivalence")?.body).toContain(
      "when present",
    );
  });
});
