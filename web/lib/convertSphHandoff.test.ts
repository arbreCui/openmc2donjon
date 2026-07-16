import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput, ConvertResponse } from "./api";
import { convertSphHandoffStatus } from "./convertSphHandoff";

describe("convertSphHandoffStatus", () => {
  it("summarizes an SPH-augmented MACROLIB NSPH handoff", () => {
    const status = convertSphHandoffStatus(
      response({ format: "macrolib", dry_run: true, converted: false }),
      input({ sph_calculations: 2 }),
    );

    expect(status).toMatchObject({
      title: "SPH handoff detected",
      badge: "MACROLIB NSPH route",
      tone: "ready",
    });
    expect(status?.source).toContain("2 SPH calculations");
    expect(status?.source).toContain("SPH-augmented");
    expect(status?.output).toContain("GROUP/*/NSPH");
    expect(status?.nextAction).toContain("Run Convert");
  });

  it("warns when an SPH-bearing handoff is aimed at MULTICOMPO", () => {
    const status = convertSphHandoffStatus(
      response({ format: "multicompo" }),
      input({ sph_calculations: 2 }),
    );

    expect(status).toMatchObject({
      badge: "Review output format",
      tone: "warn",
    });
    expect(status?.output).toContain("validated DONJON NSPH consume smoke uses L_MACROLIB");
  });

  it("does not urge writing an NSPH handoff via MULTICOMPO", () => {
    const status = convertSphHandoffStatus(
      response({ format: "multicompo", dry_run: true, converted: false }),
      input({ sph_calculations: 2 }),
    );

    expect(status?.nextAction).not.toContain("NSPH-bearing ASCII handoff");
    expect(status?.nextAction).toContain("inert metadata");
    expect(status?.nextAction).toContain("MACROLIB (DSPH: + MAC:)");
    expect(status?.nextAction).toContain("apply-sph");
  });

  it("stays hidden for direct handoffs without SPH", () => {
    expect(convertSphHandoffStatus(response(), input({ sph_calculations: 0 }))).toBeNull();
    expect(convertSphHandoffStatus(response(), null)).toBeNull();
  });

  it("accepts an SPH-applied MULTICOMPO handoff with no active NSPH records", () => {
    const status = convertSphHandoffStatus(
      response({ format: "multicompo" }),
      input({
        sph_calculations: 0,
        sph_applied: true,
        sph_kind: "openmc-ce-mg-global",
      }),
    );
    expect(status).toMatchObject({
      title: "SPH-applied handoff detected",
      badge: "pre-applied XS route",
      tone: "ready",
    });
    expect(status?.output).toContain("L_MULTICOMPO");
    expect(status?.output).toContain("no downstream NSPH operation");
  });
});

function response(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: true,
    converted: false,
    format: "macrolib",
    writer_backend: "ascii",
    input_path: "/mock/mgxs_with_openmc_sph.h5",
    output_path: "/mock/out.macrolib.txt",
    summary_path: "/mock/convert_summary.json",
    summary_written: false,
    output_exists: false,
    output_size: null,
    preflight_ok: true,
    preflight: null,
    cli_command: ["openmc2donjon"],
    cli_command_text: "openmc2donjon",
    ...overrides,
  };
}

function input(overrides: Partial<ConvertPreflightInput> = {}): ConvertPreflightInput {
  return {
    path: "/mock/mgxs_with_openmc_sph.h5",
    ok: true,
    energy_groups: 33,
    legendre_order: 3,
    mixtures: 2,
    calculations: 2,
    state_points: 1,
    fissionable_mixtures: 1,
    adf_mixtures: 0,
    adf_faces: [],
    sph_calculations: 2,
    issues: [],
    warnings: [],
    ...overrides,
  };
}
