"use client";

const CHOICES = [
  {
    title: "Direct conversion",
    focus: "MGXS HDF5 -> DONJON ASCII",
    body:
      "Use this when the OpenMC MGXS HDF5 already contains the homogenized macro data you want DONJON to consume.",
  },
  {
    title: "OpenMC-side SPH",
    focus: "CE reference + MG 33g same geometry",
    body:
      "Use this when CE and 33-group MG OpenMC runs share geometry/output regions. Compute SPH from their flux ratio, carry NSPH, then convert.",
  },
  {
    title: "Review evidence",
    focus: "physics summary + production gates",
    body:
      "Use the physics summary to verify CE/MG/SPH semantics, then use production gates to check mesh, uncertainty, balance, chi, and equivalence layout.",
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
            Pick the physics route first. For SPH, the main path is: run the
            CE/MG workflow, load the physics summary, then convert the corrected
            HDF5.
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
