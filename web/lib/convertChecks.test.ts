import { describe, expect, it } from "vitest";
import {
  CONVERT_CHECKS_DEFAULTS,
  CONVERT_CHECKS_LEVELS,
  convertChecksFlags,
  convertChecksLevel,
  convertChecksLevelDescription,
  convertChecksLevelLabel,
} from "./convertChecks";

describe("convertChecks", () => {
  it("defaults the converter form to the production contract", () => {
    expect(CONVERT_CHECKS_DEFAULTS).toEqual({ check: true, production: true });
    expect(
      convertChecksLevel(
        CONVERT_CHECKS_DEFAULTS.check,
        CONVERT_CHECKS_DEFAULTS.production,
      ),
    ).toBe("production");
  });

  it("maps flag pairs onto the three-level checks enum", () => {
    expect(convertChecksLevel(true, true)).toBe("production");
    expect(convertChecksLevel(true, false)).toBe("standard");
    expect(convertChecksLevel(false, false)).toBe("none");
    // --production implies the strict preset even if check was toggled off.
    expect(convertChecksLevel(false, true)).toBe("production");
  });

  it("round-trips every level through its flag pair", () => {
    for (const level of CONVERT_CHECKS_LEVELS) {
      const { check, production } = convertChecksFlags(level);
      expect(convertChecksLevel(check, production)).toBe(level);
    }
  });

  it("labels every level and shows the CLI flag in its description", () => {
    expect(convertChecksLevelLabel("production")).toBe("Production");
    expect(convertChecksLevelLabel("standard")).toBe("Standard");
    expect(convertChecksLevelLabel("none")).toBe("None");
    expect(convertChecksLevelDescription("production")).toContain(
      "--production",
    );
    expect(convertChecksLevelDescription("standard")).toContain("--check");
    expect(convertChecksLevelDescription("none")).toContain("dry run");
  });
});
