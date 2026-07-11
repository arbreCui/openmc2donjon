import type { CommandCatalogEntry } from "./api";

/**
 * Copy for the /builder page whose truthfulness depends on catalog
 * state. Kept out of the page component so the branching can be
 * unit-tested: the fallback used to assert "visible in the catalog"
 * even when the catalog failed or lacked the id, and fabricated a
 * copyable ``openmc2donjon <id>`` command for unknown ids.
 */

export type CatalogAvailability = "loading" | "ok" | "error";

export interface BuilderFallbackCopy {
  message: string;
  /** CLI to offer for copying; null when no trustworthy command exists. */
  cli: string | null;
}

export function builderFallbackCopy(
  catalog: CatalogAvailability,
  command: CommandCatalogEntry | null,
  commandId: string,
): BuilderFallbackCopy {
  if (command) {
    return {
      message:
        "This command is visible in the catalog, but no structured builder exists yet.",
      cli: command.cli,
    };
  }
  if (catalog === "loading") {
    return {
      message: `Checking the command catalog for "${commandId}"…`,
      cli: null,
    };
  }
  if (catalog === "error") {
    return {
      message:
        `The command catalog could not be loaded, so "${commandId}" cannot be ` +
        "verified and no CLI preview is available.",
      cli: null,
    };
  }
  return {
    message:
      `The command catalog does not contain "${commandId}", so there is no CLI ` +
      "to copy. Pick a command from the catalog instead.",
    cli: null,
  };
}

/** Tail of the catalog-failure banner: only claim a local builder when one exists. */
export function builderCatalogFailureHint(hasLocalBuilder: boolean): string {
  return hasLocalBuilder
    ? "The local builder can still assemble its CLI preview."
    : "No local builder exists for this command id, so no CLI preview is available.";
}

/**
 * Rows for the "command in plain language" panel. The catalog-less
 * fallback deliberately omits "Use when": the workflow-step panel above
 * already renders the stage summary, and repeating the identical
 * sentence in two adjacent panels read as a rendering mistake.
 */
export function commandContextRows(
  command: CommandCatalogEntry | null,
): readonly (readonly [string, string])[] {
  if (command) {
    return [
      ["Use when", command.use_when],
      ["Produces", command.produces],
      ["After this", command.next_step],
    ];
  }
  return [
    ["Produces", "A copyable CLI command assembled from the form values."],
    [
      "After this",
      "Run the command locally and keep any generated summaries with the handoff.",
    ],
  ];
}
