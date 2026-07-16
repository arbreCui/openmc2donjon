import { describe, expect, it } from "vitest";
import {
  mixtureScopeSelection,
  normalizeMixtureScope,
  toggleMixtureScope,
} from "./convertMixtureScope";

const names = ["fuel", "moderator", "reflector"];

describe("Converter mixture scope", () => {
  it("shows the empty contract value as all mixtures selected", () => {
    expect(mixtureScopeSelection("", names)).toMatchObject({
      allByDefault: true,
      selectedCount: 3,
    });
  });

  it("turns off one mixture from the default-all state explicitly", () => {
    const next = toggleMixtureScope("", "reflector", names);
    expect(next).toBe("fuel\nmoderator");
    expect(mixtureScopeSelection(next, names).selectedCount).toBe(2);
  });

  it("normalizes an explicit full selection back to the default empty value", () => {
    expect(normalizeMixtureScope(names, names)).toBe("");
    expect(toggleMixtureScope("fuel\nmoderator", "reflector", names)).toBe("");
  });

  it("does not discard unknown explicit names while normalizing", () => {
    expect(normalizeMixtureScope([...names, "custom"], names)).toContain("custom");
  });
});
