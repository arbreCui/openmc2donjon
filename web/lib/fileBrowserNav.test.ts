import { describe, expect, it } from "vitest";
import { requestedPathParent } from "./fileBrowserNav";

describe("requestedPathParent", () => {
  it("derives the parent of a failed listing's requested path", () => {
    // Regression: after a 404 listing, ↑ parent and the breadcrumb were
    // dead because navigation only derived from the last successful
    // listing.
    expect(requestedPathParent("/mock/home/openmc-runs/nope")).toBe(
      "/mock/home/openmc-runs",
    );
    expect(requestedPathParent("/runs/case/missing")).toBe("/runs/case");
    expect(requestedPathParent("/a")).toBe("/");
  });

  it("returns null at roots that have nothing above them", () => {
    expect(requestedPathParent("/")).toBeNull();
    // The mock tree is rooted at /mock/home; there is no listable /mock.
    expect(requestedPathParent("/mock/home")).toBeNull();
    expect(requestedPathParent("~")).toBeNull();
  });
});
