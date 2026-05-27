export type ConvertIntent =
  | "direct-convert"
  | "check"
  | "openmc-sph"
  | "generic";

export interface ConvertIntentCopy {
  intent: ConvertIntent;
  eyebrow: string;
  title: string;
  body: string;
  commandHref: string | null;
  commandLabel: string | null;
  tone: "neutral" | "accent" | "production" | "sph";
}

const COPIES: Record<ConvertIntent, ConvertIntentCopy> = {
  "direct-convert": {
    intent: "direct-convert",
    eyebrow: "Command workflow",
    title: "Direct conversion",
    body:
      "Convert an existing OpenMC MGXS HDF5 handoff into DONJON ASCII. Start with Dry run, then write the artifact once the checks look right.",
    commandHref: "/commands/direct-convert",
    commandLabel: "direct-convert",
    tone: "accent",
  },
  check: {
    intent: "check",
    eyebrow: "Production QA",
    title: "Production preflight",
    body:
      "Use the converter page as a no-write production check. Dry run checks the HDF5 contract, mesh identity, physics balances, equivalence layout, and output target.",
    commandHref: "/commands/check",
    commandLabel: "check",
    tone: "production",
  },
  "openmc-sph": {
    intent: "openmc-sph",
    eyebrow: "OpenMC-side SPH",
    title: "Convert a corrected SPH handoff",
    body:
      "Use this after OpenMC CE/MG equivalence has produced SPH factors and they have been injected into the HDF5 handoff. For DONJON SPH consumption, choose MACROLIB so NSPH is written as GROUP/*/NSPH.",
    commandHref: "/commands/augment-sph",
    commandLabel: "augment-sph",
    tone: "sph",
  },
  generic: {
    intent: "generic",
    eyebrow: "Converter",
    title: "MGXS HDF5 to DONJON ASCII",
    body:
      "Choose an OpenMC MGXS HDF5 handoff, inspect the planned command, dry-run the checks, and write L_MULTICOMPO or L_MACROLIB ASCII.",
    commandHref: null,
    commandLabel: null,
    tone: "neutral",
  },
};

export function parseConvertIntent(value: string | null): ConvertIntent {
  if (value === "direct-convert" || value === "check" || value === "openmc-sph") {
    return value;
  }
  return "generic";
}

export function convertIntentCopy(value: string | null): ConvertIntentCopy {
  return COPIES[parseConvertIntent(value)];
}
