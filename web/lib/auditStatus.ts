import type { SphLoopSummary } from "./api";

export type AuditTone = "pass" | "fail" | "warn" | "neutral";

export interface AuditStatus {
  value: string;
  tone: AuditTone;
  detail: string;
}

export function isPassDecision(decision: string): boolean {
  return decision === "openmc2donjon_sph_loop_passed";
}

export function shortDecision(decision: string): string {
  return decision
    .replace(/^openmc2donjon_sph_loop_/, "")
    .replaceAll("_", " ");
}

export function summarizeChecks(
  checks: { passed: boolean }[],
): { failed: number; total: number } {
  const failed = checks.filter((check) => !check.passed).length;
  return { failed, total: checks.length };
}

export function gateStatus(
  enabled: boolean,
  passed: boolean,
  counts: { failed: number; total: number },
): AuditStatus {
  if (!enabled) {
    return { value: "disabled", tone: "neutral", detail: "not evaluated" };
  }
  return {
    value: passed ? "pass" : "fail",
    tone: passed ? "pass" : "fail",
    detail: `${counts.failed} / ${counts.total} failed`,
  };
}

export function convergenceStatus(data: SphLoopSummary): AuditStatus {
  if (!data.convergence_enabled) {
    return { value: "disabled", tone: "neutral", detail: "not evaluated" };
  }
  return {
    value: data.converged ? "reached" : "not reached",
    tone: data.converged ? "pass" : "warn",
    detail: convergenceDetail(data),
  };
}

export function shouldShowAcceptedUnconverged(data: SphLoopSummary): boolean {
  return (
    data.acceptance.enabled &&
    data.acceptance.passed &&
    convergenceStatus(data).tone === "warn"
  );
}

function convergenceDetail(data: SphLoopSummary): string {
  const fluxTarget =
    data.flux_ratio_tolerance == null
      ? null
      : `flux target ${formatNumber(data.flux_ratio_tolerance)}`;
  const sphTarget =
    data.sph_change_tolerance == null
      ? null
      : `SPH target ${formatNumber(data.sph_change_tolerance)}`;
  return (
    [fluxTarget, sphTarget, data.stop_reason || null].filter(Boolean).join(" · ") ||
    "no target recorded"
  );
}

export function formatNumber(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e-3 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}
