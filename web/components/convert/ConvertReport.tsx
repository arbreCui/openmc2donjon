"use client";

import type { ConvertFormat } from "@/lib/api";
import AsciiPreview from "./AsciiPreview";
import ConvertActionProgress from "./ConvertActionProgress";
import ConvertOutcomeSummary from "./ConvertOutcomeSummary";
import ConvertRunDetails from "./ConvertRunDetails";
import type { ConvertRunState } from "./ConvertReportState";
import ConvertValidationSummary from "./ConvertValidationSummary";
import OutputActions from "./OutputActions";
import SphHandoffCard from "./SphHandoffCard";

export type { ConvertRunState } from "./ConvertReportState";

export default function ConvertReport({
  state,
  onConvert,
  draftInputPath = "",
  draftOutputPath = "",
  format = "multicompo",
}: {
  state: ConvertRunState;
  onConvert?: () => void;
  draftInputPath?: string;
  draftOutputPath?: string;
  format?: ConvertFormat;
}) {
  return (
    <div className="space-y-4">
      <ConvertActionProgress
        state={state}
        draftInputPath={draftInputPath}
        draftOutputPath={draftOutputPath}
        format={format}
      />
      <ResultBody state={state} onConvert={onConvert} />
    </div>
  );
}

function ResultBody({
  state,
  onConvert,
}: {
  state: ConvertRunState;
  onConvert?: () => void;
}) {
  if (state.kind === "idle") {
    return (
      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">
          Ready for a dry run
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-[var(--fg-2)]">
          Start with a dry run to validate the HDF5 contract, energy mesh,
          production checks, and output path without writing an ASCII file.
        </p>
      </section>
    );
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
    return (
      <section className="glass rounded-xl border-rose-500/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Request failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </section>
    );
  }
  return <ConvertSummary data={state.data} onConvert={onConvert} />;
}

function ConvertSummary({
  data,
  onConvert,
}: {
  data: Extract<ConvertRunState, { kind: "ok" }>["data"];
  onConvert?: () => void;
}) {
  const input = data.preflight?.inputs[0] ?? null;
  return (
    <div className="space-y-4">
      <ConvertOutcomeSummary data={data} input={input} onConvert={onConvert} />

      {input ? <ConvertValidationSummary data={data} input={input} /> : null}

      <SphHandoffCard data={data} input={input} />

      <OutputActions data={data} onConvert={onConvert} />

      <ConvertRunDetails data={data} input={input} onConvert={onConvert} />
      {data.converted && data.output_exists ? (
        <div id="ascii-output-preview">
          <AsciiPreview path={data.output_path} format={data.format} input={input} />
        </div>
      ) : null}
    </div>
  );
}
