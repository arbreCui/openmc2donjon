import { describe, expect, it } from "vitest";
import { converterQuickStartHref } from "./converterQuickStart";

describe("converterQuickStartHref", () => {
  it("opens the standalone Converter without project assumptions", () => {
    const href = converterQuickStartHref(" /runs/case/mgxs.h5 ");
    expect(href).toContain("/convert?");
    expect(href).toContain("input=%2Fruns%2Fcase%2Fmgxs.h5");
    expect(href).toContain("check=1");
    expect(href).not.toContain("project=");
    expect(href).not.toContain("colorset=");
  });

  it("still opens Converter when the user wants to browse there", () => {
    expect(converterQuickStartHref("")).toBe(
      "/convert?check=1&production=1#convert-component",
    );
  });
});
