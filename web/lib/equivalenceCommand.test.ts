import { describe, expect, it } from "vitest";
import { COMMAND_BUILDER_SPECS } from "./commandBuilder";
import {
  EQUIVALENCE_KINDS,
  buildEquivalenceCli,
  defaultEquivalenceOptions,
  equivalenceKindInfo,
  parseEquivalenceKind,
} from "./equivalenceCommand";
import { OPENMC_SPH_WORKFLOW_STEPS } from "./openmcSphWorkflow";

describe("equivalence command builder", () => {
  it("parses known sidecar kinds with a safe default", () => {
    expect(parseEquivalenceKind("adf-sidecar")).toBe("adf-sidecar");
    expect(parseEquivalenceKind("augment-adf")).toBe("augment-adf");
    expect(parseEquivalenceKind("openmc-sph-sidecar")).toBe("openmc-sph-sidecar");
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
        ...defaultEquivalenceOptions("openmc-sph-sidecar"),
        inputH5: "/tmp/mgxs.h5",
        outputPath: "/tmp/openmc_sph.h5",
        referenceFlux: "/tmp/ce_flux.h5::openmc_volume_flux",
        mgFlux: "/tmp/mg_flux.h5::openmc_mg_flux",
        tableOutput: "/tmp/openmc_sph.csv",
        damping: "0.5",
      }),
    ).toBe(
      "openmc2donjon make-openmc-sph-sidecar /tmp/mgxs.h5 -o /tmp/openmc_sph.h5 --reference-flux /tmp/ce_flux.h5::openmc_volume_flux --mg-flux /tmp/mg_flux.h5::openmc_mg_flux --table-output /tmp/openmc_sph.csv --damping 0.5 --flux-normalization none",
    );

    expect(
      buildEquivalenceCli({
        ...defaultEquivalenceOptions("openmc-sph-sidecar"),
        inputH5: "/tmp/mgxs.h5",
        outputPath: "/tmp/openmc_sph.h5",
        referenceFlux: "/tmp/ce_flux.h5::openmc_volume_flux",
        mgFlux: "/tmp/mg_flux.h5::openmc_mg_flux",
        zeroFluxPolicy: "identity" as const,
      }),
    ).toBe(
      "openmc2donjon make-openmc-sph-sidecar /tmp/mgxs.h5 -o /tmp/openmc_sph.h5 --reference-flux /tmp/ce_flux.h5::openmc_volume_flux --mg-flux /tmp/mg_flux.h5::openmc_mg_flux --damping 1.0 --flux-normalization none --zero-flux-policy identity",
    );

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

  it("composes the IRENA PNL rate-preserving SPH prescription", () => {
    const options = {
      ...defaultEquivalenceOptions("openmc-sph-sidecar"),
      inputH5: "/tmp/mgxs.h5",
      outputPath: "/tmp/openmc_sph.h5",
      referenceFlux: "/tmp/ce_flux.h5::openmc_volume_flux",
      mgFlux: "/tmp/mg_flux.h5::openmc_mg_flux",
      sphTarget: "rate" as const,
      freezeGroups: "1,31",
      fluxFloorRel: "1e-3",
    };

    expect(buildEquivalenceCli(options)).toBe(
      "openmc2donjon make-openmc-sph-sidecar /tmp/mgxs.h5 -o /tmp/openmc_sph.h5 --reference-flux /tmp/ce_flux.h5::openmc_volume_flux --mg-flux /tmp/mg_flux.h5::openmc_mg_flux --damping 1.0 --flux-normalization none --sph-target rate --flux-floor-rel 1e-3 --freeze-groups 1,31",
    );
  });

  it("labels record attachment as Augment, never Inject", () => {
    const augmentAdf = equivalenceKindInfo("augment-adf");
    const augmentSph = equivalenceKindInfo("augment-sph");

    expect(augmentAdf.label).toBe("Augment ADF");
    expect(augmentAdf.title).toBe("Augment MGXS with ADF/DF");
    expect(augmentSph.label).toBe("Augment SPH");
    expect(augmentSph.title).toBe("Augment MGXS with SPH");
    // The mono commandIds stay the CLI ground truth.
    expect(augmentAdf.commandId).toBe("augment-adf");
    expect(augmentSph.commandId).toBe("augment-sph");
    for (const info of EQUIVALENCE_KINDS) {
      expect(`${info.label} ${info.title} ${info.summary}`).not.toMatch(/inject/i);
    }
  });
});

describe("OpenMC-side SPH artifact naming (openmc_sph.*)", () => {
  // One convention end-to-end: the make-openmc-sph-sidecar output must
  // match what the apply-sph builder spec and the canned workflow CLIs
  // already consume, or copied step commands break the chain.
  const sidecarName = equivalenceKindInfo("openmc-sph-sidecar").outputPlaceholder;

  it("uses openmc_sph.h5 as the form default output", () => {
    expect(sidecarName).toBe("openmc_sph.h5");
    expect(defaultEquivalenceOptions("openmc-sph-sidecar").outputPath).toBe(
      "openmc_sph.h5",
    );
  });

  it("agrees with the apply-sph builder spec's --sph-source default", () => {
    const applySph = COMMAND_BUILDER_SPECS.find((spec) => spec.id === "apply-sph");
    const sphSource = applySph?.fields.find((field) => field.name === "sph_source");

    expect(sphSource?.placeholder).toBe(sidecarName);
  });

  it("agrees with the canned OpenMC SPH workflow step CLIs", () => {
    const make = OPENMC_SPH_WORKFLOW_STEPS.find((step) => step.id === "sph-sidecar");
    const apply = OPENMC_SPH_WORKFLOW_STEPS.find((step) => step.id === "apply-sph");
    const augment = OPENMC_SPH_WORKFLOW_STEPS.find((step) => step.id === "augment");

    expect(make?.cli).toContain(`-o ${sidecarName}`);
    expect(apply?.cli).toContain(`--sph-source ${sidecarName}`);
    expect(augment?.cli).toContain(`--sph-source ${sidecarName}`);
  });

  it("does not collide with the different make-sph-sidecar output", () => {
    expect(equivalenceKindInfo("sph-sidecar").outputPlaceholder).toBe(
      "sph_sidecar.h5",
    );
    expect(equivalenceKindInfo("sph-sidecar").outputPlaceholder).not.toBe(sidecarName);
  });
});
