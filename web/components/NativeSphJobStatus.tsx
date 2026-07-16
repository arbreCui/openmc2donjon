import React from "react";
import type { ExecutionJob } from "../lib/api";
import { nativeSphJobIsActive } from "../lib/nativeSphRunner";

export default function NativeSphJobStatus({ job }: { job: ExecutionJob }) {
  const active = nativeSphJobIsActive(job);
  return (
    <div className="grid gap-3" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={
            "rounded-full border px-2 py-1 font-mono text-[9px] uppercase " +
            (job.status === "completed"
              ? "border-emerald-300/25 text-emerald-100"
              : job.status === "failed"
                ? "border-rose-300/25 text-rose-100"
                : "border-cyan-300/25 text-cyan-100")
          }
        >
          {job.status}
        </span>
        <code className="text-[10px] text-[var(--fg-3)]">
          archived run {job.run_id || job.job_id}
        </code>
      </div>
      <p className="text-[11px] text-[var(--fg-2)]">{job.message}</p>
      <dl className="grid gap-2 text-[10px] sm:grid-cols-2">
        <JobField
          label="Deck"
          value={job.deck_path ?? (active ? "pending" : "not written")}
        />
        <JobField
          label="Result"
          value={job.result_path ?? (active ? "pending" : "not produced")}
        />
        <JobField
          label="Declared working directory"
          value={job.working_directory ?? "not declared"}
        />
        <JobField
          label="Run archive"
          value={job.run_directory ?? (active ? "pending" : "not persisted")}
        />
        <JobField
          label="Return code"
          value={
            job.return_code == null
              ? active
                ? "pending"
                : "not reported"
              : String(job.return_code)
          }
        />
        <JobField
          label="Reported k-effective"
          value={
            job.k_effective == null
              ? "not required by this job transport"
              : job.k_effective.toFixed(8)
          }
        />
      </dl>
      {job.artifacts_path ? (
        <div className="rounded-md border border-[var(--edge)] bg-black/10 px-3 py-2 text-[10px] leading-4 text-[var(--fg-2)]">
          SHA-256 evidence manifest: <code>{job.artifacts_path}</code>
        </div>
      ) : null}
      <details
        className="rounded-md border border-[var(--edge)] bg-black/10 p-3"
        open={job.status === "failed"}
      >
        <summary className="cursor-pointer text-[10px] font-semibold text-[var(--fg-2)]">
          Bounded DONJON log tail
        </summary>
        <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-black/25 px-3 py-2 font-mono text-[10px] leading-4 text-[var(--fg-2)]">
          {job.log_tail ||
            (active
              ? "Log tail will be available when the current backend returns it."
              : "No log text was returned.")}
        </pre>
      </details>
      <div className="rounded-md border border-amber-300/20 bg-amber-300/[0.05] px-3 py-2 text-[10px] leading-4 text-amber-100">
        Archived run <strong>{job.run_id || job.job_id}</strong> with process
        status <strong>{job.status}</strong> describes execution only. It does
        not set Project physics acceptance.
      </div>
    </div>
  );
}

function JobField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--edge)] bg-black/10 px-2 py-2">
      <dt className="uppercase tracking-[0.12em] text-[var(--fg-3)]">{label}</dt>
      <dd className="mt-1 break-all font-mono text-[var(--fg-1)]">{value}</dd>
    </div>
  );
}
