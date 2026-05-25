"use client";

import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import type { ConvertArtifactStatusMap } from "@/lib/convertArtifactStatus";
import { buildConvertRunSummary } from "@/lib/convertRunSummary";

export default function RunSummaryCard({
  data,
  input,
  statuses,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  statuses: ConvertArtifactStatusMap;
}) {
  const summary = buildConvertRunSummary(data, input, statuses);

  return (
    <details className="mt-3 rounded-md border border-[var(--edge)] bg-black/10 p-3">
      <summary className="cursor-pointer select-none text-sm font-semibold tracking-tight text-[var(--fg-0)]">
        Shareable run summary
      </summary>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[var(--fg-3)]">
        <span>
          Copy this when sharing a converter run with a collaborator or
          attaching evidence to a handoff bundle.
        </span>
        <CopyCliButton
          value={summary}
          compact
          label="Copy summary"
          copiedLabel="Copied summary"
          ariaLabel="Copy direct conversion run summary"
        />
      </div>
      <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] leading-5 text-[var(--fg-1)]">
        {summary}
      </pre>
    </details>
  );
}
