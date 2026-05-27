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

  it("shows the OpenMC-side SPH route as CE flux, MG flux, sidecar, augment, convert", () => {
    const sphLane = COMMAND_WORKFLOW_LANES.find((lane) => lane.id === "openmc-sph");
    expect(sphLane).toBeDefined();

    expect(sphLane!.steps.map((step) => step.id)).toEqual([
      "ce-flux",
      "mg-flux",
      "sph-sidecar",
      "augment",
      "convert",
    ]);
    expect(sphLane!.steps[0].body).toContain("continuous-energy OpenMC");
    expect(sphLane!.steps[1].body).toContain("selected group structure");
    expect(sphLane!.steps[2].commandIds).toContain("make-openmc-sph-sidecar");
    expect(sphLane!.steps[2].commandIds).toContain("make-sph-update-table");
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
});
