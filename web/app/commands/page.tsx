"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  CommandCatalog,
  CommandCatalogEntry,
  CommandGroup,
  CommandStatus,
  api,
} from "@/lib/api";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { CommandWorkflowMapping } from "@/lib/commandWorkflowMapping";
import { commandWorkflowMapping } from "@/lib/commandWorkflowMapping";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: CommandCatalog }
  | { kind: "error"; message: string };

const STATUS_ORDER: CommandStatus[] = ["ready", "partial", "planned"];
const WORKFLOW_STEPS = [
  {
    label: "OpenMC",
    detail: "recipe / statepoint",
    href: "/openmc",
  },
  {
    label: "HDF5",
    detail: "MGXS handoff",
    href: "/inspect",
  },
  {
    label: "Equivalence",
    detail: "optional ADF or SPH",
    href: "/commands",
  },
  {
    label: "Convert",
    detail: "MULTICOMPO / MACROLIB",
    href: "/convert",
  },
  {
    label: "DONJON",
    detail: "solve / audit",
    href: "/audit",
  },
];

export default function CommandsPage() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await api.commands();
      setState({ kind: "ok", data });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Unknown error";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              <span className="grad-text">Command workspace</span>
            </h1>
            <p className="mt-2 text-sm text-[var(--fg-2)]">
              Production commands grouped by workflow, with web surfaces and
              equivalent CLI entry points side by side.
            </p>
          </div>
          {state.kind === "ok" ? (
            <StatusCounts data={state.data} />
          ) : (
            <button type="button" onClick={refresh} className="btn btn-secondary">
              Refresh
            </button>
          )}
        </header>

        {state.kind === "loading" ? (
          <section className="glass rounded-lg p-5 text-sm text-[var(--fg-2)]">
            Loading command catalog…
          </section>
        ) : null}

        {state.kind === "error" ? (
          <section className="glass rounded-lg p-5">
            <div className="text-sm font-semibold text-rose-300">
              Command catalog failed
            </div>
            <div className="mt-1 text-sm text-[var(--fg-2)]">
              {state.message}
            </div>
          </section>
        ) : null}

        {state.kind === "ok" ? <Catalog data={state.data} /> : null}
      </div>
    </main>
  );
}

function StatusCounts({ data }: { data: CommandCatalog }) {
  return (
    <div className="grid grid-cols-3 gap-2 text-right text-[12px] tab-num">
      {STATUS_ORDER.map((status) => (
        <div
          key={status}
          className="rounded-md border border-[var(--edge)] bg-white/[0.03] px-3 py-2"
        >
          <div className={statusTextClass(status)}>
            {data.status_counts[status] ?? 0}
          </div>
          <div className="uppercase tracking-wider text-[var(--fg-3)]">
            {status}
          </div>
        </div>
      ))}
    </div>
  );
}

function Catalog({ data }: { data: CommandCatalog }) {
  const [query, setQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<CommandStatus | "all">("all");
  const filteredCommands = useMemo(
    () =>
      data.commands.filter((command) =>
        commandMatches(command, {
          query,
          group: groupFilter,
          status: statusFilter,
        }),
      ),
    [data.commands, groupFilter, query, statusFilter],
  );
  const featured = filteredCommands.find((command) => command.id === "direct-convert");
  const commandsByGroup = useMemo(
    () => groupCommands(filteredCommands.filter((command) => command.id !== featured?.id)),
    [featured?.id, filteredCommands],
  );

  return (
    <div className="space-y-6">
      <WorkflowMap />
      <CommandFilters
        data={data}
        query={query}
        onQuery={setQuery}
        groupFilter={groupFilter}
        onGroupFilter={setGroupFilter}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        resultCount={filteredCommands.length}
      />
      {featured ? <FeaturedCommand command={featured} /> : null}
      {data.groups.map((group) => {
        const commands = commandsByGroup.get(group.id) ?? [];
        if (commands.length === 0) return null;
        return (
          <CommandGroupSection key={group.id} group={group} commands={commands} />
        );
      })}
      {filteredCommands.length === 0 ? (
        <section className="glass rounded-lg p-5 text-sm text-[var(--fg-2)]">
          No commands match the current filters.
        </section>
      ) : null}
    </div>
  );
}

function WorkflowMap() {
  return (
    <section className="glass rounded-lg p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold tracking-tight">Workflow map</h2>
        <span className="text-[12px] text-[var(--fg-3)]">
          command families in production order
        </span>
      </div>
      <div className="grid gap-2 md:grid-cols-5">
        {WORKFLOW_STEPS.map((step, index) => (
          <Link
            key={step.label}
            href={step.href}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-3 hover:border-[var(--edge-bright)]"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                {String(index + 1).padStart(2, "0")}
              </span>
              {index + 1 < WORKFLOW_STEPS.length ? (
                <span className="text-[var(--fg-3)]">to</span>
              ) : null}
            </div>
            <div className="mt-2 text-sm font-semibold">{step.label}</div>
            <div className="mt-1 text-[12px] text-[var(--fg-2)]">{step.detail}</div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function CommandFilters({
  data,
  query,
  onQuery,
  groupFilter,
  onGroupFilter,
  statusFilter,
  onStatusFilter,
  resultCount,
}: {
  data: CommandCatalog;
  query: string;
  onQuery: (value: string) => void;
  groupFilter: string;
  onGroupFilter: (value: string) => void;
  statusFilter: CommandStatus | "all";
  onStatusFilter: (value: CommandStatus | "all") => void;
  resultCount: number;
}) {
  return (
    <section className="glass rounded-lg p-4">
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

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
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

function FeaturedCommand({ command }: { command: CommandCatalogEntry }) {
  const mapping = commandWorkflowMapping(command);
  return (
    <section className="glass rounded-lg p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={command.status} label={command.status_label} />
            <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              first workflow
            </span>
          </div>
          <h2 className="text-lg font-semibold tracking-tight">
            {command.title}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-[var(--fg-2)]">
            {command.summary}
          </p>
          <p className="mt-3 max-w-2xl text-sm text-[var(--fg-1)]">
            <span className="text-[var(--fg-3)]">Use when: </span>
            {command.use_when}
          </p>
        </div>
        {command.web_path ? (
          <Link href={command.web_path} className="btn btn-primary shrink-0">
            Open converter
          </Link>
        ) : null}
      </div>
      <WorkflowMappingHint mapping={mapping} />
      <CliLine value={command.cli} />
      <div className="mt-3">
        <CopyCliButton value={command.cli} />
      </div>
    </section>
  );
}

function CommandGroupSection({
  group,
  commands,
}: {
  group: CommandGroup;
  commands: CommandCatalogEntry[];
}) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            {group.label}
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">{group.summary}</p>
        </div>
        <div className="text-[12px] text-[var(--fg-3)] tab-num">
          {commands.length} commands
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {commands.map((command) => (
          <CommandCard key={command.id} command={command} />
        ))}
      </div>
    </section>
  );
}

function CommandCard({ command }: { command: CommandCatalogEntry }) {
  const mapping = commandWorkflowMapping(command);
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">
            {command.title}
          </h3>
          <div className="mt-1 font-mono text-[12px] text-[var(--fg-3)]">
            {command.name}
          </div>
        </div>
        <StatusBadge status={command.status} label={command.status_label} />
      </div>
      <p className="min-h-[3.25rem] text-sm text-[var(--fg-2)]">
        {command.summary}
      </p>
      <div className="mt-3 rounded-md border border-[var(--edge)] bg-black/10 px-3 py-2">
        <div className="text-[10px] uppercase tracking-wider text-[var(--fg-3)]">
          Use when
        </div>
        <p className="mt-1 text-[12px] leading-5 text-[var(--fg-1)]">
          {command.use_when}
        </p>
      </div>
      <WorkflowMappingHint mapping={mapping} compact />
      <TagRow tags={command.tags} />
      <CliLine value={command.cli} compact />
      <div className="mt-3 flex items-center justify-between gap-3">
        <AliasText aliases={command.aliases} />
        <div className="flex shrink-0 items-center gap-2">
          <CopyCliButton value={command.cli} compact />
          <Link href={`/commands/${command.id}`} className="btn btn-secondary">
            Details
          </Link>
          {command.web_path ? (
            <Link href={command.web_path} className="btn btn-primary">
              Open
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function WorkflowMappingHint({
  mapping,
  compact = false,
}: {
  mapping: CommandWorkflowMapping;
  compact?: boolean;
}) {
  const visiblePresets = compact ? mapping.presets.slice(0, 2) : mapping.presets;
  const hiddenCount = mapping.presets.length - visiblePresets.length;
  return (
    <div
      className={
        "mt-3 rounded-md border bg-black/10 " +
        (compact ? "px-3 py-2" : "px-4 py-3") +
        " " +
        (mapping.available
          ? "border-emerald-400/20"
          : "border-[var(--edge)]")
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-[10px] uppercase tracking-wider text-[var(--fg-3)]">
          Web workflow
        </div>
        <span
          className={
            "rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider " +
            (mapping.available
              ? "border-emerald-400/30 text-emerald-300"
              : "border-[var(--edge-bright)] text-[var(--fg-3)]")
          }
        >
          {mapping.surface}
        </span>
      </div>
      <p
        className={
          "mt-1 leading-5 " +
          (compact ? "text-[12px]" : "text-sm") +
          " text-[var(--fg-2)]"
        }
      >
        {compact ? mapping.title : mapping.summary}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {visiblePresets.map((preset) => (
          <span
            key={preset}
            className="rounded border border-[var(--edge)] bg-white/[0.03] px-2 py-0.5 text-[11px] text-[var(--fg-1)]"
          >
            {preset}
          </span>
        ))}
        {hiddenCount > 0 ? (
          <span className="rounded border border-[var(--edge)] bg-white/[0.02] px-2 py-0.5 text-[11px] text-[var(--fg-3)]">
            +{hiddenCount} more
          </span>
        ) : null}
      </div>
    </div>
  );
}

function StatusBadge({
  status,
  label,
}: {
  status: CommandStatus;
  label: string;
}) {
  return (
    <span
      className={
        "shrink-0 rounded-md border px-2 py-1 text-[11px] font-medium " +
        statusBadgeClass(status)
      }
    >
      {label}
    </span>
  );
}

function TagRow({ tags }: { tags: string[] }) {
  if (tags.length === 0) return <div className="mt-3 h-6" />;
  return (
    <div className="mt-3 flex min-h-6 flex-wrap gap-1.5">
      {tags.map((tag) => (
        <span
          key={tag}
          className="rounded-md border border-[var(--edge)] bg-white/[0.03] px-2 py-0.5 text-[11px] text-[var(--fg-2)]"
        >
          {tag}
        </span>
      ))}
    </div>
  );
}

function CliLine({ value, compact = false }: { value: string; compact?: boolean }) {
  return (
    <div
      className={
        "mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 " +
        (compact ? "px-2 py-1.5" : "px-3 py-2")
      }
    >
      <code className="whitespace-nowrap font-mono text-[12px] text-[var(--fg-1)]">
        {value}
      </code>
    </div>
  );
}

function AliasText({ aliases }: { aliases: string[] }) {
  if (aliases.length === 0) {
    return <span className="text-[12px] text-[var(--fg-3)]">no aliases</span>;
  }
  return (
    <span className="text-[12px] text-[var(--fg-3)]">
      alias:{" "}
      <span className="font-mono text-[var(--fg-2)]">{aliases.join(", ")}</span>
    </span>
  );
}

function groupCommands(commands: CommandCatalogEntry[]) {
  const grouped = new Map<string, CommandCatalogEntry[]>();
  for (const command of commands) {
    const existing = grouped.get(command.group) ?? [];
    existing.push(command);
    grouped.set(command.group, existing);
  }
  return grouped;
}

function commandMatches(
  command: CommandCatalogEntry,
  filters: { query: string; group: string; status: CommandStatus | "all" },
) {
  if (filters.group !== "all" && command.group !== filters.group) return false;
  if (filters.status !== "all" && command.status !== filters.status) return false;
  const query = filters.query.trim().toLowerCase();
  if (!query) return true;
  const haystack = [
    command.id,
    command.name,
    command.title,
    command.summary,
    command.cli,
    command.cli_help,
    command.use_when,
    command.produces,
    command.next_step,
    ...command.tags,
    ...command.aliases,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function statusBadgeClass(status: CommandStatus) {
  if (status === "ready") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }
  if (status === "partial") {
    return "border-cyan-300/30 bg-cyan-300/10 text-cyan-200";
  }
  return "border-[var(--edge-bright)] bg-white/[0.04] text-[var(--fg-2)]";
}

function statusTextClass(status: CommandStatus) {
  if (status === "ready") return "text-emerald-300";
  if (status === "partial") return "text-cyan-300";
  return "text-[var(--fg-1)]";
}
