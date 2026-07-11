import { describe, expect, it } from "vitest";
import { HOME_HERO } from "./homeHero";

describe("home hero", () => {
  it("leads with the physics-first positioning", () => {
    expect(HOME_HERO.kicker).toBe("Monte Carlo lattice physics for DONJON");
    expect(HOME_HERO.heading).toBe(
      "Monte Carlo cross sections for DONJON core calculations",
    );
  });

  it("keeps the honest-scope statement in the hero paragraph", () => {
    expect(HOME_HERO.paragraph).toContain("OpenMC MGXS handoff");
    expect(HOME_HERO.paragraph).toContain("production contract");
    expect(HOME_HERO.paragraph).toContain(
      "L_MULTICOMPO or L_MACROLIB library DONJON consumes",
    );
    expect(HOME_HERO.paragraph).toContain(
      "SPH/ADF equivalence prepared upstream",
    );
    expect(HOME_HERO.paragraph).toContain(
      "serializes homogenized data and equivalence factors; it does not solve reactor physics.",
    );
  });
});
