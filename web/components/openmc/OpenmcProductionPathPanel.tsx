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
          id: "ce-mg",
          label: "01",
          eyebrow: "OpenMC physics",
          title: "Run CE + MG",
          body:
            "Run the CE reference and OpenMC MG macro calculation on the selected group structure with the same geometry and output regions.",
          status: statuses.source,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "sph",
          label: "02",
          eyebrow: "OpenMC-side SPH",
          title: "Build NSPH sidecar",
          body:
            "Export CE/MG region-group fluxes, compute SPH factors, and inject them into the MGXS handoff as NSPH.",
          status: statuses.plan,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "summary",
          label: "03",
          eyebrow: "Physics evidence",
          title: "Load physics summary",
          body:
            "Review SPH ranges, CE/MG flux uncertainty, and confirm the final ASCII carries NSPH factors.",
          status: statuses.run,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "convert",
          label: "04",
          eyebrow: "Converter",
          title: `Convert corrected HDF5 to ${object}`,
          body:
            "Use the augmented HDF5 as the converter input. The macro XS remain unchanged; DONJON consumes NSPH as equivalence factors.",
          status: statuses.review,
          href: convertHref ?? inspectHref ?? undefined,
          hrefLabel: convertHref ? "Open converter" : "Inspect HDF5",
        },
        {
          id: "bundle",
          label: "05",
          eyebrow: "Bundle",
          title: "Package production evidence",
          body:
            "Keep the corrected MGXS, ASCII handoff, physics summary, command summaries, and manifest together.",
          status: statuses.bundle,
          href: bundleHref ?? undefined,
          hrefLabel: "Open bundle builder",
        },
      ]
    : [
        {
          id: "source",
          label: "01",
          eyebrow: "OpenMC source",
          title: loadStatepoint ? "Recipe + statepoint" : "Recipe dry-run mode",
          body: loadStatepoint
            ? "Select the export recipe and statepoint that define the OpenMC MGXS handoff."
            : "Use the recipe without loading a statepoint when you only need the generated command scaffold.",
          status: statuses.source,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "plan",
          label: "02",
          eyebrow: "Plan commands",
          title: "Build the handoff plan",
          body: "The web page checks paths and emits copyable CLI commands. It does not execute OpenMC.",
          status: statuses.plan,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "run",
          label: "03",
          eyebrow: workflow === "one-step" ? "Run managed CLI" : "Run staged CLI",
          title: workflow === "one-step" ? "Export, check, convert" : "Export then convert",
          body:
            workflow === "one-step"
              ? `The primary command exports MGXS, applies ${equivalenceLabel(equivalence)}, writes ${object}, and records the run.`
              : `Run export first, inspect or augment the HDF5, then convert that handoff into ${object}.`,
          status: statuses.run,
          href: undefined,
          hrefLabel: undefined,
        },
        {
          id: "review",
          label: "04",
          eyebrow: "Review handoff",
          title: workflow === "two-step" ? "Inspect before conversion" : "Inspect outputs",
          body: "Review the HDF5 contract and generated ASCII before handing the result to DONJON.",
          status: statuses.review,
          href: inspectHref ?? undefined,
          hrefLabel: "Inspect HDF5",
        },
        {
          id: "bundle",
          label: "05",
          eyebrow: "Bundle",
          title: "Package production evidence",
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
            Production path
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {isOpenmcSph
              ? "OpenMC CE/MG SPH before DONJON conversion"
              : "Plan the OpenMC export before direct conversion"}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {isOpenmcSph
              ? "This route keeps the SPH equivalence calculation upstream in OpenMC. DONJON receives the corrected handoff and NSPH factors; it is not used as an SPH feedback loop."
              : "This surface builds the shell commands for the OpenMC side of the workflow. After the command runs, the produced HDF5 and ASCII artifacts continue through Inspect, Convert, and Bundle."}
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {workflow === "one-step" ? "one-step" : "two-step"} ·{" "}
          {equivalenceLabel(equivalence)}
        </span>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-5">
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
