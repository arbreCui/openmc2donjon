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
  return runKind === "idle";
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
        "Preflight runs hard physics checks before writing: row balance, chi normalization, ADF face consistency, transport/P1 consistency, and audit warnings.",
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
      title: "ADF / SPH carry-through",
      badge: "detected after dry run",
      body:
        "If the source HDF5 already carries ADF/DF or NSPH sidecar data — a sidecar is a small companion HDF5 carrying ADF/DF or SPH factors — the converter carries those blocks into the DONJON output.",
      tone: "neutral",
    };
  }

  const adfMixtures = input.adf_mixtures ?? 0;
  const adfFaces = input.adf_faces?.length ?? 0;
  const sph = input.sph_calculations ?? 0;
  if (adfMixtures > 0 && adfFaces > 0 && sph > 0) {
    return {
      id: "equivalence",
      title: "ADF / SPH carry-through",
      badge: `${adfMixtures} ADF mix · ${sph} SPH`,
      body: `Carries ADF/DF over ${adfFaces} face type(s) and ${sph} NSPH calculation record(s) from the source handoff.`,
      tone: "pass",
    };
  }
  if (adfMixtures > 0 && adfFaces > 0) {
    return {
      id: "equivalence",
      title: "ADF carry-through",
      badge: `${adfMixtures} mix · ${adfFaces} face type(s)`,
      body:
        "Carries ADF/DF data from the source HDF5. No NSPH calculation records were reported by preflight.",
      tone: "pass",
    };
  }
  if (sph > 0) {
    return {
      id: "equivalence",
      title: "SPH carry-through",
      badge: `${sph} calculation record(s)`,
      body:
        "Carries NSPH equivalence factors from the source HDF5. No ADF/DF face data was reported by preflight.",
      tone: "pass",
    };
  }
  return {
    id: "equivalence",
    title: "Equivalence data",
    badge: "direct XS only",
    body:
      "No ADF/DF or NSPH records were reported by the current preflight. Use the sidecar builders before conversion if equivalence factors are needed.",
    tone: "warn",
  };
}

function momentLabel(input: ConvertPreflightInput): string {
  if (input.legendre_order == null) return "? moments";
  return `P0-P${input.legendre_order}`;
}

function value(item: number | null | undefined): string {
  return item == null ? "?" : String(item);
}
