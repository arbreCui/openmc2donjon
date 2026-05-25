import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import { convertArtifactAnatomy } from "@/lib/convertArtifactAnatomy";

export default function ArtifactAnatomyCard({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
}) {
  const anatomy = convertArtifactAnatomy(data.format, input);
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">
            Artifact anatomy
          </h3>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            {anatomy.subtitle}
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {anatomy.label}
        </span>
      </div>

      <div className="mt-3 rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 text-[12px] text-[var(--fg-2)] tab-num">
        {anatomy.countLine}
      </div>

      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {anatomy.sections.map((section) => (
          <article
            key={section.id}
            className="rounded-md border border-[var(--edge)] bg-black/15 px-3 py-2"
          >
            <h4 className="text-sm font-semibold tracking-tight text-[var(--fg-0)]">
              {section.title}
            </h4>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {section.body}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {section.blocks.map((block) => (
                <span
                  key={block}
                  className="rounded border border-cyan-300/20 bg-cyan-300/[0.05] px-1.5 py-0.5 font-mono text-[10px] text-cyan-100"
                >
                  {block}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
