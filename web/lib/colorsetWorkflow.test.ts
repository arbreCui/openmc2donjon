import { describe, expect, it } from "vitest";
import {
  COLORSET_DEFINITIONS,
  REQUIRED_COLORSET_COUNT,
  colorsetConvertHref,
  colorsetDefinition,
  colorsetOpenmcHref,
  colorsetSphHref,
  isWithdrawnColorsetWorkflow,
} from "./colorsetWorkflow";

describe("withdrawn IRENA colorset diagnostic", () => {
  it("retains the five historical target environments plus optional REFL", () => {
    expect(COLORSET_DEFINITIONS.map((item) => item.id)).toEqual([
      "int_ext",
      "ext_int",
      "csd_int",
      "dsdf_int",
      "pnl_ext",
      "refl_ext",
    ]);
    expect(REQUIRED_COLORSET_COUNT).toBe(5);
    expect(COLORSET_DEFINITIONS.filter((item) => !item.required)).toHaveLength(1);
  });

  it("keeps the target assembly at the center of every colorset", () => {
    expect(
      COLORSET_DEFINITIONS.map(({ id, target, neighbors }) => [
        id,
        target,
        neighbors,
      ]),
    ).toEqual([
      ["int_ext", "INT", "EXT"],
      ["ext_int", "EXT", "INT"],
      ["csd_int", "CSD", "INT"],
      ["dsdf_int", "DSDF", "INT"],
      ["pnl_ext", "PNL", "EXT"],
      ["refl_ext", "REFL", "EXT"],
    ]);
  });

  it("deep-links archived views without creating a production chain", () => {
    const openmc = colorsetOpenmcHref("csd_int");
    const convert = colorsetConvertHref("csd_int");
    expect(openmc).toContain("colorset=csd_int");
    expect(openmc).toContain("equivalence=direct");
    expect(openmc).toContain("production=0");
    expect(openmc).not.toContain("production=1");
    expect(colorsetSphHref("csd_int")).toBe(
      "/equivalence?kind=openmc-sph-sidecar&colorset=csd_int&contract=irena30-colorset-sph&diagnostic=withdrawn-five-colorset",
    );
    expect(convert).toContain("format=multicompo");
    expect(convert).toContain("production=0");
    expect(convert).not.toContain("production=1");
    expect(convert).toContain("diagnostic=withdrawn-five-colorset");
    expect(convert).toContain("#convert-component");
  });

  it("fail-closes bare colorset and legacy-contract queries only", () => {
    expect(isWithdrawnColorsetWorkflow("csd_int", null)).toBe(true);
    expect(isWithdrawnColorsetWorkflow("", null)).toBe(true);
    expect(isWithdrawnColorsetWorkflow(null, "irena30-colorset-sph")).toBe(true);
    expect(isWithdrawnColorsetWorkflow(null, "physical-colorset-sph")).toBe(true);
    expect(
      isWithdrawnColorsetWorkflow(
        null,
        "native-sph",
        "withdrawn-five-colorset",
      ),
    ).toBe(true);
    expect(isWithdrawnColorsetWorkflow(null, "physical-sph")).toBe(false);
    expect(isWithdrawnColorsetWorkflow(null, "native-sph")).toBe(false);
  });

  it("falls back to the first historical case for an unknown query", () => {
    expect(colorsetDefinition("unknown").id).toBe("int_ext");
  });
});
