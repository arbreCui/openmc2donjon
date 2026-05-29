import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import {
  convertSphHandoffStatus,
  type ConvertSphHandoffStatus,
} from "@/lib/convertSphHandoff";

export default function SphHandoffCard({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
}) {
  const status = convertSphHandoffStatus(data, input);
  if (!status) return null;

  return (
    <section className={"rounded-xl border p-5 " + cardClass(status)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            OpenMC-side SPH delivery
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {status.title}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            This converter step does not recompute SPH. It verifies the
            corrected OpenMC handoff and writes the DONJON-facing ASCII object.
          </p>
        </div>
        <span className="rounded border border-current/25 px-2 py-1 text-[10px] uppercase tracking-[0.14em]">
          {status.badge}
        </span>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <SphTile label="Corrected source" value={status.source} />
        <SphTile label="DONJON output" value={status.output} />
        <SphTile label="Production check" value={status.validation} />
        <SphTile label="Next action" value={status.nextAction} />
      </div>
    </section>
  );
}

function SphTile({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-md border border-current/10 bg-black/15 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-65">
        {label}
      </div>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-1)]">{value}</p>
    </article>
  );
}

function cardClass(status: ConvertSphHandoffStatus): string {
  if (status.tone === "ready") {
    return "border-emerald-300/25 bg-emerald-300/[0.055] text-emerald-100";
  }
  return "border-amber-300/25 bg-amber-300/[0.055] text-amber-100";
}

