import Link from "next/link";
import type { ConvertFormat } from "@/lib/api";
import { convertActionGuideSteps } from "@/lib/convertActionGuide";
import type { ConvertWalkthroughRun } from "@/lib/convertWalkthrough";
import {
  actionGuideClass,
  actionGuideStatusLabel,
} from "./ConvertReportShared";
import type { ConvertRunState } from "./ConvertReportState";

export default function ConvertActionProgress({
  state,
  draftInputPath,
  draftOutputPath,
  format,
}: {
  state: ConvertRunState;
  draftInputPath: string;
  draftOutputPath: string;
  format: ConvertFormat;
}) {
  const inputPath = state.kind === "ok" ? state.data.input_path : draftInputPath;
  const outputPath = state.kind === "ok" ? state.data.output_path : draftOutputPath;
  const resolvedFormat = state.kind === "ok" ? state.data.format : format;
  const steps = convertActionGuideSteps({
    inputPath,
    outputPath,
    format: resolvedFormat,
    run: convertActionRunFromState(state),
  });
  return (
    <section className="rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Converter main path
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Dry-run the OpenMC MGXS handoff, convert it to ASCII, then preview
            or bundle the DONJON delivery file.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {resolvedFormat === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO"}
        </span>
      </div>
      <PathPrecondition inputPath={inputPath} outputPath={outputPath} />
      <div className="mt-4 grid gap-2 lg:grid-cols-3">
        {steps.map((step) => (
          <article
            key={step.id}
            className={"rounded-lg border px-3 py-2 " + actionGuideClass(step.status)}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="rounded border border-current/25 px-1.5 py-0.5 font-mono text-[10px]">
                {step.label}
              </span>
              <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
                {actionGuideStatusLabel(step.status)}
              </span>
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {step.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {step.body}
            </p>
            {step.links?.length ? (
              <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1">
                {step.links.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="inline-flex text-[12px] font-medium text-[var(--accent-2)] hover:underline"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function PathPrecondition({
  inputPath,
  outputPath,
}: {
  inputPath: string;
  outputPath: string;
}) {
  const input = inputPath.trim();
  const output = outputPath.trim();
  const hasBoth = input.length > 0 && output.length > 0;
  return (
    <div className="mt-4 rounded-lg border border-[var(--edge)] bg-white/[0.02] px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-[12px]">
        <span className="font-medium text-[var(--fg-1)]">
          Paths {hasBoth ? "set" : "needed before dry-run"}
        </span>
        <span className="text-[var(--fg-3)]">
          Source HDF5 and ASCII target are inputs to the three-step path below.
        </span>
      </div>
      {hasBoth ? (
        <dl className="mt-2 grid gap-1 text-[11px] tab-num md:grid-cols-[max-content_1fr]">
          <dt className="text-[var(--fg-3)]">input</dt>
          <dd className="min-w-0 truncate text-[var(--fg-2)]">{input}</dd>
          <dt className="text-[var(--fg-3)]">output</dt>
          <dd className="min-w-0 truncate text-[var(--fg-2)]">{output}</dd>
        </dl>
      ) : null}
    </div>
  );
}

function convertActionRunFromState(state: ConvertRunState): ConvertWalkthroughRun {
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
