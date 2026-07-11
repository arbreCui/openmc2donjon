"use client";

import { convertDonjonGuideHref } from "@/lib/convertNextSteps";
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
  onConvert,
  mockBackend = false,
}: {
  state: ConvertRunState;
  onConvert?: () => void;
  mockBackend?: boolean;
}) {
  return (
    <ResultBody state={state} onConvert={onConvert} mockBackend={mockBackend} />
  );
}

function ResultBody({
  state,
  onConvert,
  mockBackend,
}: {
  state: ConvertRunState;
  onConvert?: () => void;
  mockBackend: boolean;
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
    return (
      <section className="glass rounded-xl border-rose-500/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Request failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </section>
    );
  }
  return (
    <ConvertSummary
      data={state.data}
      onConvert={onConvert}
      mockBackend={mockBackend}
    />
  );
}

function ConvertSummary({
  data,
  onConvert,
  mockBackend,
}: {
  data: Extract<ConvertRunState, { kind: "ok" }>["data"];
  onConvert?: () => void;
  mockBackend: boolean;
}) {
  const input = data.preflight?.inputs[0] ?? null;
  return (
    <div className="space-y-4">
      <ConvertOutcomeSummary
        data={data}
        input={input}
        onConvert={onConvert}
        mockBackend={mockBackend}
      />

      {input ? <ConvertValidationSummary data={data} input={input} /> : null}

      <SphHandoffCard data={data} input={input} />

      <OutputActions data={data} onConvert={onConvert} />

      <ConvertRunDetails data={data} input={input} onConvert={onConvert} />
      {data.converted && data.output_exists ? (
        <div id="ascii-output-preview">
          <AsciiPreview
            path={data.output_path}
            format={data.format}
            input={input}
            donjonHref={convertDonjonGuideHref(data)}
          />
        </div>
      ) : null}
    </div>
  );
}
