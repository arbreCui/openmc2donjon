import { describe, expect, it } from "vitest";
import { convertIntentBannerVisible, convertIntentCopy } from "./convertIntent";

describe("convertIntentCopy", () => {
  it("explains that openmc-sph conversion consumes an SPH-augmented handoff", () => {
    const copy = convertIntentCopy("openmc-sph");

    expect(copy.title).toBe("Convert an SPH-augmented handoff");
    expect(copy.body).toContain("does not recompute SPH");
    expect(copy.body).toContain("SPH-augmented HDF5");
    expect(copy.body).toContain("GROUP/*/NSPH");
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
