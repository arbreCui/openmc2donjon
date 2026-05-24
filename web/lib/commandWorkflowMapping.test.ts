import { describe, expect, it } from "vitest";
import type { CommandCatalogEntry } from "./api";
import { commandWorkflowMapping } from "./commandWorkflowMapping";

describe("commandWorkflowMapping", () => {
  it("describes direct conversion deep links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "direct-convert",
        group: "convert",
        web_path: "/convert?intent=direct-convert&format=multicompo&check=1",
      }),
    );

    expect(mapping.available).toBe(true);
    expect(mapping.surface).toBe("Convert page");
    expect(mapping.presets).toContain("Output object: MULTICOMPO");
    expect(mapping.presets).toContain("Preflight: on");
    expect(mapping.presets).toContain("Production gates: off");
    expect(mapping.requiredInputs).toContain("Input MGXS HDF5 path");
  });

  it("describes production preflight deep links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "check",
        group: "inspect",
        web_path: "/convert?intent=check&format=multicompo&check=1&production=1",
      }),
    );

    expect(mapping.surface).toBe("Convert page");
    expect(mapping.presets).toContain("Production gates: on");
  });

  it("describes OpenMC planner deep links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "openmc2donjon-export",
        group: "openmc",
        web_path: "/openmc?intent=export&workflow=two-step",
      }),
    );

    expect(mapping.surface).toBe("OpenMC planner");
    expect(mapping.presets).toContain("Workflow: two-step export then convert");
    expect(mapping.presets).toContain("Equivalence: direct");
  });

  it("describes audit viewer links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "run-sph-loop",
        group: "sph",
        web_path: "/audit",
      }),
    );

    expect(mapping.surface).toBe("Audit page");
    expect(mapping.requiredInputs).toEqual(["SPH loop summary JSON path"]);
  });

  it("gives a CLI-only explanation when no web surface exists", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "augment-adf",
        group: "adf",
        web_path: null,
      }),
    );

    expect(mapping.available).toBe(false);
    expect(mapping.surface).toBe("CLI only");
    expect(mapping.requiredInputs).toEqual(["Use the CLI form below"]);
  });
});

function command(
  overrides: Pick<CommandCatalogEntry, "id" | "group" | "web_path">,
): CommandCatalogEntry {
  return {
    id: overrides.id,
    kind: "subcommand",
    name: overrides.id,
    aliases: [],
    group: overrides.group,
    title: overrides.id,
    summary: "summary",
    cli_help: "help",
    status: overrides.web_path ? "ready" : "planned",
    status_label: overrides.web_path ? "Web form ready" : "CLI only",
    web_path: overrides.web_path,
    cli: `openmc2donjon ${overrides.id}`,
    tags: [],
    use_when: "use when",
    produces: "produces",
    next_step: "next step",
  };
}
