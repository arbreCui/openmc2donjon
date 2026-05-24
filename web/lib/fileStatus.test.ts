import { describe, expect, it } from "vitest";
import type { FileStatus } from "./api";
import { fileStatusLabel, fileStatusTone, formatBytes } from "./fileStatus";

function status(overrides: Partial<FileStatus>): FileStatus {
  return {
    schema: "openmc2donjon.file-status.v1",
    path: "/x",
    exists: true,
    kind: "file",
    size: null,
    detail: null,
    ...overrides,
  };
}

describe("file status helpers", () => {
  it("formats file, directory, and missing states", () => {
    expect(fileStatusLabel(status({ kind: "file", size: 4096 }))).toBe(
      "file · 4.0 KiB",
    );
    expect(fileStatusLabel(status({ kind: "dir" }))).toBe("directory");
    expect(
      fileStatusLabel(status({ exists: false, kind: "missing" })),
    ).toBe("missing");
  });

  it("maps filesystem states to UI tones", () => {
    expect(fileStatusTone(status({ kind: "file" }))).toBe("ready");
    expect(fileStatusTone(status({ kind: "dir" }))).toBe("ready");
    expect(fileStatusTone(status({ exists: false, kind: "missing" }))).toBe(
      "missing",
    );
    expect(fileStatusTone(status({ kind: "unknown" }))).toBe("warning");
  });

  it("formats byte counts compactly", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KiB");
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MiB");
  });
});
