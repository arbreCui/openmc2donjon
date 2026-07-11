import { describe, expect, it } from "vitest";
import type { CommandCatalogEntry } from "./api";
import {
  builderCatalogFailureHint,
  builderFallbackCopy,
  commandContextRows,
} from "./builderCopy";

describe("builderFallbackCopy", () => {
  it("offers the catalog CLI when the catalog lists the command", () => {
    const copy = builderFallbackCopy("ok", command("pygan-inspect-compo"), "pygan-inspect-compo");
    expect(copy.message).toBe(
      "This command is visible in the catalog, but no structured builder exists yet.",
    );
    expect(copy.cli).toBe("openmc2donjon pygan-inspect-compo");
  });

  it("does not fabricate a command for ids the catalog does not contain", () => {
    // Regression: unknown ids used to render a copyable
    // `openmc2donjon <id>` and claim the id was "visible in the catalog".
    const copy = builderFallbackCopy("ok", null, "no-such-command");
    expect(copy.cli).toBeNull();
    expect(copy.message).toContain('"no-such-command"');
    expect(copy.message).not.toContain("visible in the catalog");
  });

  it("does not claim catalog visibility while the catalog is unavailable", () => {
    const failed = builderFallbackCopy("error", null, "pygan-doctor");
    expect(failed.cli).toBeNull();
    expect(failed.message).toContain("catalog could not be loaded");
    expect(failed.message).not.toContain("visible in the catalog");

    const loading = builderFallbackCopy("loading", null, "pygan-doctor");
    expect(loading.cli).toBeNull();
    expect(loading.message).toContain("Checking the command catalog");
  });
});

describe("builderCatalogFailureHint", () => {
  it("only claims a local builder when one exists", () => {
    expect(builderCatalogFailureHint(true)).toBe(
      "The local builder can still assemble its CLI preview.",
    );
    expect(builderCatalogFailureHint(false)).toBe(
      "No local builder exists for this command id, so no CLI preview is available.",
    );
  });
});

describe("commandContextRows", () => {
  it("uses the catalog guidance when available", () => {
    const rows = commandContextRows(command("diff"));
    expect(rows.map(([label]) => label)).toEqual(["Use when", "Produces", "After this"]);
    expect(rows[0][1]).toBe("diff use");
  });

  it("omits the duplicated stage summary in the catalog-less fallback", () => {
    // Regression: the fallback "Use when" row repeated the identical
    // stage.summary sentence rendered by the workflow-step panel above.
    const rows = commandContextRows(null);
    expect(rows.map(([label]) => label)).toEqual(["Produces", "After this"]);
  });
});

function command(id: string): CommandCatalogEntry {
  return {
    id,
    kind: "subcommand",
    name: id,
    aliases: [],
    group: "test",
    title: id,
    summary: `${id} summary`,
    cli_help: `${id} help`,
    status: "partial",
    status_label: "Command builder ready",
    web_path: `/builder?command=${id}`,
    cli: `openmc2donjon ${id}`,
    tags: [],
    use_when: `${id} use`,
    produces: `${id} output`,
    next_step: `${id} next`,
  };
}
