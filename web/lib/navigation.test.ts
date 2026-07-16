import { describe, expect, it } from "vitest";
import {
  isAnyNavItemActive,
  isNavItemActive,
  PRIMARY_NAV_ITEMS,
  SECONDARY_NAV_ITEMS,
  WORKFLOW_NAV_ITEMS,
} from "./navigation";

describe("navigation", () => {
  it("keeps the four common entry points visible", () => {
    expect(PRIMARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Converter",
      "Inspect",
      "Projects",
      "Documentation",
    ]);
    expect(PRIMARY_NAV_ITEMS.every((item) => item.step == null)).toBe(true);
    expect(PRIMARY_NAV_ITEMS.find((item) => item.label === "Converter")?.href).toBe("/convert");
    expect(PRIMARY_NAV_ITEMS[0].href).toBe("/convert");
    expect(PRIMARY_NAV_ITEMS.find((item) => item.label === "Documentation")?.href).toBe("/docs");
  });

  it("keeps model-specific workflows available without crowding the header", () => {
    expect(WORKFLOW_NAV_ITEMS.map((item) => item.label)).toEqual([
      "OpenMC MGXS",
      "SPH",
      "DONJON",
    ]);
    expect(WORKFLOW_NAV_ITEMS.find((item) => item.label === "DONJON")?.description).toContain("user-defined");
  });

  it("keeps secondary tools stable", () => {
    expect(SECONDARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Commands", "Command builder", "PyGan writer", "Settings",
    ]);
    const settings = SECONDARY_NAV_ITEMS.find((item) => item.label === "Settings")!;
    expect(settings.description).toBe("Default path prefix for path inputs and the file browser.");
  });

  it("matches each generic workflow surface independently", () => {
    expect(isNavItemActive(WORKFLOW_NAV_ITEMS.find((item) => item.label === "OpenMC MGXS")!, "/openmc")).toBe(true);
    expect(isNavItemActive(WORKFLOW_NAV_ITEMS.find((item) => item.label === "SPH")!, "/equivalence")).toBe(true);
    expect(isNavItemActive(PRIMARY_NAV_ITEMS.find((item) => item.label === "Inspect")!, "/inspect")).toBe(true);
    expect(isNavItemActive(PRIMARY_NAV_ITEMS.find((item) => item.label === "Converter")!, "/inspect")).toBe(false);
  });

  it("matches nested and secondary routes", () => {
    const commands = SECONDARY_NAV_ITEMS.find((item) => item.label === "Commands")!;
    expect(isNavItemActive(commands, "/commands/direct-convert")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/pygan")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/convert")).toBe(false);
    expect(isAnyNavItemActive(WORKFLOW_NAV_ITEMS, "/donjon")).toBe(true);
  });
});
