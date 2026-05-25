import { ApiError, ConvertResponse, api } from "./api";
import { convertBundleOutputDir } from "./convertNextSteps";
import {
  fileStatusIsDirectory,
  fileStatusIsFile,
  fileStatusLabel,
  type FileStatusState,
} from "./fileStatus";

export const CONVERT_ARTIFACT_STATUS_IDS = ["input", "output", "bundle"] as const;
export type ConvertArtifactStatusId = (typeof CONVERT_ARTIFACT_STATUS_IDS)[number];
export type ConvertArtifactStatusMap = Record<ConvertArtifactStatusId, FileStatusState>;
export type ConvertArtifactPathMap = Record<ConvertArtifactStatusId, string>;

export function convertArtifactPaths(data: ConvertResponse): ConvertArtifactPathMap {
  return {
    input: data.input_path,
    output: data.output_path,
    bundle: convertBundleOutputDir(data),
  };
}

export function loadingConvertArtifactStatuses(): ConvertArtifactStatusMap {
  return {
    input: { kind: "loading" },
    output: { kind: "loading" },
    bundle: { kind: "loading" },
  };
}

export function convertArtifactStatusMapFromItems(
  items: readonly { id: ConvertArtifactStatusId; state: FileStatusState }[],
): ConvertArtifactStatusMap {
  const next = loadingConvertArtifactStatuses();
  for (const item of items) {
    next[item.id] = item.state;
  }
  return next;
}

export async function fetchConvertArtifactStatuses(
  paths: ConvertArtifactPathMap,
): Promise<ConvertArtifactStatusMap> {
  const items = await Promise.all(
    CONVERT_ARTIFACT_STATUS_IDS.map(async (id) => {
      try {
        return {
          id,
          state: {
            kind: "ok",
            status: await api.fileStatus(paths[id]),
          } satisfies FileStatusState,
        };
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.detail ?? err.message
            : err instanceof Error
              ? err.message
              : "status check failed";
        return {
          id,
          state: { kind: "error", message } satisfies FileStatusState,
        };
      }
    }),
  );
  return convertArtifactStatusMapFromItems(items);
}

export function convertArtifactStatusSummary(
  statuses: ConvertArtifactStatusMap,
): string {
  const loading = CONVERT_ARTIFACT_STATUS_IDS.some(
    (id) => statuses[id].kind === "loading",
  );
  if (loading) return "Checking input, output, and bundle paths...";
  const errors = CONVERT_ARTIFACT_STATUS_IDS.filter(
    (id) => statuses[id].kind === "error",
  );
  if (errors.length > 0) {
    return `${errors.length} file-status check${errors.length === 1 ? "" : "s"} failed.`;
  }
  const outputReady = fileStatusIsFile(statuses.output);
  const bundleReady = fileStatusIsDirectory(statuses.bundle);
  if (outputReady && bundleReady) {
    return "ASCII output and bundle directory are present on disk.";
  }
  if (outputReady) {
    return "ASCII output is present; the bundle directory is still a builder target.";
  }
  return "ASCII output is not present yet; preview and bundling wait for conversion.";
}

export function convertArtifactStatusText(state: FileStatusState): string {
  if (state.kind === "loading") return "checking";
  if (state.kind === "error") return `unknown (${state.message})`;
  return fileStatusLabel(state.status);
}
