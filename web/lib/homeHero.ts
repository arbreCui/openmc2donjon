export interface HomeHero {
  kicker: string;
  heading: string;
  paragraph: string;
  supporting: string;
}

export const HOME_FLOW = [
  { label: "MGXS HDF5", qualifier: "bring one or prepare with OpenMC" },
  { label: "Converter", qualifier: "required handoff boundary" },
  { label: "L_MULTICOMPO / L_MACROLIB", qualifier: "object + receipt" },
  { label: "SPH · Project · DONJON", qualifier: "optional model-specific work" },
] as const;

export const HOME_HERO: HomeHero = {
  kicker: "OpenMC → DRAGON / DONJON handoff",
  heading: "Convert OpenMC MGXS into a traceable DRAGON/DONJON object.",
  paragraph:
    "Converter is the required handoff boundary. It checks a declared MGXS HDF5 and its mapping, then writes an L_MULTICOMPO or L_MACROLIB object with a hash-linked receipt.",
  supporting:
    "Bring an existing handoff or prepare one with OpenMC. When needed, solve native DRAGON SPH on a declared coarse model, coordinate multi-component or repeated workflows in Project, and run downstream DONJON calculations. Built-in ASCII is the default writer; PyGan/LCM is optional.",
} as const;
