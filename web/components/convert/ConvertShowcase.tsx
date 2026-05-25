import Link from "next/link";
import type { ConvertFormat, ConvertPreflightInput } from "@/lib/api";
import {
  convertShowcaseFacts,
  convertShowcaseObjectLabel,
} from "@/lib/convertShowcase";

interface Props {
  format: ConvertFormat;
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
  outputPath: string;
  input: ConvertPreflightInput | null;
}

export default function ConvertShowcase({
  format,
  check,
  production,
  requireKnownMesh,
  outputPath,
  input,
}: Props) {
  const objectLabel = convertShowcaseObjectLabel(format);
  const facts = convertShowcaseFacts({
    format,
    check,
    production,
    requireKnownMesh,
    input,
  });
  const trimmedOutput = outputPath.trim();
  return (
    <section className="mb-5 rounded-xl border border-[var(--edge)] bg-white/[0.018] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--accent-2)]">
            What will be written
          </p>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {objectLabel} ASCII handoff for DONJON
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Dry run reads the same inputs and reports the same checks, but does
            not create a file. Convert writes the selected ASCII object and
            preserves the OpenMC mixture ordering.
          </p>
        </div>
        <Link href="/equivalence?kind=adf-sidecar" className="btn btn-secondary">
          Need ADF/SPH?
        </Link>
      </div>

      {trimmedOutput ? (
        <div className="mt-3 truncate rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-[12px] text-[var(--fg-1)]">
          {trimmedOutput}
        </div>
      ) : null}

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {facts.map((fact) => (
          <article
            key={fact.id}
            className={"rounded-lg border px-3 py-2 " + factClass(fact.tone)}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-sm font-semibold tracking-tight">
                {fact.title}
              </h3>
              <span className="shrink-0 rounded border border-current/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] opacity-85">
                {fact.badge}
              </span>
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
              {fact.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function factClass(tone: "neutral" | "accent" | "pass" | "warn"): string {
  if (tone === "accent") {
    return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-50";
  }
  if (tone === "pass") {
    return "border-emerald-300/20 bg-emerald-300/[0.045] text-emerald-50";
  }
  if (tone === "warn") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-50";
  }
  return "border-[var(--edge)] bg-black/10 text-[var(--fg-0)]";
}
