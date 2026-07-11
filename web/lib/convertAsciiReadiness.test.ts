import { describe, expect, it } from "vitest";
import type { ConvertResponse, FileStatus } from "./api";
import { convertAsciiReadiness } from "./convertAsciiReadiness";

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

function fileStatus(kind: FileStatus["kind"]): FileStatus {
  return {
    schema: "openmc2donjon.file-status.v1",
    path: "/runs/case/out.mcompo.txt",
    exists: kind !== "missing",
    kind,
    size: kind === "file" ? 1024 : null,
    detail: null,
  };
}

describe("convertAsciiReadiness", () => {
  it("describes a clean dry run as ready to write", () => {
    const readiness = convertAsciiReadiness(response());

    expect(readiness.tone).toBe("write");
    expect(readiness.label).toBe("ready to write");
    expect(readiness.previewAvailable).toBe(false);
    expect(readiness.title).toContain("L_MULTICOMPO");
    expect(readiness.body).toContain("Dry run passed");
  });

  it("warns when a dry run target already exists", () => {
    const readiness = convertAsciiReadiness(
      response({ output_exists: true }),
      { kind: "ok", status: fileStatus("file") },
    );

    expect(readiness.tone).toBe("warn");
    expect(readiness.label).toBe("target exists");
    expect(readiness.next).toContain("overwrite");
  });

  it("marks converted confirmed output as previewable", () => {
    const readiness = convertAsciiReadiness(
      response({
        dry_run: false,
        converted: true,
        output_exists: true,
        output_size: 1024,
      }),
      { kind: "ok", status: fileStatus("file") },
    );

    expect(readiness.tone).toBe("ready");
    expect(readiness.label).toBe("artifact ready");
    expect(readiness.previewAvailable).toBe(true);
    expect(readiness.next).toContain("bundle");
  });

  it("separates converter failure from unconfirmed output", () => {
    expect(
      convertAsciiReadiness(response({ ok: false, preflight_ok: false })).tone,
    ).toBe("blocked");

    const unconfirmed = convertAsciiReadiness(
      response({ dry_run: false, converted: true, output_exists: false }),
    );
    expect(unconfirmed.tone).toBe("warn");
    expect(unconfirmed.title).toContain("not confirmed");
  });

  it("reconciles a reported write against a probe that says missing", () => {
    const conflict = convertAsciiReadiness(
      response({ dry_run: false, converted: true, output_exists: true }),
      { kind: "ok", status: fileStatus("missing") },
    );

    expect(conflict.tone).toBe("warn");
    expect(conflict.label).toBe("verify path");
    expect(conflict.title).toContain("written this session");
    expect(conflict.title).toContain("file-status probe disagrees");
    expect(conflict.next).toContain("Check the output path");
    expect(conflict.previewAvailable).toBe(false);
  });
});
