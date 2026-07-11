import { describe, expect, it } from "vitest";
import type { CommandCatalogEntry } from "./api";
import { commandWorkflowMapping } from "./commandWorkflowMapping";

describe("commandWorkflowMapping", () => {
  it("describes direct conversion deep links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "direct-convert",
        group: "convert",
        web_path: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
      }),
    );

    expect(mapping.available).toBe(true);
    expect(mapping.surface).toBe("Convert page");
    expect(mapping.presets).toContain("Output object: MULTICOMPO");
    expect(mapping.presets).toContain("Preflight: on");
    expect(mapping.presets).toContain("Production checks: on");
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
    expect(mapping.presets).toContain("Production checks: on");
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

  it("describes OpenMC-side SPH sidecar links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "make-sph-sidecar",
        group: "sph",
        web_path: "/equivalence?kind=sph-sidecar",
      }),
    );

    expect(mapping.surface).toBe("Equivalence page");
    expect(mapping.presets).toContain("Builder: make OpenMC-side SPH sidecar");
    expect(mapping.requiredInputs).toContain("OpenMC CE/MG SPH table or source options");
  });

  it("describes ADF/SPH equivalence command-builder links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "make-adf-sidecar",
        group: "adf",
        web_path: "/equivalence?kind=adf-sidecar",
      }),
    );

    expect(mapping.available).toBe(true);
    expect(mapping.surface).toBe("Equivalence page");
    expect(mapping.title).toBe("Sidecar command builder");
    expect(mapping.presets).toContain("Builder: make ADF/DF sidecar");
    expect(mapping.requiredInputs).toContain("ADF sidecar output path");
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

  it("describes PyGan links with a friendly surface instead of the raw pathname", () => {
    const doctor = commandWorkflowMapping(
      command({ id: "pygan-doctor", group: "pygan", web_path: "/pygan" }),
    );

    expect(doctor.available).toBe(true);
    expect(doctor.surface).toBe("PyGan page");
    expect(doctor.title).toBe("PyGan diagnostics and writer comparison");

    const compare = commandWorkflowMapping(
      command({
        id: "compare-writers",
        group: "pygan",
        web_path: "/pygan?tab=compare",
      }),
    );

    expect(compare.surface).toBe("PyGan page");
    // /pygan never reads a "tab" param, so it must not surface as a preset.
    expect(compare.presets).not.toContain("tab: compare");
  });

  it("describes generic command-builder links", () => {
    const mapping = commandWorkflowMapping(
      command({
        id: "diff",
        group: "inspect",
        web_path: "/builder?command=diff",
      }),
    );

    expect(mapping.available).toBe(true);
    expect(mapping.surface).toBe("Command builder");
    expect(mapping.presets).toContain("Builder: diff");
    expect(mapping.requiredInputs).toContain("Terminal execution after copy");
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
