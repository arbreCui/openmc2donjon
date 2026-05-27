import { describe, expect, it } from "vitest";
import {
  LIVE_OPENMC_SPH_DEMO,
  MOCK_OPENMC_SPH_DEMO,
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

  it("points the live minicase to the repository smoke output directory", () => {
    expect(LIVE_OPENMC_SPH_DEMO.command).toBe(
      "bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh",
    );
    expect(LIVE_OPENMC_SPH_DEMO.mgxs).toContain(
      "/private/tmp/openmc2donjon_ce_mg_33g_sph_minicase/handoff",
    );
    expect(LIVE_OPENMC_SPH_DEMO.physicsSummary).toContain("physics_summary.json");
  });
});
