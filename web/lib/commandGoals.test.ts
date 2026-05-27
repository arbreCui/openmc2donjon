import { describe, expect, it } from "vitest";
import type { CommandCatalogEntry } from "./api";
import {
  commandGoalCommandIds,
  commandGoals,
  commandGoalsForCommand,
} from "./commandGoals";

describe("commandGoals", () => {
  it("groups commands by user goal with status counts", () => {
    const goals = commandGoals([
      command("direct-convert", "ready"),
      command("check", "partial"),
      command("bundle", "planned"),
      command("make-sph-sidecar", "partial"),
    ]);

    const direct = goals.find((goal) => goal.id === "direct-convert");
    expect(direct).toMatchObject({
      readyCount: 1,
      partialCount: 1,
      plannedCount: 1,
    });
    expect(direct?.commands.map((command) => command.id)).toEqual([
      "direct-convert",
      "check",
      "bundle",
    ]);
    expect(direct?.missingCommandIds).toContain("inspect");
  });

  it("keeps OpenMC visible in the SPH sidecar goal", () => {
    const goals = commandGoals([
      command("export-volume-flux", "partial"),
      command("make-openmc-sph-sidecar", "partial"),
      command("augment-sph", "partial"),
    ]);

    const sph = goals.find((goal) => goal.id === "openmc-sph");
    expect(sph?.body).toContain("OpenMC CE");
    expect(sph?.actionHint).toContain("sidecar");
    expect(sph?.commands.map((command) => command.id)).toEqual([
      "export-volume-flux",
      "make-openmc-sph-sidecar",
      "augment-sph",
    ]);
  });

  it("finds all goals that reuse a command", () => {
    expect(commandGoalsForCommand("bundle").map((goal) => goal.id)).toEqual([
      "direct-convert",
      "package",
    ]);
    expect(commandGoalsForCommand("missing")).toEqual([]);
  });

  it("returns the command ids for a selected user goal", () => {
    expect(commandGoalCommandIds("direct-convert")).toEqual([
      "direct-convert",
      "check",
      "inspect",
      "bundle",
    ]);
  });
});

function command(id: string, status: CommandCatalogEntry["status"]): CommandCatalogEntry {
  return {
    id,
    kind: "subcommand",
    name: id,
    aliases: [],
    group: "test",
    title: id,
    summary: `${id} summary`,
    cli_help: `${id} help`,
    status,
    status_label: status,
    web_path: status === "planned" ? null : `/${id}`,
    cli: `openmc2donjon ${id}`,
    tags: [],
    use_when: `${id} use`,
    produces: `${id} output`,
    next_step: `${id} next`,
  };
}
