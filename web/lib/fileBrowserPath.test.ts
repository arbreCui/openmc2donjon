import { describe, expect, it } from "vitest";
import { pathCrumbs } from "./fileBrowserPath";

describe("pathCrumbs", () => {
  it("emits a single root crumb for '/'", () => {
    expect(pathCrumbs("/")).toEqual([{ label: "/", path: "/" }]);
  });

  it("walks an absolute path and accumulates click targets", () => {
    expect(pathCrumbs("/Users/wen/run")).toEqual([
      { label: "/", path: "/" },
      { label: "Users", path: "/Users" },
      { label: "wen", path: "/Users/wen" },
      { label: "run", path: "/Users/wen/run" },
    ]);
  });

  it("collapses the /mock/home scaffolding into a 'home' crumb", () => {
    expect(pathCrumbs("/mock/home/openmc-runs/c5g7")).toEqual([
      { label: "home", path: "/mock/home" },
      { label: "openmc-runs", path: "/mock/home/openmc-runs" },
      { label: "c5g7", path: "/mock/home/openmc-runs/c5g7" },
    ]);
  });

  it("falls back to a single crumb for non-absolute inputs", () => {
    // ``~`` shouldn't normally reach the breadcrumb (the backend
    // resolves it before sending the listing back), but a render-time
    // crash here would be far worse than an honest single-crumb
    // fallback.
    expect(pathCrumbs("~")).toEqual([{ label: "~", path: "~" }]);
  });
});
