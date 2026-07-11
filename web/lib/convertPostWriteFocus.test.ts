import { describe, expect, it } from "vitest";
import type { ConvertResponse } from "./api";
import { convertPostWriteFocus } from "./convertPostWriteFocus";

describe("convertPostWriteFocus", () => {
  it("does not show delivery focus before a confirmed output exists", () => {
    expect(convertPostWriteFocus(response({ dry_run: true }))).toBeNull();
    expect(
      convertPostWriteFocus(
        response({ dry_run: false, converted: true, output_exists: false }),
      ),
    ).toBeNull();
  });

  it("points ASCII writer output at the DONJON input card", () => {
    const focus = convertPostWriteFocus(
      response({ dry_run: false, converted: true, output_exists: true }),
    );

    expect(focus?.badge).toBe("default production route");
    expect(focus?.title).toBe(
      "Review the ASCII file, then prepare the DONJON input card",
    );
    expect(focus?.body).toContain("normal converter route");
  });

  it("focuses PyGan writer output on semantic writer comparison", () => {
    const focus = convertPostWriteFocus(
      response({
        dry_run: false,
        converted: true,
        output_exists: true,
        writer_backend: "pygan",
      }),
    );

    expect(focus?.badge).toBe("optional backend evidence");
    expect(focus?.title).toContain("Validate the PyGan writer");
    expect(focus?.body).toContain("writer comparison");
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
