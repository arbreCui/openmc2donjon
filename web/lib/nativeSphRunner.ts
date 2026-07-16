import type {
  DonjonExecutionRequest,
  ExecutionJob,
  TextPreview,
} from "./api";
import { containingDirectory } from "./outputBrowse";
import { projectPath } from "./projectWorkspace";

export const NATIVE_SPH_DEFAULT_DECK_FILENAME = "native_sph.x2m";
// Full-core transport/SPH solves routinely exceed one hour. Keep the UI value
// aligned with the backend's bounded 24-hour ceiling so a physical run is not
// killed merely because it is larger than a component smoke case.
export const NATIVE_SPH_TIMEOUT_SECONDS = 86_400;
export const NATIVE_SPH_PREVIEW_MAX_BYTES = 262_144;
export const NATIVE_SPH_PREVIEW_MAX_LINES = 2_000;

export interface NativeSphValidationInputs {
  reference_h5?: string;
  reference_macrolib?: string;
  sph_macrolib?: string;
  verify_macrolib?: string;
  result_listing?: string;
  execution_deck?: string;
  energy_coverage?: string;
  converter_receipt?: string;
  summary_json?: string;
}

export const NATIVE_SPH_VALIDATION_FIELDS = [
  ["reference_h5", "OpenMC fine-reference HDF5"],
  ["reference_macrolib", "Converter reference MACROLIB"],
  ["sph_macrolib", "native-SPH MACROLIB"],
  ["verify_macrolib", "DONJON verification MACROLIB"],
  ["result_listing", "native-SPH / DONJON result listing"],
  ["execution_deck", "exact CLE-2000 execution deck"],
  ["energy_coverage", "full-energy coverage JSON"],
  ["converter_receipt", "production Converter receipt"],
  ["summary_json", "validator output summary JSON"],
] as const satisfies readonly [keyof NativeSphValidationInputs, string][];

const NATIVE_SPH_VALIDATION_KEYS = NATIVE_SPH_VALIDATION_FIELDS.map(
  ([key]) => key,
) satisfies readonly (keyof NativeSphValidationInputs)[];

// Keep this byte-for-byte compatible with the existing backend guard.  The
// runner may load an upper-case source suffix, but the archived filename sent
// to /api/execute/donjon must use the backend's lower-case `.x2m` suffix.
const SIMPLE_X2M_FILENAME = /^[A-Za-z0-9][A-Za-z0-9_.-]*\.x2m$/;

export function nativeSphDeckFilename(path: string): string {
  const basename = path.trim().replace(/\\/g, "/").split("/").pop() ?? "";
  return SIMPLE_X2M_FILENAME.test(basename)
    ? basename
    : NATIVE_SPH_DEFAULT_DECK_FILENAME;
}

export function nativeSphDeckPathIssue(path: string): string | null {
  const trimmed = path.trim();
  if (!trimmed) return "Choose a native-SPH .x2m deck first.";
  if (!trimmed.toLowerCase().endsWith(".x2m")) {
    return "Native SPH deck path must end with .x2m.";
  }
  return null;
}

export function nativeSphDeckFilenameIssue(filename: string): string | null {
  const trimmed = filename.trim();
  if (!trimmed) return "Deck filename is required.";
  if (!SIMPLE_X2M_FILENAME.test(trimmed)) {
    return "Deck filename must be a simple .x2m filename without directories or spaces.";
  }
  return null;
}

export function nativeSphPreviewIssue(preview: TextPreview): string | null {
  if (!preview.truncated) return null;
  const limit = preview.truncated_by.join(" and ") || "preview limits";
  return (
    `The deck was truncated by ${limit}; it was not loaded or run. ` +
    "Use a complete .x2m deck within the bounded loader limits."
  );
}

export function nativeSphArtifactDirectory(
  projectRoot: string,
): string | undefined {
  const directory = projectPath(
    projectRoot,
    "diagnostics",
    "native-sph-runs",
  );
  return directory || undefined;
}

export function buildNativeSphExecutionRequest({
  deckText,
  deckFilename,
  donjonRoot,
  projectRoot,
  componentId,
  sourceDeckPath,
  sourceDeckSha256,
  workingDirectory,
}: {
  deckText: string;
  deckFilename: string;
  donjonRoot: string;
  projectRoot: string;
  componentId: string;
  sourceDeckPath: string;
  sourceDeckSha256: string;
  workingDirectory: string;
}): DonjonExecutionRequest {
  return {
    deck_text: deckText,
    deck_filename: deckFilename.trim(),
    donjon_root: donjonRoot.trim() || undefined,
    artifact_directory: nativeSphArtifactDirectory(projectRoot),
    working_directory: workingDirectory.trim() || undefined,
    source_deck_path: sourceDeckPath.trim() || undefined,
    source_deck_sha256: sourceDeckSha256.trim() || undefined,
    project_root: projectRoot.trim() || undefined,
    component_id: componentId.trim() || undefined,
    timeout_seconds: NATIVE_SPH_TIMEOUT_SECONDS,
    // A native-SPH deck may write its physical evidence without exposing a
    // generic k-effective marker.  The independent validator, not this job
    // transport, decides whether the required evidence is complete.
    expect_k_effective: false,
  };
}

export function nativeSphWorkingDirectory(deckPath: string): string {
  const trimmed = deckPath.trim();
  if (!trimmed) return "";
  const directory = containingDirectory(trimmed.replace(/\\/g, "/"));
  return directory === "~" ? "" : directory;
}

export function latestNativeSphJob(jobs: ExecutionJob[]): ExecutionJob | null {
  return (
    [...jobs].sort((left, right) => right.created_at - left.created_at)[0] ?? null
  );
}

export function nativeSphJobMatchesDeclaration(
  job: ExecutionJob,
  deckPath: string,
  workingDirectory: string,
  projectRoot = "",
  componentId = "",
  deckSha256 = "",
): boolean {
  const declaredDirectory = normalizedPath(workingDirectory);
  const jobDirectory = normalizedPath(job.working_directory ?? "");
  if (
    !declaredDirectory ||
    jobDirectory !== declaredDirectory ||
    normalizedPath(job.source_deck_path ?? "") !== normalizedPath(deckPath) ||
    normalizedPath(job.project_root ?? "") !== normalizedPath(projectRoot) ||
    (job.component_id ?? "") !== componentId.trim() ||
    (deckSha256 && job.deck_sha256 !== deckSha256) ||
    !job.deck_path
  ) {
    return false;
  }
  return nativeSphDeckFilename(job.deck_path) === nativeSphDeckFilename(deckPath);
}

function normalizedPath(value: string): string {
  const normalized = value.trim().replace(/\\/g, "/").replace(/\/+$/, "");
  return normalized || (value.trim() === "/" ? "/" : "");
}

export function nativeSphJobIsActive(job: ExecutionJob): boolean {
  return job.status === "queued" || job.status === "running";
}

export function nativeSphJobIsTerminal(job: ExecutionJob): boolean {
  return job.status === "completed" || job.status === "failed";
}

export function nativeSphValidationHref(
  declared: NativeSphValidationInputs = {},
  currentResultPath?: string | null,
): string {
  const params = new URLSearchParams({ command: "validate-native-sph" });
  const currentResult = currentResultPath?.trim() ?? "";
  for (const key of NATIVE_SPH_VALIDATION_KEYS) {
    const value =
      key === "result_listing" && currentResult
        ? currentResult
        : declared[key]?.trim() ?? "";
    if (value) params.set(key, value);
  }
  return `/builder?${params.toString()}`;
}

export function nativeSphValidationInputCount(
  declared: NativeSphValidationInputs,
  currentResultPath?: string | null,
): number {
  const currentResult = currentResultPath?.trim() ?? "";
  return NATIVE_SPH_VALIDATION_KEYS.filter((key) =>
    key === "result_listing" && currentResult
      ? true
      : Boolean(declared[key]?.trim()),
  ).length;
}

export function nativeSphMissingValidationInputs(
  declared: NativeSphValidationInputs,
  currentResultPath?: string | null,
): string[] {
  const currentResult = currentResultPath?.trim() ?? "";
  return NATIVE_SPH_VALIDATION_FIELDS.filter(([key]) =>
    key === "result_listing" && currentResult
      ? false
      : !declared[key]?.trim(),
  ).map(([, label]) => label);
}
