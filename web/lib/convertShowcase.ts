import type { ConvertFormat, ConvertPreflightInput } from "./api";

export interface ConvertShowcaseFact {
  id: "object" | "payload" | "gates" | "equivalence";
  title: string;
  badge: string;
  body: string;
  tone: "neutral" | "accent" | "pass" | "warn";
}

export interface ConvertShowcaseOptions {
  format: ConvertFormat;
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
  input: ConvertPreflightInput | null;
}

export type ConvertShowcaseRunKind = "idle" | "loading" | "ok" | "error";

export function convertShowcaseFacts({
  format,
  check,
  production,
  requireKnownMesh,
  input,
}: ConvertShowcaseOptions): readonly ConvertShowcaseFact[] {
  return [
    outputObjectFact(format),
    payloadFact(input),
    gateFact({ check, production, requireKnownMesh }),
    equivalenceFact(input),
  ] as const;
}

export function convertShowcaseObjectLabel(format: ConvertFormat): string {
  return format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
}

export function convertShowcaseDefaultOpen(
  runKind: ConvertShowcaseRunKind,
): boolean {
  void runKind;
  return false;
}

function outputObjectFact(format: ConvertFormat): ConvertShowcaseFact {
  if (format === "macrolib") {
    return {
      id: "object",
      title: "Output object",
      badge: "one-state macrolib",
      body:
        "Writes a compact L_MACROLIB for direct deterministic consumption when no multicompo mapping is needed.",
      tone: "accent",
    };
  }
  return {
    id: "object",
    title: "Output object",
    badge: "mapped domain library",
    body:
      "Writes L_MULTICOMPO so DONJON sees exported OpenMC domains as ordered mixture slots with calculation records.",
    tone: "accent",
  };
}

function payloadFact(input: ConvertPreflightInput | null): ConvertShowcaseFact {
  const badge =
    input == null
      ? "counts after dry run"
      : `${value(input.mixtures)} mix · ${value(input.energy_groups)} g · ${momentLabel(input)}`;
  return {
    id: "payload",
    title: "Macroscopic payload",
    badge,
    body:
      "Carries total, transport/diffusion, absorption and fission data, chi, volumes, energy bounds, and sparse Legendre scattering.",
    tone: input == null ? "neutral" : "pass",
  };
}

function gateFact({
  check,
  production,
  requireKnownMesh,
}: Pick<
  ConvertShowcaseOptions,
  "check" | "production" | "requireKnownMesh"
>): ConvertShowcaseFact {
  if (production) {
    return {
      id: "gates",
      title: "Production checks (--production)",
      badge: requireKnownMesh ? "strict mesh + production" : "production preset",
      body:
        "Preflight runs hard physics checks before writing: row balance, chi normalization, equivalence-record layout, transport/P1 consistency, and audit warnings.",
      tone: "pass",
    };
  }
  if (check) {
    return {
      id: "gates",
      title: "Preflight (--check)",
      badge: requireKnownMesh ? "standard + known mesh" : "standard checks",
      body:
        "Preflight checks the HDF5 contract and key consistency rules. Enable production checks for stricter handoff acceptance.",
      tone: "neutral",
    };
  }
  return {
    id: "gates",
    title: "Checks off",
    badge: "none",
    body:
      "Conversion can run with no preflight, but a dry run plus production checks is the safer way to hand off.",
    tone: "warn",
  };
}

function equivalenceFact(input: ConvertPreflightInput | null): ConvertShowcaseFact {
  if (input == null) {
    return {
      id: "equivalence",
      title: "Optional equivalence data",
      badge: "reported after dry run",
      body:
        "Converter reports SPH or other equivalence provenance when it is present. A normal conversion does not require SPH unless the selected physics contract says so.",
      tone: "neutral",
    };
  }

  const sph = input.sph_calculations ?? 0;
  if (input.sph_applied) {
    return {
      id: "equivalence",
      title: "SPH already applied",
      badge: input.sph_kind?.trim() || "XS divided by NSPH",
      body:
        "apply-sph provenance is present. Converter writes the already corrected cross sections; DONJON does not need to consume NSPH records separately.",
      tone: "pass",
    };
  }
  if (sph > 0) {
    return {
      id: "equivalence",
      title: "SPH records attached",
      badge: `${sph} calculation record(s)`,
      body:
        "Carries attached NSPH equivalence records into a compatible DONJON object; cross sections in this HDF5 have not been rewritten.",
      tone: "pass",
    };
  }
  return {
    id: "equivalence",
    title: "No SPH records",
    badge: "direct cross sections",
    body:
      "The HDF5 contains no NSPH records. This is valid for direct-conversion routes that do not declare SPH as a required physics contract.",
    tone: "neutral",
  };
}

function momentLabel(input: ConvertPreflightInput): string {
  if (input.legendre_order == null) return "? moments";
  return `P0-P${input.legendre_order}`;
}

function value(item: number | null | undefined): string {
  return item == null ? "?" : String(item);
}
