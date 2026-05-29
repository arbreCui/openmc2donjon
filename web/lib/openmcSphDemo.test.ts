import { describe, expect, it } from "vitest";
import {
  LIVE_OPENMC_SPH_DEMO,
  MOCK_OPENMC_SPH_DEMO,
  openmcSphBundleHref,
  openmcSphConvertHref,
  openmcSphEvidenceHref,
  openmcSphFluxExportHref,
  openmcSphPlannerPrefill,
} from "./openmcSphDemo";

describe("openmcSphDemo", () => {
  it("prefills the OpenMC planner for the SPH route", () => {
    const prefill = openmcSphPlannerPrefill(MOCK_OPENMC_SPH_DEMO);

    expect(prefill.workflow).toBe("two-step");
    expect(prefill.equivalence).toBe("sph");
    expect(prefill.format).toBe("macrolib");
    expect(prefill.production).toBe(true);
    expect(prefill.keepHdf5Path).toBe(MOCK_OPENMC_SPH_DEMO.augmentedH5);
    expect(prefill.outputPath).toBe(MOCK_OPENMC_SPH_DEMO.ascii);
    expect(prefill.outputPath).toContain(".macrolib.txt");
    expect(prefill.sphSource).toBe(MOCK_OPENMC_SPH_DEMO.sphSidecar);
  });

  it("builds distinct CE and MG volume-flux export links", () => {
    const ce = openmcSphFluxExportHref(MOCK_OPENMC_SPH_DEMO, "ce");
    const mg = openmcSphFluxExportHref(MOCK_OPENMC_SPH_DEMO, "mg");

    expect(ce).toContain("command=export-volume-flux");
    expect(ce).toContain("dataset_name=openmc_volume_flux");
    expect(ce).toContain("tally_name=openmc_ce_volume_flux");
    expect(mg).toContain("dataset_name=openmc_mg_flux");
    expect(mg).toContain("tally_name=openmc_mg_volume_flux");
  });

  it("builds the three-link demo mainline from evidence to converter to bundle", () => {
    const evidence = new URL(
      openmcSphEvidenceHref(MOCK_OPENMC_SPH_DEMO),
      "http://localhost:3000",
    );
    expect(evidence.pathname).toBe("/openmc");
    expect(evidence.hash).toBe("#openmc-sph-summary");
    expect(evidence.searchParams.get("equivalence")).toBe("sph");
    expect(evidence.searchParams.get("summary")).toBe(
      MOCK_OPENMC_SPH_DEMO.physicsSummary,
    );

    const convert = new URL(
      openmcSphConvertHref(MOCK_OPENMC_SPH_DEMO),
      "http://localhost:3000",
    );
    expect(convert.pathname).toBe("/convert");
    expect(convert.searchParams.get("intent")).toBe("openmc-sph");
    expect(convert.searchParams.get("input")).toBe(MOCK_OPENMC_SPH_DEMO.augmentedH5);
    expect(convert.searchParams.get("output")).toBe(MOCK_OPENMC_SPH_DEMO.ascii);
    expect(convert.searchParams.get("format")).toBe("macrolib");
    expect(convert.searchParams.get("production")).toBe("1");

    const bundle = new URL(
      openmcSphBundleHref(MOCK_OPENMC_SPH_DEMO),
      "http://localhost:3000",
    );
    expect(bundle.pathname).toBe("/builder");
    expect(bundle.searchParams.get("command")).toBe("bundle");
    expect(bundle.searchParams.get("mgxs")).toBe(MOCK_OPENMC_SPH_DEMO.augmentedH5);
    expect(bundle.searchParams.get("macrolib")).toBe(MOCK_OPENMC_SPH_DEMO.ascii);
  });

  it("points the live minicase to the repository smoke output directory", () => {
    expect(LIVE_OPENMC_SPH_DEMO.command).toContain(
      "OPENMC2DONJON_COLORSET_VARIANT=two_region",
    );
    expect(LIVE_OPENMC_SPH_DEMO.command).toContain("BATCHES=80");
    expect(LIVE_OPENMC_SPH_DEMO.command).toContain("MG_BATCHES=80");
    expect(LIVE_OPENMC_SPH_DEMO.command).toContain("MAX_CE_FLUX_REL_STD=0.06");
    expect(LIVE_OPENMC_SPH_DEMO.mgxs).toContain(
      "/private/tmp/openmc2donjon_two_region_production_probe_20260529/handoff",
    );
    expect(LIVE_OPENMC_SPH_DEMO.ceStatepoint).toContain("statepoint.80.h5");
    expect(LIVE_OPENMC_SPH_DEMO.mgStatepoint).toContain("statepoint.80.h5");
    expect(LIVE_OPENMC_SPH_DEMO.physicsSummary).toContain("physics_summary.json");
  });
});
