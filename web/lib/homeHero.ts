export interface HomeHero {
  kicker: string;
  heading: string;
  paragraph: string;
}

export const HOME_HERO: HomeHero = {
  kicker: "Monte Carlo lattice physics for DONJON",
  heading: "Monte Carlo cross sections for DONJON core calculations",
  paragraph:
    "Take an OpenMC MGXS handoff, check it against the production contract, and write the L_MULTICOMPO or L_MACROLIB library DONJON consumes — with SPH equivalence prepared upstream from paired OpenMC fine/coarse models when it is needed. The converter serializes homogenized data and equivalence factors; it does not solve reactor physics.",
} as const;
