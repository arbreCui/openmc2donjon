import { describe, expect, it } from "vitest";
import type { CommandCatalogEntry } from "./api";
import { commandCoverage } from "./commandCoverage";

describe("commandCoverage", () => {
  it("summarizes web-linked commands by status, surface, and group", () => {
    const coverage = commandCoverage({
      schema: "test",
      groups: [
        { id: "convert", label: "Convert", summary: "Convert", command_count: 2 },
        { id: "adf", label: "ADF", summary: "ADF", command_count: 1 },
      ],
      commands: [
        command("direct-convert", "convert", "ready", "/convert?intent=direct-convert"),
        command("check", "convert", "partial", "/convert?intent=check"),
        command("make-adf-sidecar", "adf", "planned", null),
      ],
      status_counts: {},
    });

    expect(coverage.total).toBe(3);
    expect(coverage.webLinked).toBe(2);
    expect(coverage.cliOnly).toBe(1);
    expect(coverage.coveragePercent).toBe(67);
    expect(coverage.surfaces[0]).toEqual({ surface: "Convert page", count: 2 });
    expect(coverage.groups).toContainEqual({
      id: "convert",
      label: "Convert",
      total: 2,
      webLinked: 2,
      ready: 1,
      partial: 1,
      planned: 0,
      coveragePercent: 100,
    });
  });
});

function command(
  id: string,
  group: string,
  status: CommandCatalogEntry["status"],
  webPath: string | null,
): CommandCatalogEntry {
  return {
    id,
    kind: "subcommand",
    name: id,
    aliases: [],
    group,
    title: id,
    summary: "summary",
    cli_help: "help",
    status,
    status_label: status,
    web_path: webPath,
    cli: `openmc2donjon ${id}`,
    tags: [],
    use_when: "use when this command is needed",
    produces: "produces an artifact or a command",
    next_step: "continue to the next workflow step",
  };
}
