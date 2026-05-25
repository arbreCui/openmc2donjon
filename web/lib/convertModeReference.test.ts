import { describe, expect, it } from "vitest";
import { convertModeReference } from "./convertModeReference";

describe("convertModeReference", () => {
  it("keeps dry-run, convert, and review in the user-facing order", () => {
    const items = convertModeReference("multicompo");

    expect(items.map((item) => item.id)).toEqual([
      "dry-run",
      "convert",
      "review",
    ]);
    expect(items[0].body).toContain("never creates or replaces");
    expect(items[1].title).toContain("L_MULTICOMPO");
    expect(items[2].body).toContain("bundle builder");
  });

  it("names the selected DONJON ASCII object", () => {
    expect(convertModeReference("macrolib")[1].title).toContain("L_MACROLIB");
  });
});
