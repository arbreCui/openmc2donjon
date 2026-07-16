import { describe, expect, it } from "vitest";
import type { ExecutionJob, TextPreview } from "./api";
import {
  NATIVE_SPH_TIMEOUT_SECONDS,
  buildNativeSphExecutionRequest,
  latestNativeSphJob,
  nativeSphArtifactDirectory,
  nativeSphDeckFilename,
  nativeSphDeckFilenameIssue,
  nativeSphDeckPathIssue,
  nativeSphJobIsActive,
  nativeSphJobMatchesDeclaration,
  nativeSphJobIsTerminal,
  nativeSphMissingValidationInputs,
  nativeSphPreviewIssue,
  nativeSphValidationHref,
  nativeSphValidationInputCount,
  nativeSphWorkingDirectory,
} from "./nativeSphRunner";

describe("native SPH runner helpers", () => {
  it("derives only a backend-safe .x2m filename", () => {
    expect(nativeSphDeckFilename("/runs/case/native_fpsph.x2m")).toBe(
      "native_fpsph.x2m",
    );
    expect(nativeSphDeckFilename("C:\\runs\\case\\native sph.x2m")).toBe(
      "native_sph.x2m",
    );
    expect(nativeSphDeckFilenameIssue("native_fpsph.x2m")).toBeNull();
    expect(nativeSphDeckFilenameIssue("../native_fpsph.x2m")).toContain(
      "simple .x2m filename",
    );
    expect(nativeSphDeckFilenameIssue("native_fpsph.X2M")).toContain(
      "simple .x2m filename",
    );
    expect(nativeSphDeckPathIssue("/runs/case/deck.txt")).toContain(".x2m");
  });

  it("refuses to run a truncated deck preview", () => {
    expect(nativeSphPreviewIssue(preview({ truncated: false }))).toBeNull();
    expect(
      nativeSphPreviewIssue(
        preview({ truncated: true, truncated_by: ["bytes", "lines"] }),
      ),
    ).toContain("not loaded or run");
  });

  it("archives project jobs under a project-local diagnostic run directory", () => {
    expect(nativeSphArtifactDirectory("/projects/pwr-case/")).toBe(
      "/projects/pwr-case/diagnostics/native-sph-runs",
    );
    expect(nativeSphArtifactDirectory("")).toBeUndefined();

    expect(
      buildNativeSphExecutionRequest({
        deckText: "SPH: ;\nQUIT .",
        deckFilename: " pwr_native_sph.x2m ",
        donjonRoot: " /opt/dragon-5.1 ",
        projectRoot: "/projects/pwr-case",
        componentId: "fullcore",
        sourceDeckPath: "/projects/pwr-case/decks/native.x2m",
        sourceDeckSha256: "a".repeat(64),
        workingDirectory: " /projects/pwr-case/decks ",
      }),
    ).toEqual({
      deck_text: "SPH: ;\nQUIT .",
      deck_filename: "pwr_native_sph.x2m",
      donjon_root: "/opt/dragon-5.1",
      artifact_directory:
        "/projects/pwr-case/diagnostics/native-sph-runs",
      working_directory: "/projects/pwr-case/decks",
      source_deck_path: "/projects/pwr-case/decks/native.x2m",
      source_deck_sha256: "a".repeat(64),
      project_root: "/projects/pwr-case",
      component_id: "fullcore",
      timeout_seconds: NATIVE_SPH_TIMEOUT_SECONDS,
      expect_k_effective: false,
    });
    expect(NATIVE_SPH_TIMEOUT_SECONDS).toBe(86_400);
  });

  it("derives an explicit working directory and recovers the latest run", () => {
    expect(nativeSphWorkingDirectory("/projects/pwr/decks/native.x2m")).toBe(
      "/projects/pwr/decks",
    );
    expect(nativeSphWorkingDirectory("native.x2m")).toBe("");
    expect(
      latestNativeSphJob([
        job({ job_id: "old", created_at: 1 }),
        job({ job_id: "new", created_at: 2 }),
      ])?.job_id,
    ).toBe("new");
    expect(
      nativeSphJobMatchesDeclaration(
        job({
          deck_path: "/archive/run-1/native.x2m",
          deck_sha256: "a".repeat(64),
          source_deck_path: "/projects/pwr/decks/native.x2m",
          project_root: "/projects/pwr",
          component_id: "fullcore",
          working_directory: "/projects/pwr/decks",
        }),
        "/projects/pwr/decks/native.x2m",
        "/projects/pwr/decks/",
        "/projects/pwr",
        "fullcore",
        "a".repeat(64),
      ),
    ).toBe(true);
    expect(
      nativeSphJobMatchesDeclaration(
        job({
          deck_path: "/archive/run-1/native.x2m",
          source_deck_path: "/projects/pwr/decks/native.x2m",
          project_root: "/projects/pwr",
          component_id: "fullcore",
          working_directory: "/projects/other",
        }),
        "/projects/pwr/decks/native.x2m",
        "/projects/pwr/decks",
        "/projects/pwr",
        "fullcore",
        "a".repeat(64),
      ),
    ).toBe(false);
  });

  it("keeps job completion separate from evidence validation", () => {
    expect(nativeSphJobIsActive(job({ status: "running" }))).toBe(true);
    expect(nativeSphJobIsTerminal(job({ status: "completed" }))).toBe(true);
    const declared = {
      reference_h5: "/runs/case/reference.h5",
      reference_macrolib: "/runs/case/reference.macrolib.txt",
      sph_macrolib: "/runs/case/native-sph.macrolib.txt",
      verify_macrolib: "/runs/case/verification.macrolib.txt",
      result_listing: "/runs/case/declared.result",
      execution_deck: "/runs/case/native_sph.x2m",
      energy_coverage: "/runs/case/energy-coverage.json",
      converter_receipt: "/runs/case/converter-receipt.json",
      summary_json: "/runs/case/physics-summary.json",
    };
    const validation = new URL(
      nativeSphValidationHref(
        declared,
        "/runs/case/current-job.result",
      ),
      "http://localhost",
    );
    expect(validation.pathname).toBe("/builder");
    expect(validation.searchParams.get("command")).toBe("validate-native-sph");
    expect(validation.searchParams.get("reference_h5")).toBe(
      "/runs/case/reference.h5",
    );
    expect(validation.searchParams.get("result_listing")).toBe(
      "/runs/case/current-job.result",
    );
    expect(validation.searchParams.get("summary_json")).toBe(
      "/runs/case/physics-summary.json",
    );
    expect(validation.searchParams.get("converter_receipt")).toBe(
      "/runs/case/converter-receipt.json",
    );
    expect(validation.searchParams.get("execution_deck")).toBe(
      "/runs/case/native_sph.x2m",
    );
    expect(nativeSphValidationInputCount(declared)).toBe(9);
    expect(nativeSphMissingValidationInputs(declared)).toEqual([]);
    expect(
      new URL(nativeSphValidationHref(declared), "http://localhost").searchParams.get(
        "result_listing",
      ),
    ).toBe("/runs/case/declared.result");
  });

  it("lists every missing validation field instead of enabling on one path", () => {
    const partial = { reference_h5: "/runs/case/reference.h5" };
    expect(nativeSphValidationInputCount(partial)).toBe(1);
    expect(nativeSphMissingValidationInputs(partial)).toEqual([
      "Converter reference MACROLIB",
      "native-SPH MACROLIB",
      "DONJON verification MACROLIB",
      "native-SPH / DONJON result listing",
      "exact CLE-2000 execution deck",
      "full-energy coverage JSON",
      "production Converter receipt",
      "validator output summary JSON",
    ]);
  });
});

function preview(overrides: Partial<TextPreview>): TextPreview {
  return {
    schema: "openmc2donjon.text-preview.v1",
    path: "/runs/case/native.x2m",
    file_size: 12,
    preview_bytes: 12,
    max_bytes: 262_144,
    displayed_lines: 2,
    decoded_lines: 2,
    max_lines: 2_000,
    truncated: false,
    truncated_by: [],
    sha256: "a".repeat(64),
    text: "SPH: ;\nQUIT .",
    ...overrides,
  };
}

function job(overrides: Partial<ExecutionJob>): ExecutionJob {
  return {
    schema: "openmc2donjon.web-donjon-job.v1",
    job_id: "job-1",
    run_id: "job-1",
    operation: "donjon",
    status: "queued",
    created_at: 1,
    started_at: null,
    finished_at: null,
    message: "Queued.",
    result_path: null,
    deck_path: null,
    k_effective: null,
    return_code: null,
    log_tail: "",
    working_directory: "/runs/case",
    archive_root: "/runs",
    run_directory: "/runs/job-1",
    request_path: "/runs/job-1/request.json",
    status_path: "/runs/job-1/status.json",
    artifacts_path: "/runs/job-1/artifacts.json",
    log_path: "/runs/job-1/run.log",
    staged_manifest_path: "/runs/job-1/staged-inputs.json",
    runtime_output_directory: "/runs/job-1/runtime-output",
    ...overrides,
  };
}
