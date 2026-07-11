import { describe, expect, it } from "vitest";
import { buildExtensionRegex } from "./fileBrowserExtensions";

describe("buildExtensionRegex", () => {
  it("matches dotted and undotted extension specs alike", () => {
    // Regression: the builder specs pass dotted extensions ([".h5"])
    // while the equivalence page passes undotted (["h5"]); the dotted
    // form used to match nothing and hid every selectable file.
    expect(buildExtensionRegex([".h5", ".hdf5"]).test("reference.h5")).toBe(true);
    expect(buildExtensionRegex([".h5", ".hdf5"]).test("reference.hdf5")).toBe(true);
    expect(buildExtensionRegex(["h5", "hdf5"]).test("reference.h5")).toBe(true);
    expect(buildExtensionRegex(["h5", "hdf5"]).test("reference.hdf5")).toBe(true);
  });

  it("is case-insensitive and anchored at end-of-name", () => {
    const regex = buildExtensionRegex([".json"]);
    expect(regex.test("summary.JSON")).toBe(true);
    expect(regex.test("summary.json.bak")).toBe(false);
    expect(regex.test("json")).toBe(false);
  });

  it("keeps literal dots in multi-part extensions", () => {
    const regex = buildExtensionRegex([".mcompo.txt"]);
    expect(regex.test("out.mcompo.txt")).toBe(true);
    expect(regex.test("outXmcompo.txt")).toBe(false);
  });

  it("rejects files that miss the filter", () => {
    expect(buildExtensionRegex([".h5"]).test("notes.txt")).toBe(false);
  });

  it("matches nothing when no extensions are supplied", () => {
    expect(buildExtensionRegex([]).test("anything.h5")).toBe(false);
  });
});
