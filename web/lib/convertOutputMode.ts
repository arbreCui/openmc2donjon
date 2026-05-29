import type { ConvertResponse } from "./api";

export type ConvertOutputMode = "dry-run-ready" | "converted" | "blocked";

export function convertOutputMode(data: ConvertResponse): ConvertOutputMode {
  if (data.converted && data.output_exists) return "converted";
  if (data.ok && data.dry_run && !data.output_exists) return "dry-run-ready";
  return "blocked";
}
