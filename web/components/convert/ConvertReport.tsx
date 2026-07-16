"use client";

import {
  convertDonjonGuideHref,
  type ConvertDownstreamDestination,
} from "@/lib/convertNextSteps";
import AsciiPreview from "./AsciiPreview";
import ConvertOutcomeSummary from "./ConvertOutcomeSummary";
import ConvertRunDetails from "./ConvertRunDetails";
import type { ConvertRunState } from "./ConvertReportState";
import ConvertValidationSummary from "./ConvertValidationSummary";
import OutputActions from "./OutputActions";
import SphHandoffCard from "./SphHandoffCard";

export type { ConvertRunState } from "./ConvertReportState";

export default function ConvertReport({
  state,
  mockBackend = false,
  outputPath,
  onOverwriteRetry,
  downstream,
}: {
  state: ConvertRunState;
  mockBackend?: boolean;
  outputPath?: string;
  onOverwriteRetry?: () => void;
  downstream?: ConvertDownstreamDestination | null;
}) {
  return (
    <ResultBody
      state={state}
      mockBackend={mockBackend}
      outputPath={outputPath}
      onOverwriteRetry={onOverwriteRetry}
      downstream={downstream}
    />
  );
}

function ResultBody({
  state,
  mockBackend,
  outputPath,
  onOverwriteRetry,
  downstream,
}: {
  state: ConvertRunState;
  mockBackend: boolean;
  outputPath?: string;
  onOverwriteRetry?: () => void;
  downstream?: ConvertDownstreamDestination | null;
}) {
  if (state.kind === "idle") {
    return null;
  }
  if (state.kind === "loading") {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)] tab-num">
        {state.mode === "dry-run"
          ? "Validating input and output target..."
          : "Validating input and writing ASCII output..."}
      </section>
    );
  }
  if (state.kind === "error") {
    const physicalGatePrefix = "physical SPH gate failed: ";
    const physicalGateFailed = state.message.startsWith(physicalGatePrefix);
    const outputConflict = state.status === 409;
    const errorParts = (physicalGateFailed
      ? state.message.slice(physicalGatePrefix.length)
      : state.message
    )
      .split(/;\s+/)
      .filter(Boolean);
    return (
      <section className="glass rounded-xl border-rose-500/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          {physicalGateFailed
            ? "Converter stopped before writing"
            : outputConflict
              ? "Output already exists"
              : state.status
                ? `HTTP ${state.status}`
                : "Request failed"}
        </div>
        {physicalGateFailed ? (
          <div className="mt-2">
            <p className="text-sm text-[var(--fg-1)]">
              This HDF5 does not satisfy the requested physical SPH contract:
            </p>
            <ul className="mt-2 grid gap-1.5 text-[12px] leading-5 text-[var(--fg-2)]">
              {errorParts.map((part) => (
                <li key={part} className="rounded-md border border-rose-300/15 bg-rose-300/[0.04] px-3 py-1.5">
                  {part}
                </li>
              ))}
            </ul>
          </div>
        ) : outputConflict ? (
          <div className="mt-2 space-y-3">
            <p className="text-sm text-[var(--fg-1)]">
              Converter did not replace the existing artifact. Change the
              Output ASCII path above, or explicitly allow replacement and run
              the same production checks again.
            </p>
            {outputPath ? (
              <div className="break-all rounded border border-[var(--edge)] bg-black/15 px-3 py-2 font-mono text-[11px] text-[var(--fg-2)]">
                {outputPath}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {onOverwriteRetry ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={onOverwriteRetry}
                >
                  Allow overwrite and rerun Converter
                </button>
              ) : null}
              <a href="#convert-component" className="btn btn-secondary">
                Change output path
              </a>
            </div>
          </div>
        ) : (
          <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
        )}
      </section>
    );
  }
  return (
    <ConvertSummary
      data={state.data}
      mockBackend={mockBackend}
      downstream={downstream}
    />
  );
}

function ConvertSummary({
  data,
  mockBackend,
  downstream,
}: {
  data: Extract<ConvertRunState, { kind: "ok" }>["data"];
  mockBackend: boolean;
  downstream?: ConvertDownstreamDestination | null;
}) {
  const input = data.preflight?.inputs[0] ?? null;
  if (data.dry_run) {
    return (
      <div className="space-y-4">
        <ConvertOutcomeSummary
          data={data}
          input={input}
          mockBackend={mockBackend}
        />
        {input ? (
          <details className="rounded-xl border border-[var(--edge)] bg-black/10 p-3">
            <summary className="cursor-pointer text-sm font-semibold text-[var(--fg-1)]">
              Validation evidence
            </summary>
            <div className="mt-4">
              <ConvertValidationSummary data={data} input={input} />
            </div>
          </details>
        ) : null}
        <ConvertRunDetails data={data} input={input} downstream={downstream} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <ConvertOutcomeSummary
        data={data}
        input={input}
        mockBackend={mockBackend}
      />

      <SphHandoffCard data={data} input={input} />

      <OutputActions data={data} downstream={downstream} />

      {input ? (
        <details className="rounded-xl border border-[var(--edge)] bg-black/10 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-[var(--fg-1)]">
            Validation evidence
          </summary>
          <div className="mt-4">
            <ConvertValidationSummary data={data} input={input} />
          </div>
        </details>
      ) : null}

      <ConvertRunDetails data={data} input={input} downstream={downstream} />
      {data.converted && data.output_exists ? (
        <details id="ascii-output-preview" className="rounded-xl border border-[var(--edge)] bg-black/10 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-[var(--fg-1)]">
            Preview generated ASCII
          </summary>
          <div className="mt-4">
            <AsciiPreview
              path={data.output_path}
              format={data.format}
              input={input}
              donjonHref={downstream?.href ?? convertDonjonGuideHref(data)}
            />
          </div>
        </details>
      ) : null}
    </div>
  );
}
