import { describe, expect, it } from "vitest";
import type { ConvertResponse } from "./api";
import { convertOutputMode } from "./convertOutputMode";

describe("convertOutputMode", () => {
  it("treats a passing dry run as ready to write", () => {
    expect(convertOutputMode(response({ dry_run: true }))).toBe("dry-run-ready");
  });

  it("treats confirmed conversion as converted", () => {
    expect(
      convertOutputMode(
        response({ dry_run: false, converted: true, output_exists: true }),
      ),
    ).toBe("converted");
  });

  it("treats failed or unconfirmed runs as blocked", () => {
    expect(convertOutputMode(response({ ok: false, preflight_ok: false }))).toBe(
      "blocked",
    );
    expect(
      convertOutputMode(
        response({ dry_run: false, converted: true, output_exists: false }),
      ),
    ).toBe("blocked");
    expect(convertOutputMode(response({ dry_run: true, output_exists: true }))).toBe(
      "blocked",
    );
  });
});

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
