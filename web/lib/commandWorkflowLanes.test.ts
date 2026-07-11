import { describe, expect, it } from "vitest";
import {
  COMMAND_WORKFLOW_LANES,
  commandWorkflowOccurrences,
  workflowLaneCommandIds,
} from "./commandWorkflowLanes";

describe("commandWorkflowLanes", () => {
  it("shows only the current production lanes", () => {
    expect(COMMAND_WORKFLOW_LANES.map((lane) => lane.id)).toEqual([
      "direct",
      "openmc-sph",
      "adf-df",
    ]);
  });

  it("keeps direct conversion connected to delivery", () => {
    const ids = workflowLaneCommandIds();

    expect(ids).toContain("direct-convert");
    expect(ids).toContain("bundle");
    expect(ids).toContain("validate-bundle");
  });

  it("shows the OpenMC-side SPH route as CE flux, MG flux, sidecar, apply, augment, convert", () => {
    const sphLane = COMMAND_WORKFLOW_LANES.find((lane) => lane.id === "openmc-sph");
    expect(sphLane).toBeDefined();

    expect(sphLane!.steps.map((step) => step.id)).toEqual([
      "ce-flux",
      "mg-flux",
      "sph-sidecar",
      "apply-sph",
      "augment",
      "convert",
    ]);
    expect(sphLane!.steps[0].body).toContain("continuous-energy OpenMC");
    expect(sphLane!.steps[1].body).toContain("selected energy mesh");
    expect(sphLane!.steps[5].href).toContain("format=macrolib");
    expect(sphLane!.steps[2].commandIds).toContain("make-openmc-sph-sidecar");
    expect(sphLane!.steps[2].commandIds).toContain("make-sph-update-table");
    expect(sphLane!.steps[3].commandIds).toContain("apply-sph");
    expect(sphLane!.summary).toContain("one-shot SPH");
    expect(sphLane!.steps[3].body).toContain("damping-sensitive");
  });

  it("finds all workflow positions for commands reused across lanes", () => {
    const occurrences = commandWorkflowOccurrences("direct-convert");

    expect(occurrences.map((item) => item.lane.id)).toEqual([
      "direct",
      "openmc-sph",
      "adf-df",
    ]);
    expect(occurrences[0].step.title).toBe("Write ASCII");
    expect(occurrences[0].previousStep?.title).toBe("Inspect and preflight");
    expect(occurrences[0].nextStep?.title).toBe("Bundle and share");
  });

  it("returns an empty list for commands outside the visual workflow lanes", () => {
    expect(commandWorkflowOccurrences("serve")).toEqual([]);
  });

  it("keeps the shared vocabulary: bundle pitch, augment verb, no inject", () => {
    const direct = COMMAND_WORKFLOW_LANES.find((lane) => lane.id === "direct");
    const deliver = direct!.steps.find((step) => step.id === "deliver");
    expect(deliver!.body).toContain("Collect the MGXS HDF5");
    expect(deliver!.body).toContain("bundle");

    const adf = COMMAND_WORKFLOW_LANES.find((lane) => lane.id === "adf-df");
    // The one per-page "sidecar" gloss for /commands lives here.
    expect(adf!.summary).toContain("small companion HDF5");

    for (const lane of COMMAND_WORKFLOW_LANES) {
      expect(lane.summary.toLowerCase()).not.toContain("inject");
      for (const step of lane.steps) {
        expect(step.body.toLowerCase()).not.toContain("inject");
      }
    }
  });
});
