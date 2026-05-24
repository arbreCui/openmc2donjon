import type { SphLoopAcceptanceCheck } from "./api";

export function filterAuditChecks(
  checks: SphLoopAcceptanceCheck[],
  query: string,
): SphLoopAcceptanceCheck[] {
  const terms = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  if (terms.length === 0) return checks;
  return checks.filter((check) => {
    const haystack = auditCheckSearchText(check);
    return terms.every((term) => haystack.includes(term));
  });
}

function auditCheckSearchText(check: SphLoopAcceptanceCheck): string {
  return [
    check.passed ? "pass passed" : "fail failed",
    check.name,
    check.message,
    check.units,
    formatSearchValue(check.actual),
    formatSearchValue(check.limit),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function formatSearchValue(value: SphLoopAcceptanceCheck["actual"]): string {
  if (value == null) return "";
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "";
  }
  return String(value);
}
