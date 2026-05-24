import { describe, expect, it } from "vitest";
import { summarizeReferenceFluxUncertainty } from "./referenceFluxUncertainty";

describe("reference flux uncertainty summary", () => {
  it("marks present reference-flux std_dev metadata as a pass", () => {
    expect(
      summarizeReferenceFluxUncertainty(
        {
          std_dev_dataset: "openmc_volume_flux_std_dev",
          std_dev_max_rel: 1.0e-3,
          std_dev_worst: "mixture=FUEL g=2",
        },
        [
          {
            name: "require_reference_flux_std_dev",
            passed: true,
            actual: true,
            limit: true,
            units: null,
            message: "reference flux std_dev present",
          },
          {
            name: "max_reference_flux_std_dev_rel",
            passed: true,
            actual: 1.0e-3,
            limit: 1.0e-2,
            units: "relative",
            message: "actual <= limit",
          },
        ],
      ),
    ).toMatchObject({
      status: "present",
      tone: "pass",
      badge: "gate pass",
      datasetLabel: "openmc_volume_flux_std_dev",
      maxRelLabel: "0.001000",
      gateLabel: "2/2 pass",
    });
  });

  it("warns when reference metadata exists but no std_dev dataset is recorded", () => {
    expect(summarizeReferenceFluxUncertainty({ std_dev_dataset: null })).toMatchObject({
      status: "missing",
      tone: "warn",
      badge: "missing",
      datasetLabel: "missing",
      gateLabel: "not required",
    });
  });

  it("marks failed reference-flux gates as fail", () => {
    expect(
      summarizeReferenceFluxUncertainty(
        { std_dev_dataset: null },
        [
          {
            name: "require_reference_flux_std_dev",
            passed: false,
            actual: false,
            limit: true,
            units: null,
            message: "reference flux std_dev missing",
          },
        ],
      ),
    ).toMatchObject({
      status: "missing",
      tone: "fail",
      badge: "gate fail",
      gateLabel: "1/1 fail",
      detail: "reference flux std_dev missing",
    });
  });

  it("keeps older summaries readable when reference metadata is absent", () => {
    expect(summarizeReferenceFluxUncertainty(null)).toMatchObject({
      status: "not-recorded",
      tone: "neutral",
      badge: "not recorded",
      datasetLabel: "—",
    });
  });
});
