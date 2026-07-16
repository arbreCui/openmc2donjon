import { describe, expect, it } from "vitest";
import { HOME_FLOW, HOME_HERO } from "./homeHero";

describe("home hero", () => {
  it("leads with the concrete Converter product", () => {
    expect(HOME_HERO.kicker).toBe("OpenMC → DRAGON / DONJON handoff");
    expect(HOME_HERO.heading).toBe(
      "Convert OpenMC MGXS into a traceable DRAGON/DONJON object.",
    );
    expect(HOME_HERO.paragraph).toContain("L_MULTICOMPO or L_MACROLIB");
    expect(HOME_HERO.paragraph).toContain("hash-linked receipt");
  });

  it("shows Converter as the required boundary before optional native SPH", () => {
    expect(HOME_FLOW.map((stage) => stage.label)).toEqual([
      "MGXS HDF5",
      "Converter",
      "L_MULTICOMPO / L_MACROLIB",
      "SPH · Project · DONJON",
    ]);
    expect(HOME_FLOW[1].qualifier).toContain("required");
    expect(HOME_FLOW[0].qualifier).toContain("prepare with OpenMC");
    expect(HOME_FLOW[3].qualifier).toContain("optional");
  });

  it("places Converter at the center without erasing SPH or projects", () => {
    expect(HOME_HERO.paragraph).toContain("required handoff boundary");
    expect(HOME_HERO.supporting).toContain("native DRAGON SPH");
    expect(HOME_HERO.supporting).toContain(
      "multi-component or repeated workflows in Project",
    );
    expect(HOME_HERO.supporting).toContain("downstream DONJON calculations");
    expect(HOME_HERO.supporting).toContain("PyGan/LCM is optional");
  });
});
