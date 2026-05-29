import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { openmcSphWorkflowSteps } from "@/lib/openmcSphWorkflow";

export default function OpenmcSphWorkflowPanel({
  activeCommandId,
}: {
  activeCommandId: string | null;
}) {
  const steps = openmcSphWorkflowSteps(activeCommandId);
  return (
    <section className="mt-4 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.045] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-300">
            OpenMC-side SPH route
          </div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            CE reference and MG macro solve stay in OpenMC
          </h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            This route does not iterate DONJON for SPH. Run OpenMC twice with the
            same geometry, compute SPH from the two OpenMC flux fields, inject the
            factors into the MGXS HDF5, then use the normal converter.
          </p>
          <p className="mt-2 max-w-3xl text-[12px] leading-5 text-amber-200/85">
            Current accepted evidence includes the one-shot two-region production
            probe: two output regions produce two SPH factors per energy group.
            The five-region 2D case remains the larger diagnostic. Additional
            OpenMC MG reruns are available for review, but they are
            damping-sensitive and should not be treated as the default path.
          </p>
        </div>
        <Link href="/commands/export-volume-flux" className="btn btn-secondary">
          Flux export guide
        </Link>
      </div>

      <div className="mt-4 grid gap-2 lg:grid-cols-5">
        {steps.map((step, index) => (
          <article
            key={step.id}
            className={
              "rounded-md border px-3 py-2 " +
              (step.active
                ? "border-emerald-300/35 bg-emerald-300/[0.09]"
                : "border-[var(--edge)] bg-black/15")
            }
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[11px] text-[var(--fg-3)]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="rounded border border-current/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                {step.badge}
              </span>
            </div>
            <h4 className="mt-2 text-[12px] font-semibold tracking-tight">
              {step.title}
            </h4>
            <p className="mt-1 min-h-[3.5rem] text-[11px] leading-4 text-[var(--fg-2)]">
              {step.body}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Link href={step.href} className="text-[12px] text-[var(--accent-2)] hover:underline">
                Open step
              </Link>
              <CopyCliButton value={step.cli} compact />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
