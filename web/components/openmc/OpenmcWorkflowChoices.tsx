"use client";

const CHOICES = [
  {
    title: "Run shape",
    focus: "One-step vs Two-step",
    body:
      "Use one-step when you want a managed OpenMC -> HDF5 -> DONJON ASCII bundle. Use two-step when the HDF5 handoff should be inspected, archived, or augmented before conversion.",
  },
  {
    title: "Equivalence",
    focus: "Direct / ADF / SPH",
    body:
      "Direct keeps the raw homogenized XS. ADF/DF carries face discontinuity corrections. SPH carries OpenMC CE/MG flux-equivalence factors as an explicit sidecar.",
  },
  {
    title: "Production guard",
    focus: "Preflight vs Production gates",
    body:
      "Preflight checks the HDF5 contract and paths. Production gates add stricter physics checks for mesh identity, balance, chi, uncertainty, equivalence layout, and transport consistency.",
  },
] as const;

export default function OpenmcWorkflowChoices() {
  return (
    <section className="mb-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            How to choose the workflow
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            Pick the run shape, equivalence method, and gate strictness independently.
          </p>
        </div>
        <span className="rounded border border-emerald-300/25 bg-emerald-300/[0.06] px-2 py-1 text-[11px] uppercase tracking-wider text-emerald-100">
          OpenMC handoff
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {CHOICES.map((choice) => (
          <article
            key={choice.title}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.02] p-3"
          >
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {choice.title}
            </div>
            <h3 className="mt-1 text-sm font-semibold tracking-tight text-[var(--fg-0)]">
              {choice.focus}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-[var(--fg-2)]">
              {choice.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
