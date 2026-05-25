export type ConvertIntent = "direct-convert" | "check" | "sph-loop" | "generic";

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
  "sph-loop": {
    intent: "sph-loop",
    eyebrow: "SPH feedback loop",
    title: "Reconvert with updated equivalence factors",
    body:
      "In an SPH loop, OpenMC remains the fixed reference. DONJON solves with current factors, the loop updates NSPH, then this conversion step writes the next handoff.",
    commandHref: "/commands/run-sph-loop",
    commandLabel: "run-sph-loop",
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
  if (value === "direct-convert" || value === "check" || value === "sph-loop") {
    return value;
  }
  return "generic";
}

export function convertIntentCopy(value: string | null): ConvertIntentCopy {
  return COPIES[parseConvertIntent(value)];
}
