"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  CommandCatalog,
  CommandCatalogEntry,
  CommandStatus,
  api,
} from "@/lib/api";
import TaskLauncher from "@/components/TaskLauncher";
import { commandCoverage } from "@/lib/commandCoverage";
import {
  commandGoalCommandIds,
  commandGoals,
  type CommandGoalId,
} from "@/lib/commandGoals";
import { commandWorkflowMapping } from "@/lib/commandWorkflowMapping";
import { TASK_ENTRYPOINTS } from "@/lib/taskEntrypoints";
import { CommandFilters } from "@/components/commands/CommandFilters";
import {
  CommandGroupSection,
  FeaturedCommand,
} from "@/components/commands/CommandCards";
import { CoverageDashboard } from "@/components/commands/CommandCoverageDashboard";
import { GoalCommandGuide } from "@/components/commands/CommandGoalGuide";
import { WorkflowMap } from "@/components/commands/CommandWorkflowMap";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: CommandCatalog }
  | { kind: "error"; message: string };

const STATUS_ORDER: CommandStatus[] = ["ready", "partial", "planned"];

export default function CommandWorkspace() {
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
              <span className="grad-text">Command reference</span>
            </h1>
            <p className="mt-2 text-sm text-[var(--fg-2)]">
              Advanced reference for CLI commands and their web surfaces. For
              normal work, start with Convert; use this page when you need the
              lower-level command behind a workflow step.
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

        <TaskLauncher
          title="Main product paths"
          summary="These are the routes users should click first. The catalog below is for advanced command lookup and troubleshooting."
          entries={TASK_ENTRYPOINTS}
          className="mb-6"
        />

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
  const [surfaceFilter, setSurfaceFilter] = useState("all");
  const [activeGoalId, setActiveGoalId] = useState<CommandGoalId | "all">("all");

  const handleGoalFilterChange = useCallback((value: CommandGoalId | "all") => {
    setActiveGoalId(value);
    if (value !== "all") {
      setQuery("");
      setGroupFilter("all");
      setStatusFilter("all");
      setSurfaceFilter("all");
    }
  }, []);

  const surfaceOptions = useMemo(
    () => [
      ["all", "All"] as [string, string],
      ...Array.from(
        new Set(
          data.commands.map((command) => commandWorkflowMapping(command).surface),
        ),
      ).map((surface) => [surface, surface] as [string, string]),
    ],
    [data.commands],
  );
  const coverage = useMemo(() => commandCoverage(data), [data]);
  const goals = useMemo(() => commandGoals(data.commands), [data.commands]);
  const activeGoal = useMemo(
    () => goals.find((goal) => goal.id === activeGoalId) ?? null,
    [activeGoalId, goals],
  );
  const activeGoalCommandIds = useMemo(() => {
    if (activeGoalId === "all") return null;
    return new Set(commandGoalCommandIds(activeGoalId));
  }, [activeGoalId]);
  const filteredCommands = useMemo(
    () =>
      data.commands.filter((command) =>
        commandMatches(command, {
          query,
          group: groupFilter,
          status: statusFilter,
          surface: surfaceFilter,
          goalCommandIds: activeGoalCommandIds,
        }),
      ),
    [
      activeGoalCommandIds,
      data.commands,
      groupFilter,
      query,
      statusFilter,
      surfaceFilter,
    ],
  );
  const featured = filteredCommands.find((command) => command.id === "direct-convert");
  const commandsByGroup = useMemo(
    () => groupCommands(filteredCommands.filter((command) => command.id !== featured?.id)),
    [featured?.id, filteredCommands],
  );

  return (
    <div className="space-y-6">
      <ReferenceNotice />
      <GoalCommandGuide
        goals={goals}
        activeGoalId={activeGoalId}
        onGoalFilterChange={handleGoalFilterChange}
      />
      <WorkflowMap commands={data.commands} />
      <details className="glass rounded-lg p-5">
        <summary className="cursor-pointer text-base font-semibold tracking-tight">
          Web command coverage
        </summary>
        <div className="mt-4">
          <CoverageDashboard coverage={coverage} embedded />
        </div>
      </details>
      <CommandFilters
        data={data}
        activeGoal={activeGoal}
        onClearGoal={() => handleGoalFilterChange("all")}
        query={query}
        onQuery={setQuery}
        groupFilter={groupFilter}
        onGroupFilter={setGroupFilter}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        surfaceFilter={surfaceFilter}
        onSurfaceFilter={setSurfaceFilter}
        surfaceOptions={surfaceOptions}
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

function ReferenceNotice() {
  return (
    <section className="rounded-xl border border-amber-300/20 bg-amber-300/[0.045] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-amber-100/80">
            Advanced page
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight text-amber-50">
            This is not the main converter flow
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Use Commands when you need to inspect a CLI flag, copy a lower-level
            command, or debug a workflow. The product path remains: Convert
            existing HDF5, or prepare OpenMC inputs before converting.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/convert?intent=direct-convert&format=multicompo&check=1&production=1"
            className="btn btn-primary"
          >
            Open converter
          </Link>
          <Link
            href="/openmc?workflow=two-step&equivalence=sph&production=1"
            className="btn btn-secondary"
          >
            Prepare SPH inputs
          </Link>
        </div>
      </div>
    </section>
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
  filters: {
    query: string;
    group: string;
    status: CommandStatus | "all";
    surface: string;
    goalCommandIds: ReadonlySet<string> | null;
  },
) {
  if (filters.goalCommandIds != null && !filters.goalCommandIds.has(command.id)) {
    return false;
  }
  if (filters.group !== "all" && command.group !== filters.group) return false;
  if (filters.status !== "all" && command.status !== filters.status) return false;
  const mapping = commandWorkflowMapping(command);
  if (filters.surface !== "all" && mapping.surface !== filters.surface) {
    return false;
  }
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
    mapping.surface,
    mapping.title,
    mapping.summary,
    ...mapping.presets,
    ...mapping.requiredInputs,
    ...command.tags,
    ...command.aliases,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function statusTextClass(status: CommandStatus) {
  if (status === "ready") return "text-emerald-300";
  if (status === "partial") return "text-cyan-300";
  return "text-[var(--fg-1)]";
}
