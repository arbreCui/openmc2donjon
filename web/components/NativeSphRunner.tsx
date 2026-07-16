"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import NativeSphJobStatus from "@/components/NativeSphJobStatus";
import { ApiError, api, type ExecutionJob } from "@/lib/api";
import {
  NATIVE_SPH_PREVIEW_MAX_BYTES,
  NATIVE_SPH_PREVIEW_MAX_LINES,
  NATIVE_SPH_TIMEOUT_SECONDS,
  NATIVE_SPH_VALIDATION_FIELDS,
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
  type NativeSphValidationInputs,
} from "@/lib/nativeSphRunner";
import { containingDirectory } from "@/lib/outputBrowse";
import { useSettings } from "@/lib/settings";

type DeckLoadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | {
      kind: "loaded";
      path: string;
      bytes: number;
      lines: number;
      sha256: string;
    }
  | { kind: "error"; message: string };

type NativeSphRunState =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "job"; data: ExecutionJob }
  | { kind: "error"; message: string };

export default function NativeSphRunner({
  projectRoot,
  componentId = "",
  initialDeckPath = "",
  initialWorkingDirectory = "",
  projectDeclared = false,
  validationInputs = {},
}: {
  projectRoot: string;
  componentId?: string;
  initialDeckPath?: string;
  initialWorkingDirectory?: string;
  projectDeclared?: boolean;
  validationInputs?: NativeSphValidationInputs;
}) {
  const [settings] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const [deckPath, setDeckPath] = useState(initialDeckPath);
  const [deckText, setDeckText] = useState("");
  const [deckFilename, setDeckFilename] = useState(() =>
    nativeSphDeckFilename(initialDeckPath),
  );
  const [filenameTouched, setFilenameTouched] = useState(false);
  const [workingDirectory, setWorkingDirectory] = useState(() =>
    initialWorkingDirectory.trim() || nativeSphWorkingDirectory(initialDeckPath),
  );
  const [workingDirectoryTouched, setWorkingDirectoryTouched] = useState(
    Boolean(initialWorkingDirectory.trim()),
  );
  const [browserOpen, setBrowserOpen] = useState(false);
  const [loadState, setLoadState] = useState<DeckLoadState>({ kind: "idle" });
  const [runState, setRunState] = useState<NativeSphRunState>({ kind: "idle" });
  const [knownJobs, setKnownJobs] = useState<ExecutionJob[]>([]);
  const [recoveringJobs, setRecoveringJobs] = useState(false);
  const [recoveryIssue, setRecoveryIssue] = useState<string | null>(null);
  const [runnerOpen, setRunnerOpen] = useState(projectDeclared);

  const jobActive =
    runState.kind === "starting" ||
    (runState.kind === "job" && nativeSphJobIsActive(runState.data));
  const filenameIssue = nativeSphDeckFilenameIssue(deckFilename);
  const canRun =
    loadState.kind === "loaded" &&
    deckText.trim().length > 0 &&
    filenameIssue === null &&
    workingDirectory.trim().length > 0 &&
    !jobActive;
  const artifactDirectory = nativeSphArtifactDirectory(projectRoot);
  const terminalJob =
    runState.kind === "job" && nativeSphJobIsTerminal(runState.data)
      ? runState.data
      : null;
  const currentResultPath = terminalJob?.result_path ?? null;
  const effectiveValidationInputs: NativeSphValidationInputs = {
    ...validationInputs,
    execution_deck:
      validationInputs.execution_deck?.trim() ||
      (loadState.kind === "loaded" ? loadState.path : ""),
  };
  const validationInputCount = nativeSphValidationInputCount(
    effectiveValidationInputs,
    currentResultPath,
  );
  const missingValidationInputs = nativeSphMissingValidationInputs(
    effectiveValidationInputs,
    currentResultPath,
  );
  const canOpenValidation = !jobActive && missingValidationInputs.length === 0;

  useEffect(() => {
    const declaredPath = initialDeckPath.trim();
    if (!projectDeclared || !declaredPath) return;
    let cancelled = false;
    setRunnerOpen(true);
    setDeckPath(declaredPath);
    setDeckText("");
    setLoadState({ kind: "loading" });
    setDeckFilename(nativeSphDeckFilename(declaredPath));
    setWorkingDirectory(
      initialWorkingDirectory.trim() || nativeSphWorkingDirectory(declaredPath),
    );
    setWorkingDirectoryTouched(Boolean(initialWorkingDirectory.trim()));
    api
      .textPreview(
        declaredPath,
        NATIVE_SPH_PREVIEW_MAX_BYTES,
        NATIVE_SPH_PREVIEW_MAX_LINES,
      )
      .then((preview) => {
        if (cancelled) return;
        const previewIssue = nativeSphPreviewIssue(preview);
        if (previewIssue) {
          setLoadState({ kind: "error", message: previewIssue });
          return;
        }
        if (!preview.sha256) {
          setLoadState({
            kind: "error",
            message: "The complete deck did not include a source SHA-256 binding.",
          });
          return;
        }
        setDeckText(preview.text);
        setDeckPath(preview.path);
        setDeckFilename(nativeSphDeckFilename(preview.path));
        setLoadState({
          kind: "loaded",
          path: preview.path,
          bytes: preview.preview_bytes,
          lines: preview.displayed_lines,
          sha256: preview.sha256,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        setDeckText("");
        setLoadState({
          kind: "error",
          message: nativeSphExecutionError(
            error,
            "The Project-declared .x2m deck could not be loaded.",
          ),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [initialDeckPath, initialWorkingDirectory, projectDeclared]);

  useEffect(() => {
    if (!artifactDirectory) return;
    if (projectDeclared && loadState.kind !== "loaded") {
      setKnownJobs([]);
      setRunState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setRecoveringJobs(true);
    setRecoveryIssue(null);
    api
      .executionJobs(artifactDirectory)
      .then((response) => {
        if (cancelled) return;
        const relevantJobs = projectDeclared
          ? response.jobs.filter((job) =>
              nativeSphJobMatchesDeclaration(
                job,
                loadState.kind === "loaded" ? loadState.path : initialDeckPath,
                workingDirectory,
                projectRoot,
                componentId,
                loadState.kind === "loaded" ? loadState.sha256 : "",
              ),
            )
          : response.jobs;
        setKnownJobs(relevantJobs);
        const latest = latestNativeSphJob(relevantJobs);
        if (latest) setRunState({ kind: "job", data: latest });
      })
      .catch((error) => {
        if (!cancelled) {
          setRecoveryIssue(
            nativeSphExecutionError(error, "Could not recover project run records."),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setRecoveringJobs(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    artifactDirectory,
    componentId,
    initialDeckPath,
    loadState,
    projectRoot,
    projectDeclared,
    workingDirectory,
  ]);

  useEffect(() => {
    if (runState.kind !== "job" || !nativeSphJobIsActive(runState.data)) return;
    const jobId = runState.data.job_id;
    const timer = window.setTimeout(() => {
      api
        .executionJob(jobId, artifactDirectory)
        .then((data) => {
          setRunState({ kind: "job", data });
          setKnownJobs((current) => rememberJob(current, data));
        })
        .catch((error) =>
          setRunState({
            kind: "error",
            message: nativeSphExecutionError(error, "Could not poll the DONJON job."),
          }),
        );
    }, 2_000);
    return () => window.clearTimeout(timer);
  }, [artifactDirectory, runState]);

  function updateDeckPath(value: string) {
    setDeckPath(value);
    setDeckText("");
    setLoadState({ kind: "idle" });
    setRunState({ kind: "idle" });
    if (!filenameTouched) setDeckFilename(nativeSphDeckFilename(value));
    if (!workingDirectoryTouched) {
      setWorkingDirectory(nativeSphWorkingDirectory(value));
    }
  }

  async function loadDeck() {
    const pathIssue = nativeSphDeckPathIssue(deckPath);
    if (pathIssue) {
      setLoadState({ kind: "error", message: pathIssue });
      return;
    }
    setLoadState({ kind: "loading" });
    setRunState({ kind: "idle" });
    try {
      const preview = await api.textPreview(
        deckPath.trim(),
        NATIVE_SPH_PREVIEW_MAX_BYTES,
        NATIVE_SPH_PREVIEW_MAX_LINES,
      );
      const previewIssue = nativeSphPreviewIssue(preview);
      if (previewIssue) {
        setDeckText("");
        setLoadState({ kind: "error", message: previewIssue });
        return;
      }
      if (!preview.sha256) {
        setDeckText("");
        setLoadState({
          kind: "error",
          message: "The complete deck did not include a source SHA-256 binding.",
        });
        return;
      }
      setDeckText(preview.text);
      setDeckPath(preview.path);
      if (!filenameTouched) setDeckFilename(nativeSphDeckFilename(preview.path));
      if (!workingDirectoryTouched) {
        setWorkingDirectory(nativeSphWorkingDirectory(preview.path));
      }
      setLoadState({
        kind: "loaded",
        path: preview.path,
        bytes: preview.preview_bytes,
        lines: preview.displayed_lines,
        sha256: preview.sha256,
      });
    } catch (error) {
      setDeckText("");
      setLoadState({
        kind: "error",
        message: nativeSphExecutionError(error, "Could not load the .x2m deck."),
      });
    }
  }

  async function runNativeSph() {
    if (!canRun) return;
    setRunState({ kind: "starting" });
    try {
      const data = await api.executeDonjon(
        buildNativeSphExecutionRequest({
          deckText,
          deckFilename,
          donjonRoot: "",
          projectRoot,
          componentId,
          sourceDeckPath: loadState.kind === "loaded" ? loadState.path : "",
          sourceDeckSha256:
            loadState.kind === "loaded" ? loadState.sha256 : "",
          workingDirectory,
        }),
      );
      setRunState({ kind: "job", data });
      setKnownJobs((current) => rememberJob(current, data));
    } catch (error) {
      setRunState({
        kind: "error",
        message: nativeSphExecutionError(error, "DONJON could not start."),
      });
    }
  }

  return (
    <details
      open={runnerOpen}
      onToggle={(event) => setRunnerOpen(event.currentTarget.open)}
      className="mt-4 rounded-xl border border-[var(--edge)] bg-black/10 p-3"
    >
      <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
        {projectDeclared
          ? "Run the Project-declared native-SPH deck"
          : "Run a standalone native-SPH deck"}
      </summary>
      <div className="mt-4 grid gap-3">
        {projectDeclared ? (
          <div className="rounded-lg border border-cyan-300/20 bg-cyan-300/[0.05] px-3 py-2 text-[11px] leading-5 text-cyan-50">
            Source: <code>openmc2donjon.project.json</code>
            {componentId ? <> · component <code>{componentId}</code></> : null}.
            The deck and working directory below were resolved by the backend
            inside the Project root and the deck was loaded automatically. A
            declared or loaded path is not evidence that the solve or physics
            acceptance passed. Change these paths in the manifest rather than
            silently substituting another deck here.
          </div>
        ) : null}
        <div className="rounded-lg border border-amber-300/20 bg-amber-300/[0.055] px-3 py-2 text-[11px] leading-5 text-amber-100">
          {projectDeclared ? "The Project" : "You"} declare this deck, its coarse geometry, mixtures,
          SN/SPN method, and boundary conditions. The generic DONJON smoke deck
          cannot replace a native <span className="font-mono">SPH:</span> solve.
        </div>

        <RunnerStep number="1" title="Load deck">
          <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="block">
              <span className="text-[12px] font-semibold text-[var(--fg-1)]">
                {projectDeclared ? "Project-declared .x2m path" : "Native-SPH .x2m path"}
              </span>
              <input
                value={deckPath}
                disabled={jobActive || projectDeclared}
                onChange={(event) => updateDeckPath(event.target.value)}
                placeholder="/path/to/project_native_sph.x2m"
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)] disabled:opacity-50"
              />
            </label>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={jobActive || projectDeclared}
              onClick={() => setBrowserOpen(true)}
            >
              Browse .x2m
            </button>
          </div>
          <button
            type="button"
            className="btn btn-secondary mt-3"
            disabled={loadState.kind === "loading" || jobActive}
            onClick={() => void loadDeck()}
          >
            {loadState.kind === "loading" ? "Loading deck…" : "Load deck"}
          </button>
          {loadState.kind === "loaded" ? (
            <div className="mt-3 rounded-md border border-emerald-300/20 bg-emerald-300/[0.05] px-3 py-2 text-[11px] text-emerald-100">
              Loaded the complete deck · {loadState.bytes.toLocaleString()} bytes ·{" "}
              {loadState.lines.toLocaleString()} lines
            </div>
          ) : loadState.kind === "error" ? (
            <div className="mt-3 rounded-md border border-rose-300/20 bg-rose-300/[0.06] px-3 py-2 text-[11px] text-rose-100">
              {loadState.message}
            </div>
          ) : null}
          {loadState.kind === "loaded" ? (
            <details className="mt-3 rounded-md border border-[var(--edge)] bg-black/10 p-3">
              <summary className="cursor-pointer text-[11px] font-semibold text-[var(--fg-2)]">
                Review the exact loaded deck text
              </summary>
              <textarea
                value={deckText}
                disabled={jobActive}
                readOnly
                rows={14}
                spellCheck={false}
                className="mt-3 w-full rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 font-mono text-[11px] leading-5 text-[var(--fg-1)] disabled:opacity-50"
              />
              <p className="mt-2 text-[10px] leading-4 text-[var(--fg-3)]">
                The Run action submits these exact source bytes and binds their
                SHA-256 to the job. Update the source deck, then reload it; the
                runner does not create an untracked browser-only deck variant.
              </p>
            </details>
          ) : null}
        </RunnerStep>

        <RunnerStep number="2" title="Run native SPH">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block">
              <span className="text-[12px] font-semibold text-[var(--fg-1)]">
                Archived deck filename
              </span>
              <input
                value={deckFilename}
                disabled={jobActive}
                onChange={(event) => {
                  setDeckFilename(event.target.value);
                  setFilenameTouched(true);
                }}
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)] disabled:opacity-50"
              />
              {filenameIssue ? (
                <span className="mt-1 block text-[10px] text-rose-200">
                  {filenameIssue}
                </span>
              ) : null}
            </label>
            <label className="block">
              <span className="text-[12px] font-semibold text-[var(--fg-1)]">
                Working directory (required)
              </span>
              <input
                value={workingDirectory}
                disabled={jobActive || projectDeclared}
                onChange={(event) => {
                  setWorkingDirectory(event.target.value);
                  setWorkingDirectoryTouched(true);
                }}
                placeholder="Directory that owns the deck's relative files"
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)] disabled:opacity-50"
              />
              <span className="mt-1 block text-[10px] leading-4 text-[var(--fg-3)]">
                Relative FILE paths are resolved only inside this directory. The
                backend snapshots regular files, rejects symlinks and escapes,
                and archives new runtime files without writing them back here.
              </span>
            </label>
          </div>
          <p className="mt-3 text-[10px] leading-4 text-[var(--fg-3)]">
            {artifactDirectory ? (
              <>
                Every submission gets a dedicated, SHA-256-indexed run archive under{" "}
                <code>{artifactDirectory}/&lt;run-id&gt;</code>, with request,
                status, deck, bounded log, result, and SHA-256 artifact manifest.
              </>
            ) : (
              "No Project context is active; the backend keeps the normal DONJON job paths."
            )}{" "}
            The solver-process timeout is {NATIVE_SPH_TIMEOUT_SECONDS.toLocaleString()} seconds
            (24 hours), the bounded backend maximum for a full-core solve; queue and
            snapshot preparation are reported separately.
          </p>
          <button
            type="button"
            className="btn btn-primary mt-3"
            disabled={!canRun}
            onClick={() => void runNativeSph()}
          >
            {runState.kind === "starting"
              ? "Starting native SPH…"
              : runState.kind === "job" && nativeSphJobIsActive(runState.data)
                ? "Native SPH running…"
                : "Run native SPH"}
          </button>
          {!canRun && loadState.kind !== "loaded" ? (
            <p className="mt-2 text-[10px] text-[var(--fg-3)]">
              Load a complete deck before starting the solver.
            </p>
          ) : null}
          {!workingDirectory.trim() ? (
            <p className="mt-2 text-[10px] text-rose-200">
              Declare the deck working directory before running; the backend will
              not guess relative-file semantics.
            </p>
          ) : null}
        </RunnerStep>

        <RunnerStep number="3" title="Job status, log, and result">
          {artifactDirectory ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="text-[10px] text-[var(--fg-3)]">
                {recoveringJobs
                  ? "Recovering project run records…"
                  : recoveryIssue
                    ? `Run recovery failed: ${recoveryIssue}`
                  : `${knownJobs.length} persisted project run${knownJobs.length === 1 ? "" : "s"}`}
              </span>
              {knownJobs.length > 1 ? (
                <select
                  aria-label="Persisted native SPH run"
                  value={runState.kind === "job" ? runState.data.job_id : ""}
                  onChange={(event) => {
                    const selected = knownJobs.find(
                      (job) => job.job_id === event.target.value,
                    );
                    if (selected) setRunState({ kind: "job", data: selected });
                  }}
                  className="rounded-md border border-[var(--edge)] bg-black/20 px-2 py-1 font-mono text-[10px] text-[var(--fg-1)]"
                >
                  {knownJobs.map((job) => (
                    <option key={job.job_id} value={job.job_id}>
                      {job.job_id} · {job.status}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
          ) : null}
          {runState.kind === "job" ? (
            <NativeSphJobStatus job={runState.data} />
          ) : runState.kind === "starting" ? (
            <p className="text-[11px] text-[var(--fg-2)]">Submitting the deck…</p>
          ) : runState.kind === "error" ? (
            <div className="rounded-md border border-rose-300/20 bg-rose-300/[0.06] px-3 py-2 text-[11px] text-rose-100">
              {runState.message}
            </div>
          ) : (
            <p className="text-[11px] text-[var(--fg-3)]">
              No native-SPH job has been started from this panel.
            </p>
          )}
        </RunnerStep>

        <RunnerStep number="4" title="Validate evidence">
          <p className="text-[11px] leading-5 text-[var(--fg-2)]">
            A completed process is not an accepted component or full-core result.
            The validator separately checks the Converter reference, native-SPH
            factors, solver convergence, DONJON verification, and declared
            physical tolerances.
          </p>
          {canOpenValidation ? (
            <Link
              href={nativeSphValidationHref(effectiveValidationInputs, currentResultPath)}
              className="btn btn-secondary mt-3"
            >
              Validate evidence
            </Link>
          ) : (
            <button type="button" className="btn btn-secondary mt-3" disabled>
              Validate evidence
            </button>
          )}
          <span className="ml-2 text-[10px] text-[var(--fg-3)]">
            {validationInputCount}/{NATIVE_SPH_VALIDATION_FIELDS.length} required validator fields prefilled
            {currentResultPath
              ? " · current job result overrides the supplied result evidence"
              : validationInputs.result_listing?.trim()
                ? ` · using the ${projectDeclared ? "Project-declared" : "supplied standalone"} result evidence`
                : ""}
          </span>
          {!canOpenValidation ? (
            <div className="mt-3 rounded-md border border-amber-300/20 bg-amber-300/[0.05] px-3 py-2 text-[10px] leading-4 text-amber-100">
              {jobActive ? (
                "Validation remains disabled while the current job is running."
              ) : (
                <>
                  The independent validator opens only when every required field is
                  bound. Missing: {missingValidationInputs.join(", ")}.
                </>
              )}
            </div>
          ) : null}
        </RunnerStep>
      </div>

      <FileBrowserModal
        open={browserOpen}
        initialPath={containingDirectory(deckPath.trim() || savedPrefix || "~")}
        extensions={["x2m"]}
        fileTypeLabel="native SPH deck"
        chipLabel="X2M"
        recentScope="native-sph-deck"
        onClose={() => setBrowserOpen(false)}
        onSelect={(path) => {
          updateDeckPath(path);
          setBrowserOpen(false);
        }}
      />
    </details>
  );
}

function RunnerStep({
  number,
  title,
  children,
}: {
  number: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-3">
      <div className="mb-3 flex items-center gap-2">
        <span className="step-dot h-6 w-6 text-[9px]">{number}</span>
        <h3 className="text-[12px] font-bold text-[var(--fg-0)]">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function nativeSphExecutionError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

function rememberJob(current: ExecutionJob[], incoming: ExecutionJob): ExecutionJob[] {
  return [
    incoming,
    ...current.filter((job) => job.job_id !== incoming.job_id),
  ].sort((left, right) => right.created_at - left.created_at);
}
