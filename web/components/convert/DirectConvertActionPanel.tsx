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
  onConvert,
  convertButtonRef,
  requireAppliedRateSph = false,
  requireMulticompo = false,
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
  requireAppliedRateSph?: boolean;
  requireMulticompo?: boolean;
}) {
  const hasInput = inputPath.trim().length > 0;
  const hasOutput = outputPath.trim().length > 0;
  const canRun = hasInput && hasOutput && state.kind !== "loading";
  const dryRunLoading = state.kind === "loading" && state.mode === "dry-run";
  const convertLoading = state.kind === "loading" && state.mode === "convert";
  const inspectedInput =
    state.kind === "ok" ? state.data.preflight?.inputs[0] ?? null : null;
  const appliedRateSphReady = Boolean(
    inspectedInput?.sph_applied &&
      inspectedInput.sph_applied_source?.trim() &&
      inspectedInput.sph_kind?.toLowerCase().includes("rate"),
  );
  const baseValidated =
    state.kind === "ok" && state.data.dry_run && state.data.preflight_ok;
  const blockedBySph =
    requireAppliedRateSph && baseValidated && !appliedRateSphReady;
  const blockedByFormat = requireMulticompo && format !== "multicompo";
  const validated = baseValidated && !blockedBySph && !blockedByFormat;
  const converted =
    state.kind === "ok" && !state.data.dry_run && state.data.preflight_ok;
  const object = format === "macrolib" ? "MACROLIB" : "MULTICOMPO";
  const checksLevel = convertChecksLevel(check, production);
  const productionChecks = checksLevel === "production";
  const standardChecks = checksLevel === "standard";
  const checksLabel =
    checksLevel === "none" ? "no checks" : `${checksLevel} checks`;
  const writer = convertWriterBackendShortLabel(writerBackend);
  return (
    <section className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Converter action
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {blockedByFormat
              ? "Colorset production requires L_MULTICOMPO"
              : blockedBySph
                ? "Physical SPH provenance is incomplete"
                : converted
                  ? productionChecks
                    ? "Production handoff artifact is ready"
                    : standardChecks
                      ? "Engineering output written — not production accepted"
                      : "Diagnostic output written — not production accepted"
              : validated
                ? productionChecks
                  ? "Production handoff gate passed — run Converter"
                  : standardChecks
                    ? "Engineering preflight passed — not production accepted"
                    : "No-check dry run completed"
                : requireAppliedRateSph
                  ? "Validate the SPH-applied HDF5"
                  : productionChecks
                    ? "Run production validation"
                    : standardChecks
                      ? "Run engineering preflight"
                      : "Run without contract checks"}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {blockedByFormat
              ? "Switch the output object to MULTICOMPO. MACROLIB is retained only for isolated diagnostics."
              : blockedBySph
                ? "The HDF5 contract passed, but Converter did not find an applied rate-SPH source with recorded provenance. Return to the physical SPH step; no output will be written."
                : validated
              ? productionChecks
                ? `The formal no-write handoff gate passed. The next action writes the selected ${object}; physics equivalence and reactor acceptance remain separate evidence layers.`
                : standardChecks
                  ? `Basic contract checks passed. Writing the ${object} is allowed for engineering use, but does not establish production acceptance.`
                  : `The no-write request completed without contract checks. Writing the ${object} is diagnostic only.`
              : converted
                ? productionChecks
                  ? `The contract-validated ${object} artifact was written. Continue with the result panel below; this is not a physics acceptance verdict.`
                  : `The ${object} artifact was written without production acceptance. Continue with the result panel below.`
                : requireAppliedRateSph
                  ? "This safe no-write check verifies the strict physical-SPH contract, physics balances, and provenance before anything is written."
                  : productionChecks
                    ? "This no-write gate verifies the formal Converter contract, provenance, and physics balances before anything is written."
                    : standardChecks
                      ? "This no-write engineering preflight checks the basic HDF5 contract and quick physics consistency. It is not production acceptance."
                      : "This no-write dry run skips the Converter contract checks. Any written result is diagnostic, not production accepted."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {object} · {writer} · {checksLabel}
          </span>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          ref={convertButtonRef}
          type={validated ? "button" : "submit"}
          onClick={validated ? onConvert : undefined}
          className="btn btn-primary"
          disabled={!canRun || converted || blockedBySph || blockedByFormat}
        >
          {dryRunLoading
            ? "Validating HDF5…"
            : convertLoading
              ? "Converter running…"
              : converted
                ? "✓ Converter completed"
                : validated
                  ? productionChecks
                    ? "Run Converter"
                    : standardChecks
                      ? "Write engineering output"
                      : "Write diagnostic output"
                  : productionChecks
                    ? "Validate for production"
                    : standardChecks
                      ? "Run engineering preflight"
                      : "Run no-check dry run"}
        </button>
        <p className="text-[12px] leading-5 text-[var(--fg-3)]">
          {blockedByFormat
            ? "Choose MULTICOMPO before validating this colorset."
            : blockedBySph
              ? "Required: sph_applied=true, a recorded sph_applied_source, and a rate-preserving sph_kind."
              : !hasInput
            ? "Select the Converter input HDF5 to enable validation."
            : !hasOutput
              ? "Choose an output path to enable validation."
              : validated
            ? productionChecks
              ? "The formal no-write gate passed. Converter is ready to write a contract-validated handoff artifact; physics acceptance is still separate."
              : "This result is not production accepted; switch to Production and pass that gate before formal handoff."
            : converted
              ? productionChecks
                ? "Use the generated result links to continue to DONJON or Inspect."
                : "For formal handoff, switch to Production, validate again, and regenerate the artifact."
              : "Nothing is written during this first no-write action."}
        </p>
      </div>
    </section>
  );
}
