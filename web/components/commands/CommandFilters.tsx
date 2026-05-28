"use client";

import Link from "next/link";
import type { CommandCatalog, CommandStatus } from "@/lib/api";
import type { CommandGoal } from "@/lib/commandGoals";

export function CommandFilters({
  data,
  activeGoal,
  onClearGoal,
  query,
  onQuery,
  groupFilter,
  onGroupFilter,
  statusFilter,
  onStatusFilter,
  surfaceFilter,
  onSurfaceFilter,
  surfaceOptions,
  resultCount,
}: {
  data: CommandCatalog;
  activeGoal: CommandGoal | null;
  onClearGoal: () => void;
  query: string;
  onQuery: (value: string) => void;
  groupFilter: string;
  onGroupFilter: (value: string) => void;
  statusFilter: CommandStatus | "all";
  onStatusFilter: (value: CommandStatus | "all") => void;
  surfaceFilter: string;
  onSurfaceFilter: (value: string) => void;
  surfaceOptions: [string, string][];
  resultCount: number;
}) {
  return (
    <section className="glass rounded-lg p-4">
      {activeGoal ? (
        <div className="mb-4 grid gap-3 rounded-md border border-emerald-400/25 bg-emerald-400/[0.06] px-3 py-3 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-200">
              Filtering by user goal
            </div>
            <div className="mt-0.5 text-sm text-[var(--fg-1)]">
              {activeGoal.title}{" "}
              <span className="text-[12px] text-[var(--fg-3)] tab-num">
                ({activeGoal.commands.length}/{activeGoal.commandIds.length} catalog
                commands)
              </span>
            </div>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              <span className="text-[var(--fg-3)]">Recommended next action: </span>
              {activeGoal.actionHint}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href={activeGoal.href} className="btn btn-primary">
              {activeGoal.cta}
            </Link>
            <button type="button" onClick={onClearGoal} className="btn btn-secondary">
              Show all commands
            </button>
          </div>
        </div>
      ) : null}
      <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
        <label>
          <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            Search
          </span>
          <input
            type="search"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="command, tag, summary, CLI..."
            className="mt-1 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
          />
        </label>
        <div className="text-[12px] text-[var(--fg-3)] tab-num">
          {resultCount} / {data.commands.length} commands
        </div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <FilterRow
          label="Workflow"
          value={groupFilter}
          options={[
            ["all", "All"],
            ...data.groups.map((group) => [group.id, group.label] as [string, string]),
          ]}
          onChange={onGroupFilter}
        />
        <FilterRow
          label="Status"
          value={statusFilter}
          options={[
            ["all", "All"],
            ["ready", "Ready"],
            ["partial", "Partial"],
            ["planned", "CLI only"],
          ]}
          onChange={(value) => onStatusFilter(value as CommandStatus | "all")}
        />
        <FilterRow
          label="Web surface"
          value={surfaceFilter}
          options={surfaceOptions}
          onChange={onSurfaceFilter}
        />
      </div>
    </section>
  );
}

function FilterRow({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <fieldset>
      <legend className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </legend>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {options.map(([id, text]) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={
              "rounded-md border px-2.5 py-1 text-[12px] transition " +
              (value === id
                ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-200"
                : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)] hover:text-[var(--fg-0)]")
            }
          >
            {text}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
