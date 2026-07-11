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

  it("focuses ASCII writer output on bundle and DONJON delivery", () => {
    const focus = convertPostWriteFocus(
      response({ dry_run: false, converted: true, output_exists: true }),
    );

    expect(focus?.badge).toBe("default production path");
    expect(focus?.title).toContain("DONJON guide");
    expect(focus?.primaryLabel).toBe("Bundle handoff");
    expect(focus?.primaryHref).toContain("/builder?command=bundle");
    expect(focus?.secondaryLabel).toBe("Open DONJON guide");
    expect(focus?.secondaryHref).toContain("/donjon?");
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
    expect(focus?.primaryLabel).toBe("Validate PyGan comparison");
    expect(focus?.primaryHref).toContain("/pygan?input_h5=");
    expect(focus?.primaryHref).not.toContain("tab=");
    expect(focus?.secondaryLabel).toBe("Bundle handoff");
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
