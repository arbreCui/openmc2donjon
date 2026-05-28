import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { PRODUCTION_MINICASE_COMMAND } from "@/lib/convertDemo";

export default function ProductionMinicaseMissingHint({
  onApply,
}: {
  onApply: () => void;
}) {
  return (
    <section className="mt-4 rounded-xl border border-amber-300/25 bg-amber-300/[0.06] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-amber-200">
            Production minicase artifacts were not found.
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Run the smoke command from the repository root first; it writes the
            managed MGXS path used by the live walkthrough. The repeat ASCII
            and bundle paths are created later by the web convert and bundle
            steps.
          </p>
        </div>
        <button type="button" onClick={onApply} className="btn btn-secondary">
          Refill paths
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CopyCliButton
          value={PRODUCTION_MINICASE_COMMAND}
          compact
          label="Copy smoke command"
          copiedLabel="Copied"
        />
        <code className="rounded border border-[var(--edge)] bg-black/20 px-2 py-1 font-mono text-[12px] text-[var(--fg-1)]">
          {PRODUCTION_MINICASE_COMMAND}
        </code>
      </div>
    </section>
  );
}
