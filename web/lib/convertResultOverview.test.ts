import { describe, expect, it } from "vitest";
import type { ConvertResponse } from "./api";
import { convertResultOverview } from "./convertResultOverview";

describe("convertResultOverview", () => {
  it("puts dry-run no-write semantics first", () => {
    const tiles = convertResultOverview(response({ dry_run: true }));

    expect(values(tiles)).toMatchObject({
      write: "Dry-run only",
      target: "/runs/case/out.mcompo.txt",
      next: "Convert now",
    });
    expect(tiles.find((tile) => tile.id === "write")?.body).toContain(
      "No ASCII file was written",
    );
  });

  it("surfaces the confirmed DONJON file after conversion", () => {
    const tiles = convertResultOverview(
      response({ dry_run: false, converted: true, output_exists: true }),
    );

    expect(values(tiles)).toMatchObject({
      write: "ASCII written",
      target: "/runs/case/out.mcompo.txt",
      next: "Preview / bundle",
    });
    expect(tiles.find((tile) => tile.id === "target")?.label).toBe("DONJON file");
  });

  it("blocks conversion when the run failed", () => {
    const tiles = convertResultOverview(
      response({ ok: false, preflight_ok: false, dry_run: true }),
    );

    expect(values(tiles)).toMatchObject({
      write: "No ASCII written",
      next: "Fix checks",
    });
    expect(tiles.every((tile) => tile.tone === "blocked")).toBe(true);
  });
});

function values(
  tiles: ReturnType<typeof convertResultOverview>,
): Record<string, string> {
  return Object.fromEntries(tiles.map((tile) => [tile.id, tile.value]));
}

function response(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: true,
    converted: false,
    format: "multicompo",
    writer_backend: "ascii",
    input_path: "/runs/case/mgxs_library.h5",
    output_path: "/runs/case/out.mcompo.txt",
    summary_path: null,
    summary_written: false,
    output_exists: false,
    output_size: null,
    preflight_ok: true,
    preflight: null,
    cli_command: [],
    cli_command_text: "openmc2donjon /runs/case/mgxs_library.h5",
    ...overrides,
  };
}
