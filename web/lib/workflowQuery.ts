import type {
  ConvertFormat,
  OpenmcEquivalenceMode,
  OpenmcWorkflowKind,
} from "./api";
import type { ConvertIntent } from "./convertIntent";

export interface QueryParams {
  get(key: string): string | null;
}

export function queryFlag(
  params: QueryParams,
  key: string,
  fallback: boolean,
): boolean {
  const value = params.get(key);
  if (value == null) return fallback;
  if (["1", "true", "yes", "on"].includes(value.toLowerCase())) return true;
  if (["0", "false", "no", "off"].includes(value.toLowerCase())) return false;
  return fallback;
}

export function parseConvertFormat(value: string | null): ConvertFormat {
  return value === "macrolib" ? "macrolib" : "multicompo";
}

export function parseConvertIntent(value: string | null): ConvertIntent {
  if (value === "direct-convert" || value === "check" || value === "openmc-sph") {
    return value;
  }
  return "generic";
}

export function parseOpenmcWorkflow(value: string | null): OpenmcWorkflowKind {
  return value === "two-step" ? "two-step" : "one-step";
}

export function parseOpenmcEquivalence(
  value: string | null,
): OpenmcEquivalenceMode {
  if (value === "adf" || value === "sph" || value === "flux-ratio-adf") {
    return value;
  }
  return "direct";
}
