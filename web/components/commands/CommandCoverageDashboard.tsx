"use client";

import type { CommandCoverage } from "@/lib/commandCoverage";

export function CoverageDashboard({
  coverage,
  embedded = false,
}: {
  coverage: CommandCoverage;
  embedded?: boolean;
}) {
  const summaryGridClass =
    (embedded ? "" : "mt-4 ") + "grid gap-2 sm:grid-cols-2 lg:grid-cols-5";
  return (
    <section className={embedded ? "" : "glass rounded-lg p-5"}>
      {embedded ? null : (
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight">
              Web command coverage
            </h2>
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
              Which commands already have a web surface, which are command
              builders/planners, and which still fall back to CLI-only use.
            </p>
          </div>
          <span className="rounded border border-emerald-300/25 bg-emerald-300/[0.06] px-2 py-1 font-mono text-[11px] text-emerald-200">
            {coverage.coveragePercent}% linked
          </span>
        </div>
      )}

      <div className={summaryGridClass}>
        <CoverageTile label="commands" value={coverage.total} tone="neutral" />
        <CoverageTile label="web linked" value={coverage.webLinked} tone="pass" />
        <CoverageTile label="ready" value={coverage.ready} tone="pass" />
        <CoverageTile label="partial" value={coverage.partial} tone="accent" />
        <CoverageTile label="CLI only" value={coverage.cliOnly} tone="warn" />
      </div>

      <StatusLegend />

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
        <div className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
          <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            Coverage by workflow group
          </div>
          <div className="mt-3 space-y-2">
            {coverage.groups.map((group) => (
              <div
                key={group.id}
                className="grid gap-2 rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 md:grid-cols-[1fr_160px_auto] md:items-center"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{group.label}</div>
                  <div className="mt-0.5 text-[12px] text-[var(--fg-3)] tab-num">
                    {group.webLinked}/{group.total} linked · {group.ready} ready ·{" "}
                    {group.partial} partial · {group.planned} CLI only
                  </div>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className="h-full rounded-full bg-emerald-400/70"
                    style={{ width: `${group.coveragePercent}%` }}
                  />
                </div>
                <div className="font-mono text-[12px] text-[var(--fg-2)]">
                  {group.coveragePercent}%
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
          <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            Web surfaces
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {coverage.surfaces.map((surface) => (
              <span
                key={surface.surface}
                className="rounded border border-[var(--edge)] bg-white/[0.03] px-2 py-1 text-[12px] text-[var(--fg-1)]"
              >
                {surface.surface}:{" "}
                <span className="font-mono tab-num">{surface.count}</span>
              </span>
            ))}
          </div>
          <p className="mt-3 text-[12px] leading-5 text-[var(--fg-3)]">
            Ready commands are first-class web flows. Partial commands are
            planners, viewers, or command builders that still leave the actual
            production mutation to the CLI.
          </p>
        </div>
      </div>
    </section>
  );
}

function StatusLegend() {
  const items = [
    {
      label: "Ready",
      tone: "pass",
      text: "First-class web workflow: inspect, convert, or review directly in the browser.",
    },
    {
      label: "Partial",
      tone: "accent",
      text: "Planner/viewer/builder: the web UI prepares the command or report, while production file mutation stays in the CLI.",
    },
    {
      label: "Command builder",
      tone: "neutral",
      text: "A structured form for paths and common flags. It never executes the command.",
    },
    {
      label: "CLI only",
      tone: "warn",
      text: "No web path yet. The catalog still documents the command and equivalent CLI.",
    },
  ] as const;
  return (
    <div className="mt-4 grid gap-2 md:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className={"rounded-md border px-3 py-2 " + coverageTileClass(item.tone)}
        >
          <div className="text-[12px] font-semibold tracking-tight">{item.label}</div>
          <div className="mt-1 text-[11px] leading-4 opacity-80">{item.text}</div>
        </div>
      ))}
    </div>
  );
}

function CoverageTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "neutral" | "pass" | "warn" | "accent";
}) {
  return (
    <div className={"rounded-md border px-3 py-2 " + coverageTileClass(tone)}>
      <div className="font-mono text-lg tab-num">{value}</div>
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
        {label}
      </div>
    </div>
  );
}

function coverageTileClass(tone: "neutral" | "pass" | "warn" | "accent") {
  if (tone === "pass") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (tone === "warn") {
    return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  }
  if (tone === "accent") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)]";
}
