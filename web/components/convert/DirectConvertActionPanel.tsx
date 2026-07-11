import Link from "next/link";
import type { RefObject } from "react";

import type {
  ConvertFormat,
  ConvertWriterBackend,
} from "@/lib/api";
import { convertChecksLevel } from "@/lib/convertChecks";
import {
  convertWriterBackendShortLabel,
} from "@/lib/convertWriterBackend";
import type { ConvertRunState } from "./ConvertReportState";

export default function DirectConvertActionPanel({
  state,
  inputPath,
  outputPath,
  check,
  production,
  format,
  writerBackend,
  overwrite,
  onOverwriteChange,
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
  overwrite: boolean;
  onOverwriteChange: (value: boolean) => void;
  onConvert: () => void;
  convertButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  const hasInput = inputPath.trim().length > 0;
  const hasOutput = outputPath.trim().length > 0;
  const canRun = hasInput && hasOutput && state.kind !== "loading";
  const dryRunLoading = state.kind === "loading" && state.mode === "dry-run";
  const convertLoading = state.kind === "loading" && state.mode === "convert";
  const object = format === "macrolib" ? "MACROLIB" : "MULTICOMPO";
  const checksLevel = convertChecksLevel(check, production);
  const checksLabel =
    checksLevel === "none" ? "no checks" : `${checksLevel} checks`;
  const writer = convertWriterBackendShortLabel(writerBackend);
  return (
    <section className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Direct convert action
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            Validate, then write the DONJON ASCII output
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Dry run is the safe no-write pass. Convert writes the selected{" "}
            {object} text file at the output path.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {object} · {writer} · {checksLabel}
          </span>
          <Link
            href="/commands/direct-convert"
            className="text-[12px] font-medium text-[var(--accent-2)] hover:underline"
          >
            Command notes
          </Link>
        </div>
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
        <label className="flex items-center gap-2 text-[12px] text-[var(--fg-1)]">
          <input
            type="checkbox"
            checked={overwrite}
            onChange={(event) => onOverwriteChange(event.target.checked)}
            className="accent-emerald-500"
          />
          Overwrite existing output
        </label>
        <p className="text-[12px] leading-5 text-[var(--fg-3)]">
          You can convert directly, but a dry run gives a readable no-write
          record first.
        </p>
      </div>
    </section>
  );
}
