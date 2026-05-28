import Link from "next/link";

import {
  C5G7_PRODUCTION_DEMO,
  convertDemoBundleHref,
  convertDemoClickSteps,
  convertDemoInspectHref,
  convertDemoPreviewHref,
} from "@/lib/convertDemo";

export default function MockDemoCard({
  onApply,
  onDryRun,
  onConvert,
  dryRunLoading,
  convertLoading,
  canConvert,
  converted,
}: {
  onApply: () => void;
  onDryRun: () => void;
  onConvert: () => void;
  dryRunLoading: boolean;
  convertLoading: boolean;
  canConvert: boolean;
  converted: boolean;
}) {
  const clickSteps = convertDemoClickSteps();
  return (
    <section className="mb-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.045] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Mock demo shortcut
          </div>
          <h2 className="mt-1 text-sm font-semibold tracking-tight text-cyan-100">
            {C5G7_PRODUCTION_DEMO.label}
          </h2>
          <p className="mt-1 max-w-2xl text-[12px] leading-5 text-[var(--fg-2)]">
            {C5G7_PRODUCTION_DEMO.description}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={onApply} className="btn btn-secondary">
            Fill demo
          </button>
          <button
            type="button"
            onClick={onDryRun}
            className="btn btn-primary"
            disabled={dryRunLoading}
          >
            {dryRunLoading ? "Checking…" : "Run demo dry-run"}
          </button>
          {canConvert || converted || convertLoading ? (
            <button
              type="button"
              onClick={onConvert}
              className="btn btn-primary"
              disabled={!canConvert || converted || convertLoading}
            >
              {convertLoading
                ? "Converting…"
                : converted
                  ? "Demo output ready"
                  : "Convert demo output"}
            </button>
          ) : null}
        </div>
      </div>
      {canConvert || converted ? (
        <div
          className={
            "mt-3 rounded-md border px-3 py-2 text-sm " +
            (converted
              ? "border-emerald-300/20 bg-emerald-300/[0.055] text-emerald-100"
              : "border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-100")
          }
        >
          <span className="font-semibold">
            {converted ? "Demo conversion complete." : "Dry run passed."}
          </span>
          <span className="ml-2 text-[var(--fg-1)]">
            {converted
              ? "The mock MULTICOMPO artifact is ready for preview and bundling below."
              : "Run Convert demo output to create the mock MULTICOMPO ASCII handoff."}
          </span>
        </div>
      ) : null}
      {converted ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href={convertDemoPreviewHref(C5G7_PRODUCTION_DEMO)}
            className="btn btn-primary"
          >
            Preview output
          </a>
          <Link
            href={convertDemoBundleHref(C5G7_PRODUCTION_DEMO)}
            className="btn btn-secondary"
          >
            Bundle demo
          </Link>
        </div>
      ) : null}
      <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 px-3 py-2 [&_summary::-webkit-details-marker]:hidden">
        <summary className="cursor-pointer text-[12px] font-medium text-cyan-100">
          Show demo click path
        </summary>
        <div className="mt-3 grid gap-3 lg:grid-cols-3">
          {clickSteps.map((step) => (
            <div key={step.id} className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="rounded border border-cyan-200/25 bg-cyan-200/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-cyan-100">
                  {step.label}
                </span>
                <h3 className="text-[12px] font-semibold tracking-tight text-cyan-50">
                  {step.title}
                </h3>
              </div>
              <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
                {step.body}
              </p>
            </div>
          ))}
        </div>
      </details>
      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--edge)] bg-black/10 px-3 py-2 text-[12px] text-[var(--fg-2)]">
        <span>Optional checks before or after the three-click demo:</span>
        <Link
          href={convertDemoInspectHref(C5G7_PRODUCTION_DEMO)}
          className="text-[var(--accent-2)] hover:underline"
        >
          Inspect source HDF5
        </Link>
        <Link
          href={convertDemoBundleHref(C5G7_PRODUCTION_DEMO)}
          className="text-[var(--accent-2)] hover:underline"
        >
          Open bundle builder
        </Link>
      </div>
    </section>
  );
}
