import { describe, expect, it } from "vitest";
import {
  isAnyNavItemActive,
  isNavItemActive,
  PRIMARY_NAV_ITEMS,
  SECONDARY_NAV_ITEMS,
} from "./navigation";

describe("navigation", () => {
  it("keeps the top-level bar focused on the main workflow", () => {
    expect(PRIMARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Home",
      "Convert",
      "OpenMC workflow",
      "Inspect",
      "Commands",
    ]);
    expect(SECONDARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "ADF/SPH sidecars",
      "Bundle handoff",
      "DONJON cards",
      "PyGan option",
      "Settings",
    ]);
  });

  it("matches nested command detail routes to Commands", () => {
    const commands = PRIMARY_NAV_ITEMS.find((item) => item.label === "Commands");
    expect(commands).toBeDefined();
    expect(isNavItemActive(commands!, "/commands/direct-convert")).toBe(true);
  });

  it("does not mark Home active for every path", () => {
    const home = PRIMARY_NAV_ITEMS[0];
    expect(isNavItemActive(home, "/")).toBe(true);
    expect(isNavItemActive(home, "/convert")).toBe(false);
  });

  it("marks More active when a secondary route is selected", () => {
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/pygan")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/builder")).toBe(true);
    expect(isAnyNavItemActive(SECONDARY_NAV_ITEMS, "/convert")).toBe(false);
  });
});
