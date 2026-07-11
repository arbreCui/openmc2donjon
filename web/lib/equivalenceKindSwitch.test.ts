import { describe, expect, it } from "vitest";
import { defaultEquivalenceOptions } from "./equivalenceCommand";
import { equivalenceOptionsForKindSwitch } from "./equivalenceKindSwitch";

describe("equivalenceOptionsForKindSwitch", () => {
  it("resets per-kind fields to the new kind's defaults", () => {
    // Regression: switching tabs kept the previous tool's output
    // filename, mode/clip fields, summary JSON, and Force overwrite, so
    // the CLI preview targeted the wrong artifact.
    const edited = {
      ...defaultEquivalenceOptions("adf-sidecar"),
      inputH5: "/runs/case/mgxs.h5",
      outputPath: "/runs/case/adf_sidecar.h5",
      adfMode: "flux-ratio" as const,
      clipMin: "0.5",
      summaryJson: "adf.json",
      force: true,
    };

    const switched = equivalenceOptionsForKindSwitch(edited, "augment-sph");

    expect(switched).toEqual({
      ...defaultEquivalenceOptions("augment-sph"),
      inputH5: "/runs/case/mgxs.h5",
    });
    expect(switched.outputPath).toBe("mgxs_with_sph.h5");
    expect(switched.force).toBe(false);
    expect(switched.summaryJson).toBe("");
  });

  it("preserves the shared input path", () => {
    const edited = {
      ...defaultEquivalenceOptions("sph-sidecar"),
      inputH5: "/runs/case/mgxs.h5",
    };
    expect(
      equivalenceOptionsForKindSwitch(edited, "openmc-sph-sidecar").inputH5,
    ).toBe("/runs/case/mgxs.h5");
  });
});
