import type { ConvertResponse } from "@/lib/api";

export type ConvertRunState =
  | { kind: "idle" }
  | { kind: "loading"; mode: "dry-run" | "convert" }
  | { kind: "ok"; data: ConvertResponse }
  | { kind: "error"; message: string; status?: number };
