/**
 * Single source of truth for the converter's check level.
 *
 * The form exposes one segmented control ("Checks: Production / Standard /
 * None") instead of independent check/production toggles; these helpers map
 * that level onto the two CLI flags. The production contract is the default —
 * URL params still override it, so demo and SPH deep links keep working.
 */

export type ConvertChecksLevel = "production" | "standard" | "none";

export const CONVERT_CHECKS_LEVELS: readonly ConvertChecksLevel[] = [
  "production",
  "standard",
  "none",
];

/** Form defaults: production checks on unless a URL param overrides them. */
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
    return "Production checks (--production): strict acceptance preset on top of Preflight (--check).";
  }
  if (level === "standard") {
    return "Preflight (--check): HDF5 contract and quick physics consistency before writing.";
  }
  return "No preflight before writing; a dry run plus production checks is the safer way to hand off.";
}
