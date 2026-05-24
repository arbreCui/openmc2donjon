import type { JsonValue } from "./api";

export type StdDevCoverageStatus =
  | "complete"
  | "incomplete"
  | "none-expected"
  | "not-recorded";

export interface StdDevCoverageSummary {
  status: StdDevCoverageStatus;
  tone: "pass" | "warn" | "neutral";
  present: number | null;
  expected: number | null;
  missing: number | null;
  fraction: number | null;
  badge: string;
  countLabel: string;
  percentLabel: string;
  detail: string;
}

export function summarizeStdDevCoverage(
  fluxMap: Record<string, JsonValue> | null | undefined,
): StdDevCoverageSummary {
  const present = nonnegativeInteger(fluxMap?.mgxs_std_dev_datasets);
  const expected = nonnegativeInteger(fluxMap?.mgxs_std_dev_expected_datasets);

  if (present == null || expected == null) {
    return {
      status: "not-recorded",
      tone: "neutral",
      present: null,
      expected: null,
      missing: null,
      fraction: null,
      badge: "not recorded",
      countLabel: "—",
      percentLabel: "—",
      detail:
        "This summary predates the MGXS std_dev coverage counters, so tally uncertainty coverage was not audited.",
    };
  }

  if (expected === 0) {
    return {
      status: "none-expected",
      tone: "neutral",
      present,
      expected,
      missing: null,
      fraction: null,
      badge: "no eligible XS",
      countLabel: `${present} / ${expected}`,
      percentLabel: "—",
      detail:
        "No eligible MGXS datasets were recorded for std_dev coverage in this summary.",
    };
  }

  const missing = Math.max(0, expected - present);
  const fraction = Math.min(1, present / expected);
  const percentLabel = `${Math.round(fraction * 100)}%`;
  if (missing === 0) {
    return {
      status: "complete",
      tone: "pass",
      present,
      expected,
      missing,
      fraction,
      badge: "complete",
      countLabel: `${present} / ${expected}`,
      percentLabel,
      detail:
        "All eligible MGXS standard-deviation datasets are present in this handoff.",
    };
  }

  return {
    status: "incomplete",
    tone: "warn",
    present,
    expected,
    missing,
    fraction,
    badge: "incomplete",
    countLabel: `${present} / ${expected}`,
    percentLabel,
    detail: `Missing ${missing} eligible MGXS std_dev dataset${missing === 1 ? "" : "s"}. Production can fail this when require_mgxs_std_dev_coverage is enabled.`,
  };
}

function nonnegativeInteger(value: JsonValue | undefined): number | null {
  if (typeof value !== "number") return null;
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.floor(value);
}
