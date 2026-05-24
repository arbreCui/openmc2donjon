import type {
  SphLoopAuditRow,
  SphLoopPostprocess,
  SphLoopSolve,
  SphLoopWorkflow,
} from "@/lib/api";

export interface AuditTimelineProps {
  rows: SphLoopAuditRow[];
  solves: SphLoopSolve[];
  postprocesses?: SphLoopPostprocess[];
  workflows?: SphLoopWorkflow[];
}

export default function AuditTimeline({
  rows,
  solves,
  postprocesses = [],
  workflows = [],
}: AuditTimelineProps) {
  return (
    <div className="grid gap-5">
      <AuditRowsTable rows={rows} />
      <ExecutionLog solves={solves} postprocesses={postprocesses} workflows={workflows} />
    </div>
  );
}

function AuditRowsTable({ rows }: { rows: SphLoopAuditRow[] }) {
  return (
    <section className="glass rounded-xl p-4 min-w-0">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Per-iteration audit rows
          </h2>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            CSV-equivalent loop trace: residuals, SPH extrema, convergence,
            and artifact paths by iteration.
          </p>
        </div>
        <div className="text-[12px] text-[var(--fg-2)] tab-num">
          {rows.length} row{rows.length === 1 ? "" : "s"}
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--fg-3)]">
          No audit rows were recorded.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse text-left text-[12px]">
            <thead className="text-[var(--fg-3)]">
              <tr className="border-b border-[var(--edge)]">
                <th className="py-2 pr-3 font-medium">Iter</th>
                <th className="py-2 pr-3 font-medium">Stage</th>
                <th className="py-2 pr-3 font-medium">k-eff</th>
                <th className="py-2 pr-3 font-medium">SPH min/max</th>
                <th className="py-2 pr-3 font-medium">SPH rel</th>
                <th className="py-2 pr-3 font-medium">Flux residual</th>
                <th className="py-2 pr-3 font-medium">Worst bin</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Artifacts</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={`${row.stage}-${row.iteration}-${index}`}
                  className="border-b border-[var(--edge)] last:border-0"
                >
                  <td className="py-2 pr-3 align-top tab-num">
                    {row.iteration}
                  </td>
                  <td className="py-2 pr-3 align-top">
                    <span className="rounded border border-[var(--edge)] bg-white/5 px-2 py-0.5 font-mono">
                      {row.stage}
                    </span>
                  </td>
                  <td className="py-2 pr-3 align-top tab-num text-[var(--fg-2)]">
                    {formatNumber(row.keff)}
                  </td>
                  <td className="py-2 pr-3 align-top tab-num text-[var(--fg-2)]">
                    {formatRange(row.sph_minimum, row.sph_maximum)}
                  </td>
                  <td className="py-2 pr-3 align-top tab-num text-[var(--fg-2)]">
                    {formatNumber(row.sph_max_rel_change)}
                  </td>
                  <td className="py-2 pr-3 align-top tab-num text-[var(--fg-2)]">
                    {formatNumber(row.flux_ratio_max_residual)}
                  </td>
                  <td className="py-2 pr-3 align-top text-[var(--fg-2)]">
                    {formatWorstBin(row)}
                  </td>
                  <td className="py-2 pr-3 align-top">
                    <StatusPill converged={row.converged} />
                  </td>
                  <td className="py-2 pr-3 align-top text-[var(--fg-3)]">
                    <ArtifactList row={row} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ExecutionLog({
  solves,
  postprocesses,
  workflows,
}: {
  solves: SphLoopSolve[];
  postprocesses: SphLoopPostprocess[];
  workflows: SphLoopWorkflow[];
}) {
  const postByIteration = new Map(postprocesses.map((item) => [item.iteration, item]));
  const workflowByIteration = new Map(workflows.map((item) => [item.iteration, item]));
  return (
    <section className="glass rounded-xl p-4 min-w-0">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            Solver and SPH application log
          </h2>
          <p className="mt-1 text-[12px] text-[var(--fg-3)]">
            Commands, return codes, stdout/stderr files, and generated SPH
            handoff paths.
          </p>
        </div>
        <div className="text-[12px] text-[var(--fg-2)] tab-num">
          {solves.length} solve{solves.length === 1 ? "" : "s"}
        </div>
      </div>
      {solves.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--fg-3)]">
          No low-order solves were recorded.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {solves.map((solve) => (
            <details
              key={`${solve.iteration}-${solve.result}`}
              className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-3"
            >
              <summary className="cursor-pointer list-none">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold">
                      Solve iteration {solve.iteration}
                    </div>
                    <div className="mt-0.5 truncate font-mono text-[11px] text-[var(--fg-3)]">
                      {solve.result}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 text-[12px] tab-num">
                    <ReturnCodePill returncode={solve.returncode} />
                    <span className="text-[var(--fg-2)]">
                      keff {formatNumber(solve.keff)}
                    </span>
                  </div>
                </div>
              </summary>
              <div className="mt-3 grid gap-3 text-[12px]">
                <KeyValueGrid
                  items={[
                    ["cwd", solve.cwd],
                    ["ascii input", solve.ascii_input],
                    ["result", solve.result],
                    ["stdout", solve.stdout],
                    ["stderr", solve.stderr],
                    ["flux vectors", String(solve.flux_vector_count)],
                    ["flux unknowns", String(solve.flux_unknown_count)],
                    ["result bytes", String(solve.result_bytes)],
                  ]}
                />
                <CommandBlock command={solve.command} />
                {postByIteration.has(solve.iteration) ? (
                  <PostprocessBlock postprocess={postByIteration.get(solve.iteration)!} />
                ) : null}
                {workflowByIteration.has(solve.iteration) ? (
                  <WorkflowBlock workflow={workflowByIteration.get(solve.iteration)!} />
                ) : null}
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}

function PostprocessBlock({ postprocess }: { postprocess: SphLoopPostprocess }) {
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/10 p-3">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        SPH postprocess
      </div>
      <KeyValueGrid
        items={[
          ["return code", String(postprocess.returncode)],
          ["workflow ascii", postprocess.workflow_ascii],
          ["SPH sidecar", postprocess.sph_sidecar],
          ["output", postprocess.output],
          ["stdout", postprocess.stdout],
          ["stderr", postprocess.stderr],
          ["blocks", String(postprocess.block_count)],
          ["output bytes", String(postprocess.output_bytes)],
        ]}
      />
    </div>
  );
}

function WorkflowBlock({ workflow }: { workflow: SphLoopWorkflow }) {
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/10 p-3">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        SPH workflow outputs
      </div>
      <KeyValueGrid
        items={[
          ["summary", workflow.summary_json],
          ["volume flux", workflow.donjon_volume_flux_h5],
          ["SPH sidecar", workflow.sph_sidecar],
          ["augmented HDF5", workflow.augmented_h5],
          ["ASCII output", workflow.ascii_output],
          ["SPH min/max", formatRange(workflow.sph_minimum, workflow.sph_maximum)],
          ["normalization", workflow.flux_normalization ?? "—"],
          ["norm factor", formatNumber(workflow.normalization_factor)],
        ]}
      />
    </div>
  );
}

function KeyValueGrid({ items }: { items: [string, string][] }) {
  return (
    <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[max-content_minmax(0,1fr)]">
      {items.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-[var(--fg-3)]">{label}</dt>
          <dd className="min-w-0 break-all font-mono text-[var(--fg-1)]">
            {value || "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CommandBlock({ command }: { command: string[] }) {
  return (
    <div>
      <div className="mb-1 text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        Command
      </div>
      <pre className="max-h-40 overflow-auto rounded-md border border-[var(--edge)] bg-black/20 p-3 font-mono text-[11px] text-[var(--fg-1)]">
        {shellJoin(command)}
      </pre>
    </div>
  );
}

function ArtifactList({ row }: { row: SphLoopAuditRow }) {
  const artifacts = [
    ["solve", row.solve_result],
    ["ascii", row.ascii_output],
    ["post", row.postprocess_output],
  ].filter((item): item is [string, string] => item[1] != null && item[1] !== "");
  if (artifacts.length === 0) return <>—</>;
  return (
    <ul className="space-y-0.5">
      {artifacts.map(([label, path]) => (
        <li key={label} className="min-w-0">
          <span className="text-[var(--fg-3)]">{label}: </span>
          <span className="font-mono break-all">{path}</span>
        </li>
      ))}
    </ul>
  );
}

function StatusPill({ converged }: { converged: boolean | null }) {
  if (converged == null) {
    return (
      <span className="rounded border border-[var(--edge-bright)] bg-white/5 px-2 py-0.5 text-[var(--fg-2)]">
        —
      </span>
    );
  }
  return (
    <span
      className={
        "rounded border px-2 py-0.5 font-semibold " +
        (converged
          ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
          : "border-amber-400/30 bg-amber-400/10 text-amber-200")
      }
    >
      {converged ? "converged" : "running"}
    </span>
  );
}

function ReturnCodePill({ returncode }: { returncode: number }) {
  return (
    <span
      className={
        "rounded border px-2 py-0.5 font-semibold " +
        (returncode === 0
          ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
          : "border-rose-400/30 bg-rose-400/10 text-rose-200")
      }
    >
      rc {returncode}
    </span>
  );
}

function formatWorstBin(row: SphLoopAuditRow): string {
  if (row.worst_residual_mixture == null && row.worst_residual_group == null) {
    return "—";
  }
  const mixture = row.worst_residual_mixture ?? "unknown";
  const group = row.worst_residual_group == null ? "?" : String(row.worst_residual_group);
  const residual = formatNumber(row.worst_residual);
  const raw = formatNumber(row.worst_residual_raw_update);
  return `${mixture} g${group}; residual ${residual}; raw ${raw}`;
}

function formatRange(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  return `${formatNumber(min)} / ${formatNumber(max)}`;
}

function formatNumber(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1.0e-3 && abs < 1.0e4) return value.toPrecision(4);
  return value.toExponential(3);
}

function shellJoin(command: string[]): string {
  return command.map(shellQuote).join(" ");
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:=+-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}
