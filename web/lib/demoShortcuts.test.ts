import { describe, expect, it } from "vitest";
import { HOME_DEMO_SHORTCUTS, MOCK_AUDIT_DEMO_PATH } from "./demoShortcuts";

describe("home demo shortcuts", () => {
  it("offers converter, inspector, and audit demos in a stable order", () => {
    expect(HOME_DEMO_SHORTCUTS.map((entry) => entry.id)).toEqual([
      "convert-c5g7",
      "inspect-c5g7",
      "audit-sph",
    ]);
  });

  it("deep-links to prefilled demo pages", () => {
    const [convert, inspect, audit] = HOME_DEMO_SHORTCUTS;
    expect(convert.href).toContain("/convert?intent=direct-convert");
    expect(convert.href).toContain("input=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5");
    expect(inspect.href).toBe(
      "/inspect?path=%2Fmock%2Fhome%2Fopenmc-runs%2Fc5g7%2Fhandoff.h5",
    );
    expect(audit.href).toBe(
      `/audit?path=${encodeURIComponent(MOCK_AUDIT_DEMO_PATH)}`,
    );
  });
});
