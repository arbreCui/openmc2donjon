import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput, ConvertResponse, FileStatus } from "./api";
import { convertArtifactStatusMapFromItems } from "./convertArtifactStatus";
import { buildConvertRunSummary } from "./convertRunSummary";

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
    preflight: {
      schema: "openmc2donjon.mgxs-input-contract.v1",
      decision: "mgxs_input_contract_passed",
      output_issue: null,
      inputs: [],
    },
    cli_command: [
      "openmc2donjon",
      "/runs/case/mgxs_library.h5",
      "--format",
      "multicompo",
      "--dry-run",
      "--check",
      "--production",
    ],
    cli_command_text:
      "openmc2donjon /runs/case/mgxs_library.h5 --format multicompo --dry-run --check --production",
    ...overrides,
  };
}

function input(overrides: Partial<ConvertPreflightInput> = {}): ConvertPreflightInput {
  return {
    path: "/runs/case/mgxs_library.h5",
    ok: true,
    energy_groups: 7,
    legendre_order: 1,
    energy_mesh_id: "casmo_7",
    energy_mesh_name: "CASMO-7",
    mixtures: 9,
    calculations: 9,
    state_points: 1,
    fissionable_mixtures: 4,
    adf_mixtures: 9,
    adf_faces: ["XMIN", "XMAX", "YMIN", "YMAX"],
    sph_calculations: 9,
    issues: [],
    warnings: [],
    ...overrides,
  };
}

function status(kind: FileStatus["kind"], path: string): FileStatus {
  return {
    schema: "openmc2donjon.file-status.v1",
    path,
    exists: kind !== "missing",
    kind,
    size: kind === "file" ? 4096 : null,
    detail: null,
  };
}

describe("convert run summary", () => {
  it("describes a production dry run without claiming a file was written", () => {
    const summary = buildConvertRunSummary(response(), input());

    expect(summary).toContain("run: dry run (no file written)");
    expect(summary).toContain("decision: PASS");
    expect(summary).toContain("preflight: pass");
    expect(summary).toContain(
      "production preset: requested (mgxs_input_contract_passed)",
    );
    expect(summary).toContain("ADF: 9 mixtures, faces XMIN, XMAX, YMIN, YMAX");
    expect(summary).toContain("SPH: 9 calculations");
    expect(summary).toContain("conversion summary: n/a");
    expect(summary).toContain("output size: n/a");
    expect(summary).toContain("input: not queried");
    expect(summary).toContain("--production");
  });

  it("includes copied artifact status for converted runs", () => {
    const statuses = convertArtifactStatusMapFromItems([
      {
        id: "input",
        state: {
          kind: "ok",
          status: status("file", "/runs/case/mgxs_library.h5"),
        },
      },
      {
        id: "output",
        state: { kind: "ok", status: status("file", "/runs/case/out.mcompo.txt") },
      },
      {
        id: "bundle",
        state: { kind: "ok", status: status("dir", "/runs/case/bundle") },
      },
    ]);
    const summary = buildConvertRunSummary(
      response({
        dry_run: false,
        converted: true,
        output_exists: true,
        output_size: 4096,
        summary_path: "/runs/case/convert_summary.json",
        summary_written: true,
      }),
      input({ adf_mixtures: 0, adf_faces: [], sph_calculations: 0 }),
      statuses,
    );

    expect(summary).toContain("run: converted (ASCII written)");
    expect(summary).toContain("conversion summary: /runs/case/convert_summary.json");
    expect(summary).toContain("output size: 4.0 KiB");
    expect(summary).toContain("ADF: none recorded");
    expect(summary).toContain("SPH: none recorded");
    expect(summary).toContain("input: file");
    expect(summary).toContain("output: file");
    expect(summary).toContain("bundle: directory");
  });
});
