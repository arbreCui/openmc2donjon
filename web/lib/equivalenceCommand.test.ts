import { describe, expect, it } from "vitest";
import {
  buildEquivalenceCli,
  defaultEquivalenceOptions,
  parseEquivalenceKind,
} from "./equivalenceCommand";

describe("equivalence command builder", () => {
  it("parses known sidecar kinds with a safe default", () => {
    expect(parseEquivalenceKind("adf-sidecar")).toBe("adf-sidecar");
    expect(parseEquivalenceKind("augment-adf")).toBe("augment-adf");
    expect(parseEquivalenceKind("sph-sidecar")).toBe("sph-sidecar");
    expect(parseEquivalenceKind("augment-sph")).toBe("augment-sph");
    expect(parseEquivalenceKind("bad")).toBe("adf-sidecar");
  });

  it("builds a flux-ratio ADF sidecar command", () => {
    const options = {
      ...defaultEquivalenceOptions("adf-sidecar"),
      inputH5: "/tmp/mgxs.h5",
      outputPath: "/tmp/adf.h5",
      adfMode: "flux-ratio" as const,
      surfaceFlux: "/tmp/het.h5",
      homogeneousFaceFlux: "/tmp/hom.h5",
      invalidFill: "1.0",
      force: true,
    };

    expect(buildEquivalenceCli(options)).toBe(
      "openmc2donjon make-adf-sidecar /tmp/mgxs.h5 -o /tmp/adf.h5 --mode flux-ratio --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX --surface-flux /tmp/het.h5 --homogeneous-face-flux /tmp/hom.h5 --invalid-fill 1.0 --force",
    );
  });

  it("builds an ADF augmentation command", () => {
    const options = {
      ...defaultEquivalenceOptions("augment-adf"),
      inputH5: "/tmp/mgxs.h5",
      outputPath: "/tmp/mgxs adf.h5",
      adfSource: "/tmp/adf.h5",
      faces: "",
    };

    expect(buildEquivalenceCli(options)).toBe(
      "openmc2donjon augment-adf /tmp/mgxs.h5 --adf-source /tmp/adf.h5 -o '/tmp/mgxs adf.h5'",
    );
  });

  it("builds SPH sidecar and augmentation commands", () => {
    expect(
      buildEquivalenceCli({
        ...defaultEquivalenceOptions("sph-sidecar"),
        inputH5: "/tmp/mgxs.h5",
        outputPath: "/tmp/sph.h5",
        sphMode: "table",
        table: "/tmp/sph.csv",
      }),
    ).toContain("--mode table --table /tmp/sph.csv");

    expect(
      buildEquivalenceCli({
        ...defaultEquivalenceOptions("augment-sph"),
        inputH5: "/tmp/mgxs.h5",
        outputPath: "/tmp/mgxs_sph.h5",
        sphSource: "/tmp/sph.h5",
        sphApplied: "false",
      }),
    ).toBe(
      "openmc2donjon augment-sph /tmp/mgxs.h5 --sph-source /tmp/sph.h5 -o /tmp/mgxs_sph.h5 --sph-applied false",
    );
  });
});
