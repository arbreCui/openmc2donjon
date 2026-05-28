import type { RefObject } from "react";

import type {
  ConvertFormat,
  ConvertWriterBackend,
} from "@/lib/api";
import {
  convertWriterBackendShortLabel,
} from "@/lib/convertWriterBackend";
import type { ConvertRunState } from "./ConvertReport";

export default function DirectConvertActionPanel({
  state,
  inputPath,
  outputPath,
  check,
  production,
  format,
  writerBackend,
  onConvert,
  convertButtonRef,
}: {
  state: ConvertRunState;
  inputPath: string;
  outputPath: string;
  check: boolean;
  production: boolean;
  format: ConvertFormat;
  writerBackend: ConvertWriterBackend;
  onConvert: () => void;
  convertButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  const hasInput = inputPath.trim().length > 0;
  const hasOutput = outputPath.trim().length > 0;
  const canRun = hasInput && hasOutput && state.kind !== "loading";
  const dryRunLoading = state.kind === "loading" && state.mode === "dry-run";
  const convertLoading = state.kind === "loading" && state.mode === "convert";
  const converted = state.kind === "ok" && state.data.converted && state.data.output_exists;
  const validated =
    state.kind === "ok" && state.data.preflight != null && state.data.preflight_ok;
  const validationFailed =
    (state.kind === "ok" && state.data.preflight != null && !state.data.preflight_ok) ||
    state.kind === "error";
  const object = format === "macrolib" ? "MACROLIB" : "MULTICOMPO";
  const checkMode = production ? "production" : check ? "standard" : "minimal";
  const writer = convertWriterBackendShortLabel(writerBackend);
  return (
    <section className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Direct convert action
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            Validate, then write the DONJON ASCII handoff
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Dry run is the safe no-write pass. Convert writes the selected{" "}
            {object} text file at the output path.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {object} · {writer} · {checkMode} checks
        </span>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-3">
        <ActionStep
          step="01"
          title="Select paths"
          body="Choose the MGXS HDF5 and the target ASCII filename."
          status={hasInput && hasOutput ? "ready" : "needed"}
        />
        <ActionStep
          step="02"
          title="Dry run"
          body="Run validation without creating or replacing the output file."
          status={validationFailed ? "failed" : validated ? "done" : "recommended"}
        />
        <ActionStep
          step="03"
          title="Convert"
          body={`Write the ${object} artifact for downstream DONJON use.`}
          status={converted ? "done" : canRun ? "ready" : "waiting"}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          className="btn btn-secondary"
          disabled={!canRun}
        >
          {dryRunLoading ? "Checking…" : "Dry run"}
        </button>
        <button
          ref={convertButtonRef}
          type="button"
          onClick={onConvert}
          className="btn btn-primary"
          disabled={!canRun}
        >
          {convertLoading ? "Converting…" : "Convert"}
        </button>
        <p className="text-[12px] leading-5 text-[var(--fg-3)]">
          You can convert directly, but a dry run gives a readable no-write
          record first.
        </p>
      </div>
    </section>
  );
}

function ActionStep({
  step,
  title,
  body,
  status,
}: {
  step: string;
  title: string;
  body: string;
  status: "needed" | "recommended" | "ready" | "waiting" | "done" | "failed";
}) {
  return (
    <article className={"rounded-lg border px-3 py-2 " + actionStepClass(status)}>
      <div className="flex items-center justify-between gap-3">
        <span className="rounded border border-current/25 px-1.5 py-0.5 font-mono text-[10px]">
          {step}
        </span>
        <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
          {status}
        </span>
      </div>
      <h3 className="mt-2 text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
    </article>
  );
}

function actionStepClass(status: "needed" | "recommended" | "ready" | "waiting" | "done" | "failed"): string {
  if (status === "done") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (status === "failed") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  if (status === "ready") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "recommended") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}
