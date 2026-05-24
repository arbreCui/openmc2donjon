"use client";

const CONCEPTS = [
  {
    title: "Output object",
    focus: "MULTICOMPO vs MACROLIB",
    body:
      "MULTICOMPO preserves mapped mixtures for DONJON material assignments. MACROLIB is the smaller one-state handoff when no composition map is needed.",
  },
  {
    title: "Gate mode",
    focus: "Preflight vs Production",
    body:
      "Preflight checks the HDF5 contract and output path. Production gates add stricter physics checks for handoff readiness.",
  },
  {
    title: "Run mode",
    focus: "Dry run vs Convert",
    body:
      "Dry run reports exactly what would happen without writing. Convert writes the ASCII artifact, then exposes preview and copy actions.",
  },
] as const;

export default function ConvertConcepts() {
  return (
    <section className="mb-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            How to read this workflow
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            Three choices are independent: what to write, how strictly to check it,
            and whether to write now.
          </p>
        </div>
        <span className="rounded border border-cyan-300/25 bg-cyan-300/[0.06] px-2 py-1 text-[11px] uppercase tracking-wider text-cyan-100">
          direct converter
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {CONCEPTS.map((concept) => (
          <article
            key={concept.title}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.02] p-3"
          >
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {concept.title}
            </div>
            <h3 className="mt-1 text-sm font-semibold tracking-tight text-[var(--fg-0)]">
              {concept.focus}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-[var(--fg-2)]">
              {concept.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
