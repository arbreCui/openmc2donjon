import Link from "next/link";
import type { ProductionPathStep } from "@/lib/productionPath";

interface Props {
  steps: readonly ProductionPathStep[];
}

export default function ProductionPathStrip({ steps }: Props) {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
            Production path
          </p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">
            From OpenMC handoff to DONJON-ready delivery
          </h2>
        </div>
        <Link href="/commands" className="btn btn-secondary">
          Full command map
        </Link>
      </div>

      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
        Production SPH now stays upstream in OpenMC: compare CE reference
        tallies with an OpenMC MG macro solve on the same geometry/output
        regions, carry the resulting NSPH factors into HDF5, then use the
        direct converter for DONJON delivery.
      </p>

      <ol className="mt-4 grid gap-3 lg:grid-cols-3">
        {steps.map((step, index) => (
          <li key={step.id} className="relative">
            {index > 0 ? (
              <div className="pointer-events-none absolute -left-3 top-1/2 hidden h-px w-3 bg-[var(--edge-bright)] lg:block" />
            ) : null}
            <Link
              href={step.href}
              className="group block h-full rounded-lg border border-[var(--edge)] bg-white/[0.02] p-4 transition hover:border-[var(--edge-bright)] hover:bg-white/[0.045]"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="tab-num rounded-md border border-[var(--edge)] bg-black/20 px-2 py-1 text-[11px] font-semibold text-[var(--accent)]">
                  {step.label}
                </span>
                <span className="text-[11px] text-[var(--fg-3)]">
                  {step.result}
                </span>
              </div>
              <h3 className="mt-3 text-sm font-semibold tracking-tight text-[var(--fg-0)]">
                {step.title}
              </h3>
              <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
                {step.body}
              </p>
              <div className="mt-4 text-[12px] font-medium text-[var(--accent-2)] group-hover:underline">
                Open step
              </div>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
