import { describe, expect, it } from "vitest";
import {
  isAnyNavItemActive,
  isNavItemActive,
  PRIMARY_NAV_ITEMS,
  SECONDARY_NAV_ITEMS,
} from "./navigation";

describe("navigation", () => {
  it("keeps the top-level bar reading as the pipeline: prep, convert, inspect, DONJON", () => {
    expect(PRIMARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Convert",
      "OpenMC prep",
      "Inspect HDF5",
      "DONJON",
    ]);
    expect(SECONDARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Commands",
      "Command builder",
      "SPH/ADF sidecars",
      "PyGan validation",
      "Settings",
    ]);
  });

  it("lands OpenMC prep on export planning with production checks kept", () => {
    const openmc = PRIMARY_NAV_ITEMS.find((item) => item.label === "OpenMC prep");
    expect(openmc).toBeDefined();
    expect(openmc!.href).toBe("/openmc?workflow=two-step&production=1");
    expect(openmc!.href).not.toContain("equivalence=sph");
  });

  it("promotes DONJON to primary with its consumption description", () => {
    const donjon = PRIMARY_NAV_ITEMS.find((item) => item.label === "DONJON");
    expect(donjon).toBeDefined();
    expect(donjon!.href).toBe("/donjon");
    expect(donjon!.description).toBe(
      "Generate the DONJON deck that consumes your ASCII.",
    );
  });

  it("names the one thing Settings does", () => {
    const settings = SECONDARY_NAV_ITEMS.find(
      (item) => item.label === "Settings",
    );
    expect(settings).toBeDefined();
    expect(settings!.description).toBe(
      "Default path prefix for path inputs and the file browser.",
    );
  });

  it("matches nested command detail routes to Commands", () => {
    const commands = SECONDARY_NAV_ITEMS.find(
      (item) => item.label === "Commands",
    );
    expect(commands).toBeDefined();
    expect(isNavItemActive(commands!, "/commands/direct-convert")).toBe(true);
  });

  it("does not mark Convert active for unrelated paths", () => {
    const convert = PRIMARY_NAV_ITEMS[0];
    expect(isNavItemActive(convert, "/convert")).toBe(true);
    expect(isNavItemActive(convert, "/inspect")).toBe(false);
  });

  it("keeps Command builder anchoring every /builder page after Bundle's row was dropped", () => {
    const builder = SECONDARY_NAV_ITEMS.find(
      (item) => item.label === "Command builder",
    );
    expect(builder).toBeDefined();
    expect(builder!.match).toEqual(["/builder"]);
    expect(isNavItemActive(builder!, "/builder")).toBe(true);
  });

  it("marks More active when a secondary route is selected", () => {
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/pygan")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/builder")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/commands")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/convert")).toBe(false);
  });
});
