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

  it("seeds the ADF source when switching from make to its augment sibling", () => {
    // Regression: the make->augment handoff forced hand-copying the
    // output path configured thirty seconds earlier on the make tab.
    const edited = {
      ...defaultEquivalenceOptions("adf-sidecar"),
      inputH5: "/runs/case/mgxs.h5",
      outputPath: "/runs/case/adf_sidecar.h5",
    };

    const switched = equivalenceOptionsForKindSwitch(edited, "augment-adf");

    expect(switched.adfSource).toBe("/runs/case/adf_sidecar.h5");
    expect(switched.inputH5).toBe("/runs/case/mgxs.h5");
    expect(switched.outputPath).toBe("mgxs_with_adf.h5");
  });

  it("seeds the SPH source from either SPH make kind", () => {
    const fromOpenmc = equivalenceOptionsForKindSwitch(
      {
        ...defaultEquivalenceOptions("openmc-sph-sidecar"),
        outputPath: "/runs/case/openmc_sph.h5",
      },
      "augment-sph",
    );
    expect(fromOpenmc.sphSource).toBe("/runs/case/openmc_sph.h5");

    const toApply = equivalenceOptionsForKindSwitch(
      {
        ...defaultEquivalenceOptions("openmc-sph-sidecar"),
        outputPath: "/runs/case/openmc_sph.h5",
      },
      "apply-sph",
    );
    expect(toApply.sphSource).toBe("/runs/case/openmc_sph.h5");
    expect(toApply.outputPath).toBe("mgxs_sph_applied.h5");

    const fromGeneric = equivalenceOptionsForKindSwitch(
      {
        ...defaultEquivalenceOptions("sph-sidecar"),
        outputPath: "/runs/case/sph_sidecar.h5",
      },
      "augment-sph",
    );
    expect(fromGeneric.sphSource).toBe("/runs/case/sph_sidecar.h5");
  });

  it("does not seed a sidecar source across make/augment families", () => {
    // An ADF sidecar output must never become an SPH source (and vice
    // versa); only the matching augment sibling is seeded.
    const adfToSph = equivalenceOptionsForKindSwitch(
      {
        ...defaultEquivalenceOptions("adf-sidecar"),
        outputPath: "/runs/case/adf_sidecar.h5",
      },
      "augment-sph",
    );
    expect(adfToSph.sphSource).toBe("");
    expect(adfToSph.adfSource).toBe("");

    const sphToAdf = equivalenceOptionsForKindSwitch(
      {
        ...defaultEquivalenceOptions("openmc-sph-sidecar"),
        outputPath: "/runs/case/openmc_sph.h5",
      },
      "augment-adf",
    );
    expect(sphToAdf.adfSource).toBe("");
    expect(sphToAdf.sphSource).toBe("");
  });

  it("leaves the sidecar source empty when the make output is blank", () => {
    const switched = equivalenceOptionsForKindSwitch(
      { ...defaultEquivalenceOptions("adf-sidecar"), outputPath: "   " },
      "augment-adf",
    );
    expect(switched.adfSource).toBe("");
  });
});
