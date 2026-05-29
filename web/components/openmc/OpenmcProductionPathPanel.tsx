"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type {
  ConvertFormat,
  OpenmcEquivalenceMode,
  OpenmcWorkflowKind,
  OpenmcWorkflowPlan,
} from "@/lib/api";
import {
  openmcBundleBuilderHref,
  openmcConvertHref,
  openmcInspectHref,
  openmcWalkthroughStatuses,
  type OpenmcWalkthroughRun,
  type OpenmcWalkthroughStatus,
} from "@/lib/openmcWorkflowWalkthrough";

export type OpenmcPlannerState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: OpenmcWorkflowPlan }
  | { kind: "error"; message: string; status?: number };

export default function OpenmcProductionPathPanel({
  state,
  workflow,
  equivalence,
  format,
  production,
  recipePath,
  statepointPath,
  loadStatepoint,
  runDir,
}: {
  state: OpenmcPlannerState;
  workflow: OpenmcWorkflowKind;
  equivalence: OpenmcEquivalenceMode;
  format: ConvertFormat;
  production: boolean;
  recipePath: string;
  statepointPath: string;
  loadStatepoint: boolean;
  runDir: string;
}) {
  const planned = state.kind === "ok" && state.data.ok;
  const plan = state.kind === "ok" ? state.data : null;
  const statuses = openmcWalkthroughStatuses({
    hasRecipe: recipePath.trim().length > 0,
    hasStatepoint: statepointPath.trim().length > 0,
    loadStatepoint,
    hasRunDir: runDir.trim().length > 0,
    run: openmcWalkthroughRunFromState(state),
  });
  const inspectHref = planned && plan ? openmcInspectHref(plan) : null;
  const convertHref =
    planned && plan ? openmcConvertHref(plan, format, production) : null;
  const bundleHref =
    planned && plan ? openmcBundleBuilderHref(plan, format) : null;
  const object = format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
  const isOpenmcSph = equivalence === "sph";
  const items = isOpenmcSph
    ? [
        {
          id: "run-openmc",
          label: "01",
          eyebrow: "Run physics",
          title: "Run OpenMC CE/MG SPH",
          body:
            "Run OpenMC CE as the reference and OpenMC MG on the same geometry/output regions. Export CE/MG fluxes, build SPH(region, group), and inject NSPH into the MGXS handoff.",
          status: statuses.plan,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "summary",
          label: "02",
          eyebrow: "Review evidence",
          title: "Review production evidence",
          body:
            "Load physics_summary.json and check CE/MG flux uncertainty, SPH factor range, reaction-rate preservation, and NSPH handoff status.",
          status: statuses.run,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "convert",
          label: "03",
          eyebrow: "Converter",
          title: "Convert to DONJON MACROLIB",
          body:
            `Use the corrected HDF5 as converter input and write ${object}. For this SPH route, MACROLIB is the DONJON consumption path because NSPH is carried as GROUP/*/NSPH.`,
          status: statuses.review,
          href: convertHref ?? inspectHref ?? undefined,
          hrefLabel: convertHref ? "Open converter" : "Inspect HDF5",
        },
      ]
    : [
        {
          id: "source",
          label: "01",
          eyebrow: "Export source",
          title: loadStatepoint ? "Export OpenMC MGXS" : "Prepare export command",
          body: loadStatepoint
            ? "Select the export recipe and statepoint that define the OpenMC MGXS handoff."
            : "Use the recipe without loading a statepoint when you only need the generated command scaffold.",
          status: statuses.source,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "convert",
          label: "02",
          eyebrow: "Converter",
          title: workflow === "one-step" ? `Write ${object}` : `Convert HDF5 to ${object}`,
          body:
            workflow === "one-step"
              ? `The primary command exports MGXS, applies ${equivalenceLabel(equivalence)}, writes ${object}, and records the run.`
              : `Run export first, inspect or augment the HDF5, then convert that handoff into ${object}.`,
          status: statuses.review,
          href: convertHref ?? inspectHref ?? undefined,
          hrefLabel: convertHref ? "Open converter" : "Inspect HDF5",
        },
        {
          id: "bundle",
          label: "03",
          eyebrow: "Bundle",
          title: "Package DONJON handoff",
          body:
            "Use a managed run directory to keep the MGXS input, ASCII output, summaries, and manifest together.",
          status: statuses.bundle,
          href: bundleHref ?? undefined,
          hrefLabel: "Open bundle builder",
        },
      ];

  return (
    <section className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Main line
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {isOpenmcSph
              ? "Three steps before the converter writes MACROLIB"
              : "Three steps before the converter writes DONJON ASCII"}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {isOpenmcSph
              ? "This route prepares the converter input: OpenMC MG is the SPH equivalence operator, DONJON receives precomputed NSPH factors, and DONJON is not used as an SPH feedback loop. The current production demo is one-shot SPH; extra MG reruns are a damping-sensitive review path."
              : "This route prepares the converter-facing HDF5 from OpenMC inputs. Once planned or exported, open Convert to run production checks and write the ASCII library."}
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {workflow === "one-step" ? "one-step" : "two-step"} ·{" "}
          {equivalenceLabel(equivalence)}
        </span>
      </div>

      <div className="mt-4 grid gap-2 lg:grid-cols-3">
        {items.map((item) => (
          <article
            key={item.id}
            className={
              "rounded-lg border px-3 py-2 " +
              openmcWalkthroughStatusClass(item.status)
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

      {planned && plan ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <CopyCliButton
            value={plan.primary_command_text}
            label="Copy primary command"
            copiedLabel="Copied"
          />
          {workflow === "two-step" && convertHref ? (
            <Link href={convertHref} className="btn btn-secondary">
              Open converter
            </Link>
          ) : null}
          {inspectHref ? (
            <Link href={inspectHref} className="btn btn-secondary">
              Inspect HDF5
            </Link>
          ) : null}
          {bundleHref ? (
            <Link href={bundleHref} className="btn btn-secondary">
              Bundle handoff
            </Link>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function openmcWalkthroughRunFromState(
  state: OpenmcPlannerState,
): OpenmcWalkthroughRun {
  if (state.kind === "loading") return { kind: "loading" };
  if (state.kind === "ok") return { kind: "ok", ok: state.data.ok };
  return { kind: state.kind };
}

function openmcWalkthroughStatusClass(status: OpenmcWalkthroughStatus): string {
  if (status === "passed") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (status === "ready" || status === "running") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "planned") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  if (status === "optional") {
    return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-3)]";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}

function equivalenceLabel(value: OpenmcEquivalenceMode): string {
  if (value === "adf") return "ADF/DF";
  if (value === "sph") return "SPH";
  if (value === "flux-ratio-adf") return "flux-ratio ADF";
  return "direct";
}
