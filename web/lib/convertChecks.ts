/**
 * Single source of truth for the converter's check level.
 *
 * The form exposes one segmented control ("Checks: Production / Standard /
 * None") instead of independent check/production toggles; these helpers map
 * that level onto the two CLI flags. Production is the default because the
 * Converter is the formal OpenMC-to-DRAGON/DONJON handoff boundary. Standard
 * remains available as an explicitly non-production engineering preflight.
 */

export type ConvertChecksLevel = "production" | "standard" | "none";

export const CONVERT_CHECKS_LEVELS: readonly ConvertChecksLevel[] = [
  "production",
  "standard",
  "none",
];

/** Form defaults: formal production validation unless a URL param overrides it. */
export const CONVERT_CHECKS_DEFAULTS = {
  check: true,
  production: true,
} as const;

export function convertChecksLevel(
  check: boolean,
  production: boolean,
): ConvertChecksLevel {
  if (production) return "production";
  if (check) return "standard";
  return "none";
}

export function convertChecksFlags(level: ConvertChecksLevel): {
  check: boolean;
  production: boolean;
} {
  if (level === "production") return { check: true, production: true };
  if (level === "standard") return { check: true, production: false };
  return { check: false, production: false };
}

export function convertChecksLevelLabel(level: ConvertChecksLevel): string {
  if (level === "production") return "Production";
  if (level === "standard") return "Standard";
  return "None";
}

/** One label per flag, flag shown. */
export function convertChecksLevelDescription(
  level: ConvertChecksLevel,
): string {
  if (level === "production") {
    return "Formal handoff gate (--check --production): strict contract, provenance, and physics checks before writing.";
  }
  if (level === "standard") {
    return "Engineering preflight only (--check): useful during development, but it is not production acceptance.";
  }
  return "No contract preflight before writing. Use only for diagnostics; this output is not production accepted.";
}
