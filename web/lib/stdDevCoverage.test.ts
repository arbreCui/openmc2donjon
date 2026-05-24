import { describe, expect, it } from "vitest";
import { summarizeStdDevCoverage } from "./stdDevCoverage";

describe("std_dev coverage summary", () => {
  it("marks full coverage as complete", () => {
    expect(
      summarizeStdDevCoverage({
        mgxs_std_dev_datasets: 8,
        mgxs_std_dev_expected_datasets: 8,
      }),
    ).toMatchObject({
      status: "complete",
      tone: "pass",
      countLabel: "8 / 8",
      percentLabel: "100%",
      missing: 0,
    });
  });

  it("marks partial coverage as incomplete", () => {
    expect(
      summarizeStdDevCoverage({
        mgxs_std_dev_datasets: 2,
        mgxs_std_dev_expected_datasets: 5,
      }),
    ).toMatchObject({
      status: "incomplete",
      tone: "warn",
      countLabel: "2 / 5",
      percentLabel: "40%",
      missing: 3,
    });
  });

  it("keeps older summaries readable when counters are absent", () => {
    expect(summarizeStdDevCoverage({})).toMatchObject({
      status: "not-recorded",
      tone: "neutral",
      countLabel: "—",
      percentLabel: "—",
    });
  });

  it("handles summaries with no eligible datasets", () => {
    expect(
      summarizeStdDevCoverage({
        mgxs_std_dev_datasets: 0,
        mgxs_std_dev_expected_datasets: 0,
      }),
    ).toMatchObject({
      status: "none-expected",
      tone: "neutral",
      countLabel: "0 / 0",
      percentLabel: "—",
    });
  });
});
