import { describe, expect, it } from "vitest";
import type { ConvertResponse, FileStatus } from "./api";
import {
  convertArtifactPaths,
  convertArtifactStatusMapFromItems,
  convertArtifactStatusSummary,
  convertArtifactStatusText,
  convertOutputPresence,
  loadingConvertArtifactStatuses,
} from "./convertArtifactStatus";

function response(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: false,
    converted: true,
    format: "multicompo",
    writer_backend: "ascii",
    input_path: "/runs/case/mgxs_library.h5",
    output_path: "/runs/case/out.mcompo.txt",
    summary_path: null,
    summary_written: false,
    output_exists: true,
    output_size: 2048,
    preflight_ok: true,
    preflight: null,
    cli_command: ["openmc2donjon", "/runs/case/mgxs_library.h5"],
    cli_command_text: "openmc2donjon /runs/case/mgxs_library.h5",
    ...overrides,
  };
}

function status(
  kind: FileStatus["kind"],
  overrides: Partial<FileStatus> = {},
): FileStatus {
  return {
    schema: "openmc2donjon.file-status.v1",
    path: "/runs/case/file",
    exists: kind !== "missing",
    kind,
    size: null,
    detail: null,
    ...overrides,
  };
}

describe("convert artifact status helpers", () => {
  it("derives input, output, and sibling bundle paths", () => {
    expect(convertArtifactPaths(response())).toEqual({
      input: "/runs/case/mgxs_library.h5",
      output: "/runs/case/out.mcompo.txt",
      bundle: "/runs/case/bundle",
    });
  });

  it("builds complete status maps from partial fetch results", () => {
    const map = convertArtifactStatusMapFromItems([
      { id: "output", state: { kind: "ok", status: status("file") } },
    ]);
    expect(map.input.kind).toBe("loading");
    expect(map.output.kind).toBe("ok");
    expect(map.bundle.kind).toBe("loading");
  });

  it("summarizes ready, partial, and loading states", () => {
    const loading = loadingConvertArtifactStatuses();
    expect(convertArtifactStatusSummary(loading)).toContain("Checking");

    const outputOnly = convertArtifactStatusMapFromItems([
      { id: "input", state: { kind: "ok", status: status("file") } },
      { id: "output", state: { kind: "ok", status: status("file") } },
      { id: "bundle", state: { kind: "ok", status: status("missing") } },
    ]);
    expect(convertArtifactStatusSummary(outputOnly)).toContain("ASCII output is present");

    const ready = convertArtifactStatusMapFromItems([
      { id: "input", state: { kind: "ok", status: status("file") } },
      { id: "output", state: { kind: "ok", status: status("file") } },
      { id: "bundle", state: { kind: "ok", status: status("dir") } },
    ]);
    expect(convertArtifactStatusSummary(ready)).toContain("bundle directory");
  });

  it("reconciles the convert response with the file-status probe", () => {
    // Response is authoritative: a reported write stays "existing" while the
    // probe is loading or errored.
    expect(convertOutputPresence(response(), { kind: "loading" })).toBe(
      "unverified",
    );
    expect(
      convertOutputPresence(response(), { kind: "error", message: "boom" }),
    ).toBe("unverified");
    expect(
      convertOutputPresence(response(), { kind: "ok", status: status("file") }),
    ).toBe("confirmed");
    // Probe positively reporting missing after the write is a conflict, not
    // an absolute "not present" claim.
    expect(
      convertOutputPresence(response(), {
        kind: "ok",
        status: status("missing"),
      }),
    ).toBe("conflict");
    expect(
      convertOutputPresence(response({ converted: false, output_exists: false }), {
        kind: "ok",
        status: status("missing"),
      }),
    ).toBe("absent");
  });

  it("summarizes a response/probe conflict as one reconciled state", () => {
    const probeMissing = convertArtifactStatusMapFromItems([
      { id: "input", state: { kind: "ok", status: status("file") } },
      { id: "output", state: { kind: "ok", status: status("missing") } },
      { id: "bundle", state: { kind: "ok", status: status("missing") } },
    ]);
    expect(convertArtifactStatusSummary(probeMissing, "conflict")).toBe(
      "Convert reported the ASCII write, but the file-status probe does not see the file — check the output path.",
    );
    expect(convertArtifactStatusSummary(probeMissing)).toContain(
      "not present yet",
    );
  });

  it("renders compact status text for copied summaries", () => {
    expect(convertArtifactStatusText({ kind: "loading" })).toBe("checking");
    expect(
      convertArtifactStatusText({
        kind: "error",
        message: "permission denied",
      }),
    ).toBe("unknown (permission denied)");
    expect(
      convertArtifactStatusText({
        kind: "ok",
        status: status("file", { size: 1024 }),
      }),
    ).toBe("file · 1.0 KiB");
  });
});
