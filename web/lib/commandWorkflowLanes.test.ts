import { describe, expect, it } from "vitest";
import {
  COMMAND_WORKFLOW_LANES,
  commandWorkflowOccurrences,
  workflowLaneCommandIds,
} from "./commandWorkflowLanes";

describe("commandWorkflowLanes", () => {
  it("shows the production lanes without the legacy DONJON SPH loop", () => {
    expect(COMMAND_WORKFLOW_LANES.map((lane) => lane.id)).toEqual([
      "direct",
      "equivalence",
    ]);
  });

  it("keeps direct conversion connected to delivery", () => {
    const ids = workflowLaneCommandIds();

    expect(ids).toContain("direct-convert");
    expect(ids).toContain("bundle");
    expect(ids).toContain("validate-bundle");
  });

  it("keeps SPH inside the OpenMC-side equivalence lane", () => {
    const equivalenceLane = COMMAND_WORKFLOW_LANES.find((lane) => lane.id === "equivalence");
    expect(equivalenceLane).toBeDefined();
    const firstStep = equivalenceLane!.steps[0];
    const sidecarStep = equivalenceLane!.steps.find((step) => step.id === "sidecar");

    expect(firstStep.title).toContain("OpenMC");
    expect(firstStep.body).toContain("OpenMC CE/MG SPH");
    expect(sidecarStep?.commandIds).toContain("make-openmc-sph-sidecar");
    expect(sidecarStep?.commandIds).toContain("make-sph-sidecar");
  });

  it("finds all workflow positions for commands reused across lanes", () => {
    const occurrences = commandWorkflowOccurrences("direct-convert");

    expect(occurrences.map((item) => item.lane.id)).toEqual([
      "direct",
      "equivalence",
    ]);
    expect(occurrences[0].step.title).toBe("Write ASCII");
    expect(occurrences[0].previousStep?.title).toBe("Inspect and preflight");
    expect(occurrences[0].nextStep?.title).toBe("Bundle and share");
  });

  it("returns an empty list for commands outside the visual workflow lanes", () => {
    expect(commandWorkflowOccurrences("serve")).toEqual([]);
  });
});
