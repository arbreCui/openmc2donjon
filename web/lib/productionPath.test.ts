import { describe, expect, it } from "vitest";
import { PRODUCTION_PATH_STEPS } from "./productionPath";

describe("production path steps", () => {
  it("keeps the home page path in physical workflow order", () => {
    expect(PRODUCTION_PATH_STEPS.map((step) => step.id)).toEqual([
      "openmc-equivalence",
      "direct-conversion",
      "delivery",
    ]);
  });

  it("links each step to the matching web workflow", () => {
    const [openmc, direct, delivery] = PRODUCTION_PATH_STEPS;
    expect(openmc.href).toBe("/openmc?workflow=two-step&production=1");
    expect(direct.href).toBe(
      "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    );
    expect(delivery.href).toBe("/builder?command=bundle");
  });
});
