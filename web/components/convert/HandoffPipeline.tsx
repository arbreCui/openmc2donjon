"use client";

import { ConvertPreflightInput, ConvertResponse } from "@/lib/api";

type PipelineTone = "pass" | "warn" | "fail" | "neutral";

interface PipelineStage {
  id: string;
  title: string;
  eyebrow: string;
  status: string;
  tone: PipelineTone;
  detail: string;
  path?: string;
}

export default function HandoffPipeline({
  data,
  input,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
}) {
  const stages = buildPipelineStages(data, input);
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Handoff workflow
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            What the converter is handing from OpenMC to DONJON in this run.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {formatLabel(data.format)}
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {stages.map((stage) => (
          <article
            key={stage.id}
            className={"rounded-lg border p-4 " + stageClass(stage.tone)}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
                  {stage.eyebrow}
                </div>
                <h3 className="mt-1 text-sm font-semibold tracking-tight">
                  {stage.title}
                </h3>
              </div>
              <span
                className={
                  "rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                  badgeClass(stage.tone)
                }
              >
                {stage.status}
              </span>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-[var(--fg-2)]">
              {stage.detail}
            </p>
            {stage.path ? (
              <div
                className="mt-3 truncate rounded border border-[var(--edge)] bg-black/20 px-2 py-1 font-mono text-[12px] text-[var(--fg-1)]"
                title={stage.path}
              >
                {stage.path}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function buildPipelineStages(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): PipelineStage[] {
  return [
    {
      id: "source",
      eyebrow: "OpenMC source",
      title: "MGXS HDF5 handoff",
      status: sourceStatus(input),
      tone: sourceTone(input),
      detail: sourceDetail(input),
      path: data.input_path,
    },
    {
      id: "artifact",
      eyebrow: "Converter artifact",
      title: artifactTitle(data.format),
      status: artifactStatus(data),
      tone: artifactTone(data),
      detail: artifactDetail(data),
      path: data.output_path,
    },
    {
      id: "consumer",
      eyebrow: "DONJON side",
      title: consumerTitle(data.format),
      status: consumerStatus(data),
      tone: consumerTone(data),
      detail: consumerDetail(data),
    },
  ];
}

function sourceStatus(input: ConvertPreflightInput | null): string {
  if (!input) return "unknown";
  return input.ok ? "ready" : "check";
}

function sourceTone(input: ConvertPreflightInput | null): PipelineTone {
  if (!input) return "neutral";
  return input.ok ? "pass" : "fail";
}

function sourceDetail(input: ConvertPreflightInput | null): string {
  if (!input) return "Input metadata was not reported for this response.";
  const groups = input.energy_groups == null ? "?" : String(input.energy_groups);
  const mixtures = input.mixtures == null ? "?" : String(input.mixtures);
  const states = input.state_points == null ? "?" : String(input.state_points);
  const mesh = input.energy_mesh_name ?? input.energy_mesh_id ?? "custom mesh";
  return `${mixtures} mixtures, ${groups} groups, ${states} state point(s), ${mesh}.`;
}

function formatLabel(format: ConvertResponse["format"]): string {
  return format === "macrolib" ? "MACROLIB" : "MULTICOMPO";
}

function artifactTitle(format: ConvertResponse["format"]): string {
  return format === "macrolib" ? "L_MACROLIB ASCII" : "L_MULTICOMPO ASCII";
}

function artifactStatus(data: ConvertResponse): string {
  if (data.converted && data.output_exists) return "written";
  if (data.dry_run && data.ok && !data.output_exists) return "ready";
  if (data.output_exists && data.dry_run) return "exists";
  return "blocked";
}

function artifactTone(data: ConvertResponse): PipelineTone {
  if (data.converted && data.output_exists) return "pass";
  if (data.dry_run && data.ok && !data.output_exists) return "neutral";
  if (data.output_exists && data.dry_run) return "warn";
  return "fail";
}

function artifactDetail(data: ConvertResponse): string {
  if (data.converted && data.output_exists) {
    const size = data.output_size == null ? "size unknown" : formatSize(data.output_size);
    return `The ASCII file exists and is ready to review (${size}).`;
  }
  if (data.dry_run && data.ok && !data.output_exists) {
    return "Dry run passed; Convert will write this ASCII artifact.";
  }
  if (data.output_exists && data.dry_run) {
    return "Dry run found an existing target. Enable overwrite if replacement is intended.";
  }
  return "No output artifact is ready yet. Resolve the failed checks or request error.";
}

function consumerTitle(format: ConvertResponse["format"]): string {
  return format === "macrolib" ? "Direct macrolib input" : "Mapped domain library";
}

function consumerStatus(data: ConvertResponse): string {
  if (data.converted && data.output_exists) return "ready";
  if (data.dry_run && data.ok && !data.output_exists) return "next";
  return data.ok ? "pending" : "blocked";
}

function consumerTone(data: ConvertResponse): PipelineTone {
  if (data.converted && data.output_exists) return "pass";
  if (data.dry_run && data.ok && !data.output_exists) return "neutral";
  return data.ok ? "neutral" : "fail";
}

function consumerDetail(data: ConvertResponse): string {
  if (data.format === "macrolib") {
    return "Use the output as a one-state DRAGON/DONJON macrolib input.";
  }
  return "Use the output as a MULTICOMPO input where each exported mixture maps to a DONJON material index.";
}

function stageClass(tone: PipelineTone): string {
  if (tone === "pass") return "border-emerald-400/20 bg-emerald-400/[0.06]";
  if (tone === "warn") return "border-amber-400/25 bg-amber-400/[0.06]";
  if (tone === "fail") return "border-rose-400/25 bg-rose-400/[0.06]";
  return "border-[var(--edge)] bg-white/[0.02]";
}

function badgeClass(tone: PipelineTone): string {
  if (tone === "pass") return "border-emerald-400/30 text-emerald-300";
  if (tone === "warn") return "border-amber-400/30 text-amber-300";
  if (tone === "fail") return "border-rose-400/30 text-rose-300";
  return "border-[var(--edge-bright)] text-[var(--fg-2)]";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}
