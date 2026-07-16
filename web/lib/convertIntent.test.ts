import { describe, expect, it } from "vitest";
import { convertIntentBannerVisible, convertIntentCopy } from "./convertIntent";

describe("convertIntentCopy", () => {
  it("explains that openmc-sph conversion consumes an SPH-applied handoff", () => {
    const copy = convertIntentCopy("openmc-sph");

    expect(copy.title).toBe("Convert an SPH-applied handoff");
    expect(copy.body).toContain("does not recompute SPH");
    expect(copy.body).toContain("apply-sph");
    expect(copy.commandLabel).toBe("apply-sph");
    expect(copy.tone).toBe("sph");
  });
});

describe("convertIntentBannerVisible", () => {
  it("suppresses the header-duplicating generic and direct-convert banners", () => {
    expect(convertIntentBannerVisible("generic")).toBe(false);
    expect(convertIntentBannerVisible("direct-convert")).toBe(false);
  });

  it("keeps the deep-link guidance banners for check and openmc-sph", () => {
    expect(convertIntentBannerVisible("check")).toBe(true);
    expect(convertIntentBannerVisible("openmc-sph")).toBe(true);
  });
});
