import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput, ConvertResponse } from "./api";
import { convertDecision } from "./convertDecision";

describe("convertDecision", () => {
  it("turns a passing dry run into a clear convert decision", () => {
    const decision = convertDecision(
      response({ dry_run: true, converted: false }),
      input(),
    );
    expect(decision.tone).toBe("pending");
    expect(decision.title).toBe("Ready to convert");
    expect(decision.reasons).toContain(
      "Preflight decision: mgxs input contract passed.",
    );
    expect(decision.reasons).toContain(
      "Dry run did not create or replace an ASCII file.",
    );
    expect(decision.nextAction.label).toBe("Next action");
    expect(decision.nextAction.body).toContain("No ASCII file was written");
    expect(decision.nextAction.body).toContain("Convert now");
  });

  it("surfaces warnings without blocking a passing dry run", () => {
    const decision = convertDecision(
      response({ dry_run: true, converted: false }),
      input({ warnings: ["nu ratio outside nominal range"] }),
    );
    expect(decision.tone).toBe("pending");
    expect(decision.reasons).toContain("1 warning(s) remain for audit review.");
  });

  it("summarizes failed preflight issues", () => {
    const decision = convertDecision(
      response({ ok: false, preflight_ok: false, dry_run: true, converted: false }),
      input({ ok: false, issues: ["missing total dataset", "chi is negative"] }),
    );
    expect(decision.tone).toBe("blocked");
    expect(decision.title).toBe("Do not convert yet");
    expect(decision.reasons).toContain(
      "2 issues: missing total dataset (+1 more).",
    );
    expect(decision.nextAction.body).toContain("rerun dry run");
  });

  it("reports a confirmed ASCII artifact after conversion", () => {
    const decision = convertDecision(
      response({ dry_run: false, converted: true, output_exists: true, output_size: 1234 }),
      input(),
    );
    expect(decision.tone).toBe("ready");
    expect(decision.badge).toBe("L_MULTICOMPO");
    expect(decision.reasons).toContain("Output size: 1234 bytes.");
    expect(decision.nextAction.body).toContain("Preview the LCM blocks");
  });
});

function response(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: true,
    converted: false,
    format: "multicompo",
    input_path: "/mock/handoff.h5",
    output_path: "/mock/out.mcompo.txt",
    output_exists: false,
    output_size: null,
    preflight_ok: true,
    preflight: {
      schema: "openmc2donjon.convert.preflight.v1",
      decision: "mgxs_input_contract_passed",
      output_issue: null,
      inputs: [input()],
    },
    cli_command: ["openmc2donjon", "/mock/handoff.h5"],
    cli_command_text: "openmc2donjon /mock/handoff.h5 -o /mock/out.mcompo.txt",
    ...overrides,
  };
}

function input(
  overrides: Partial<ConvertPreflightInput> = {},
): ConvertPreflightInput {
  return {
    path: "/mock/handoff.h5",
    ok: true,
    energy_groups: 7,
    legendre_order: 1,
    mixtures: 9,
    calculations: 9,
    state_points: 1,
    issues: [],
    warnings: [],
    ...overrides,
  };
}
