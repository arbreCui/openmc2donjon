"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { OpenmcWorkflowArtifact } from "@/lib/api";

export default function OpenmcArtifactList({
  artifacts,
  writtenHdf5Path = null,
}: {
  artifacts: OpenmcWorkflowArtifact[];
  writtenHdf5Path?: string | null;
}) {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Artifacts</h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            This list is a plan, not evidence that a file exists. A written
            MGXS HDF5 becomes inspectable only after export succeeds.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {artifacts.length} file{artifacts.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-3 space-y-2">
        {artifacts.map((artifact) => {
          const written =
            artifact.kind === "hdf5" &&
            writtenHdf5Path != null &&
            samePlannedOrResolvedPath(artifact.path, writtenHdf5Path);
          const writtenPath = written ? writtenHdf5Path : null;
          return (
          <article
            key={`${artifact.label}-${artifact.path}`}
            className="rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-sm font-medium">{artifact.label}</div>
                  <span className="rounded border border-[var(--edge)] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--fg-2)]">
                    {artifact.kind}
                  </span>
                  <span
                    className={
                      "rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider " +
                      (artifact.will_write
                        ? "border-emerald-400/25 text-emerald-300"
                        : "border-[var(--edge)] text-[var(--fg-3)]")
                    }
                  >
                    {written ? "written" : artifact.will_write ? "planned" : "skipped"}
                  </span>
                </div>
                <div className="mt-1 break-all font-mono text-[12px] text-[var(--fg-2)]">
                  {artifact.path}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                {artifact.kind === "hdf5" && writtenPath ? (
                  <Link
                    href={`/inspect?path=${encodeURIComponent(writtenPath)}`}
                    className="btn btn-secondary"
                  >
                    Inspect
                  </Link>
                ) : artifact.kind === "hdf5" ? (
                  <span className="rounded-md border border-[var(--edge)] px-3 py-2 text-[11px] text-[var(--fg-3)]">
                    Inspect after write
                  </span>
                ) : null}
                <CopyCliButton
                  value={artifact.path}
                  label="Copy path"
                  ariaLabel={`Copy path for ${artifact.label}`}
                  compact
                />
              </div>
            </div>
          </article>
          );
        })}
      </div>
    </section>
  );
}

function samePlannedOrResolvedPath(planned: string, written: string): boolean {
  if (planned === written) return true;
  const normalizedPlanned = planned.replace(/\/+/g, "/");
  const normalizedWritten = written.replace(/\/+/g, "/");
  return normalizedWritten.endsWith(`/${normalizedPlanned.replace(/^\.\//, "")}`);
}
