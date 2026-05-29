import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput, ConvertResponse } from "./api";
import { convertBlockedGuidance } from "./convertBlockedGuidance";

describe("convertBlockedGuidance", () => {
  it("prioritizes failed validation issues", () => {
    const guidance = convertBlockedGuidance(
      response({
        ok: false,
        preflight_ok: false,
        preflight: preflight({ decision: "failed" }),
      }),
      input({ ok: false, issues: ["missing total", "chi is negative"] }),
    );

    expect(guidance.badge).toBe("blocked");
    expect(guidance.title).toContain("Fix validation");
    expect(guidance.tone).toBe("fail");
    expect(guidance.facts).toContain("2 issues: missing total (+1 more)");
  });

  it("explains passing dry-runs blocked by an existing target", () => {
    const guidance = convertBlockedGuidance(
      response({ dry_run: true, output_exists: true }),
      input(),
    );

    expect(guidance.badge).toBe("target exists");
    expect(guidance.title).toContain("overwrite");
    expect(guidance.tone).toBe("warn");
    expect(guidance.facts).toContain("Existing target: /runs/case/out.mcompo.txt");
  });

  it("explains converted responses whose output cannot be confirmed", () => {
    const guidance = convertBlockedGuidance(
      response({ dry_run: false, converted: true, output_exists: false }),
      input(),
    );

    expect(guidance.badge).toBe("not confirmed");
    expect(guidance.title).toContain("Confirm");
    expect(guidance.facts).toContain("Unconfirmed target: /runs/case/out.mcompo.txt");
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
    preflight: preflight(),
    cli_command: [],
    cli_command_text: "openmc2donjon /runs/case/mgxs_library.h5",
    ...overrides,
  };
}

function preflight(
  overrides: Partial<ConvertResponse["preflight"]> = {},
): NonNullable<ConvertResponse["preflight"]> {
  return {
    schema: "openmc2donjon.mgxs-input-preflight.v1",
    decision: "passed",
    output_issue: null,
    inputs: [],
    ...overrides,
  };
}

function input(
  overrides: Partial<ConvertPreflightInput> = {},
): ConvertPreflightInput {
  return {
    path: "/runs/case/mgxs_library.h5",
    ok: true,
    energy_groups: 7,
    legendre_order: 3,
    issues: [],
    warnings: [],
    ...overrides,
  };
}
