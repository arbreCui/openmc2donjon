import type { ConvertResponse } from "@/lib/api";
import { convertAsciiReadiness } from "@/lib/convertAsciiReadiness";
import type { FileStatusState } from "@/lib/fileStatus";

export default function AsciiReadinessPanel({
  data,
  outputStatus,
}: {
  data: ConvertResponse;
  outputStatus?: FileStatusState;
}) {
  const readiness = convertAsciiReadiness(data, outputStatus);
  return (
    <section className={"mt-3 rounded-md border p-3 " + panelClass(readiness.tone)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-sm font-semibold tracking-tight">
              ASCII handoff readiness
            </h4>
            <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
              {readiness.label}
            </span>
          </div>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
            {readiness.objectLabel}: {readiness.objectDescription}
          </p>
        </div>
        {readiness.previewAvailable ? (
          <a
            href="#ascii-output-preview"
            className="text-[12px] text-[var(--accent-2)] hover:underline"
          >
            Jump to preview
          </a>
        ) : (
          <span className="text-[12px] text-[var(--fg-3)]">preview waits</span>
        )}
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <ReadinessCopy title={readiness.title} body={readiness.body} />
        <ReadinessCopy title="Next action" body={readiness.next} />
      </div>
    </section>
  );
}

function ReadinessCopy({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded border border-current/15 bg-black/10 px-3 py-2">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] opacity-80">
        {title}
      </div>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
    </div>
  );
}

function panelClass(tone: "ready" | "write" | "warn" | "blocked"): string {
  if (tone === "ready") {
    return "border-emerald-400/25 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (tone === "write") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (tone === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
}
