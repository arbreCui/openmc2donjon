import type { FileStatus } from "./api";

export type FileStatusTone = "ready" | "missing" | "warning";

export function fileStatusTone(status: FileStatus): FileStatusTone {
  if (!status.exists || status.kind === "missing") return "missing";
  if (status.kind === "file" || status.kind === "dir") return "ready";
  return "warning";
}

export function fileStatusLabel(status: FileStatus): string {
  if (!status.exists || status.kind === "missing") return "missing";
  if (status.kind === "dir") return "directory";
  if (status.kind === "file") {
    return status.size === null ? "file" : `file · ${formatBytes(status.size)}`;
  }
  return status.kind;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "unknown size";
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${formatUnit(kib)} KiB`;
  const mib = kib / 1024;
  if (mib < 1024) return `${formatUnit(mib)} MiB`;
  return `${formatUnit(mib / 1024)} GiB`;
}

function formatUnit(value: number): string {
  return value >= 10 ? value.toFixed(0) : value.toFixed(1);
}
