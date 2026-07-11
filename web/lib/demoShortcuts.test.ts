import { describe, expect, it } from "vitest";
import { HOME_DEMO_SHORTCUTS } from "./demoShortcuts";

describe("home demo shortcuts", () => {
  it("offers only the primary converter demo — landing pages self-serve the rest", () => {
    expect(HOME_DEMO_SHORTCUTS.map((entry) => entry.id)).toEqual([
      "convert-c5g7",
    ]);
    expect(HOME_DEMO_SHORTCUTS[0].cta).toBe("Open converter demo");
  });

  it("deep-links to the prefilled converter demo", () => {
    const [convert] = HOME_DEMO_SHORTCUTS;
    expect(convert.href).toContain("/convert?intent=direct-convert");
    expect(convert.href).toContain(
      "input=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5",
    );
  });
});
