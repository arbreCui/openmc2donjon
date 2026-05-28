import Link from "next/link";

import type { ConvertFormat } from "@/lib/api";
import {
  convertBundleBuilderHrefFromPaths,
  convertWorkflowStageSummary,
  convertWalkthroughStatuses,
  type ConvertWorkflowStageStatus,
  type ConvertWalkthroughRun,
  type ConvertWalkthroughStatus,
} from "@/lib/convertWalkthrough";
import type { ConvertRunState } from "./ConvertReportState";

export default function ConvertPrimer({
  state,
  inputPath,
  outputPath,
  format,
}: {
  state: ConvertRunState;
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
}) {
  const trimmedInput = inputPath.trim();
  const trimmedOutput = outputPath.trim();
  const run = convertWalkthroughRunFromState(state);
  const statuses = convertWalkthroughStatuses({
    hasInput: trimmedInput.length > 0,
    hasOutput: trimmedOutput.length > 0,
    run,
  });
  const stageSummary = convertWorkflowStageSummary({
    hasInput: trimmedInput.length > 0,
    hasOutput: trimmedOutput.length > 0,
    run,
  });
  const object = format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
  const inspectHref = trimmedInput
    ? `/inspect?path=${encodeURIComponent(trimmedInput)}`
    : undefined;
  const bundleHref =
    convertBundleBuilderHrefFromPaths({
      inputPath: trimmedInput,
      outputPath: trimmedOutput,
      format,
    }) ?? undefined;
  const items = [
    {
      id: "source",
      label: "01",
      eyebrow: "Source",
      title: "OpenMC MGXS HDF5",
      body:
        "Start from the homogenized OpenMC handoff. Inspect it when you need mixture, mesh, ADF, or SPH evidence.",
      href: inspectHref,
      hrefLabel: "Inspect source",
      status: statuses.source,
    },
    {
      id: "dry-run",
      label: "02",
      eyebrow: "No-write check",
      title: "No-write production check",
      body:
        "Run the converter in dry-run mode first. It checks the contract and production physics without creating output.",
      href: undefined,
      hrefLabel: undefined,
      status: statuses["dry-run"],
    },
    {
      id: "convert",
      label: "03",
      eyebrow: "Convert ASCII",
      title: `Write ${object}`,
      body:
        "Convert writes the DONJON-facing ASCII handoff at the selected output path.",
      href: undefined,
      hrefLabel: undefined,
      status: statuses.convert,
    },
    {
      id: "bundle",
      label: "04",
      eyebrow: "Bundle handoff",
      title: "Package delivery evidence",
      body:
        "Collect the MGXS input, ASCII output, summaries, and logs into a manifest-backed handoff.",
      href: bundleHref,
      hrefLabel: "Open bundle builder",
      status: statuses.bundle,
    },
  ] as const;
  return (
    <section className="mb-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Direct converter production path
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            This page turns an existing OpenMC MGXS handoff into a DONJON-facing
            ASCII library. Dry run is the readable no-write checkpoint, Convert
            creates the file, and Bundle packages the delivery record.
          </p>
        </div>
        <Link href="/commands/direct-convert" className="btn btn-secondary">
          Command notes
        </Link>
      </div>
      <div
        className={
          "mt-4 rounded-lg border px-3 py-3 " +
          stageSummaryClass(stageSummary.tone)
        }
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
              Current stage
            </div>
            <h3 className="mt-1 text-sm font-semibold tracking-tight">
              {stageSummary.title}
            </h3>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-1)]">
              {stageSummary.body}
            </p>
          </div>
          <ol className="flex min-w-0 flex-wrap items-center gap-1.5">
            {stageSummary.stages.map((stage, index) => (
              <li key={stage.id} className="flex items-center gap-1.5">
                {index > 0 ? (
                  <span className="text-[var(--fg-3)]" aria-hidden="true">
                    →
                  </span>
                ) : null}
                <span
                  className={
                    "rounded-full border px-2 py-1 text-[11px] font-medium " +
                    stagePillClass(stage.status)
                  }
                >
                  {stage.label}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => (
          <article
            key={item.id}
            className={
              "rounded-lg border px-3 py-2 " +
              walkthroughStatusClass(item.status)
            }
          >
            <div className="flex items-center justify-between gap-2">
              <span className="rounded border border-current/25 px-1.5 py-0.5 font-mono text-[10px]">
                {item.label}
              </span>
              <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
                {item.status}
              </span>
            </div>
            <div className="mt-2 text-[10px] uppercase tracking-[0.14em] opacity-70">
              {item.eyebrow}
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {item.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {item.body}
            </p>
            {item.href && item.hrefLabel ? (
              <Link
                href={item.href}
                className="mt-3 inline-flex text-[12px] font-medium text-[var(--accent-2)] hover:underline"
              >
                {item.hrefLabel}
              </Link>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function stageSummaryClass(
  tone: "ready" | "current" | "running" | "blocked",
): string {
  if (tone === "ready") {
    return "border-emerald-300/20 bg-emerald-300/[0.045] text-emerald-100";
  }
  if (tone === "running") {
    return "border-cyan-300/25 bg-cyan-300/[0.07] text-cyan-100";
  }
  if (tone === "blocked") {
    return "border-rose-300/25 bg-rose-300/[0.055] text-rose-100";
  }
  return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
}

function stagePillClass(status: ConvertWorkflowStageStatus): string {
  if (status === "complete") {
    return "border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-100";
  }
  if (status === "running") {
    return "border-cyan-300/25 bg-cyan-300/[0.12] text-cyan-100";
  }
  if (status === "current") {
    return "border-amber-300/30 bg-amber-300/[0.12] text-amber-100";
  }
  if (status === "blocked") {
    return "border-rose-300/25 bg-rose-300/[0.08] text-rose-100";
  }
  return "border-[var(--edge)] bg-black/10 text-[var(--fg-2)]";
}

function convertWalkthroughRunFromState(state: ConvertRunState): ConvertWalkthroughRun {
  if (state.kind === "loading") {
    return { kind: "loading", mode: state.mode };
  }
  if (state.kind === "ok") {
    return {
      kind: "ok",
      ok: state.data.ok,
      dryRun: state.data.dry_run,
      converted: state.data.converted,
      outputExists: state.data.output_exists,
      preflightOk: state.data.preflight_ok,
    };
  }
  return { kind: state.kind };
}

function walkthroughStatusClass(status: ConvertWalkthroughStatus): string {
  if (status === "done" || status === "passed") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (status === "ready") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "recommended" || status === "planned") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}
