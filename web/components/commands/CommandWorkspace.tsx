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
import {
  commandGoalCommandIds,
  commandGoals,
  type CommandGoalId,
} from "@/lib/commandGoals";
import { commandWorkflowMapping } from "@/lib/commandWorkflowMapping";
import { CommandFilters } from "@/components/commands/CommandFilters";
import { CommandGroupSection } from "@/components/commands/CommandCards";
import { GoalCommandGuide } from "@/components/commands/CommandGoalGuide";
import { WorkflowMap } from "@/components/commands/CommandWorkflowMap";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: CommandCatalog }
  | { kind: "error"; message: string };

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
    <main className="app-page">
      <div className="app-container max-w-6xl">
        <header className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="page-kicker">Advanced tools</div>
            <h1 className="text-3xl font-bold tracking-tight">
              Command reference
            </h1>
            <p className="mt-2 text-sm text-[var(--fg-2)]">
              Advanced reference for CLI commands and their web surfaces. For
              normal work, start with the Converter; use this page when you
              need the lower-level command behind a workflow step.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Link
              href="/convert?intent=direct-convert&format=multicompo&check=1&production=1"
              className="btn btn-primary"
            >
              Open Converter
            </Link>
            {state.kind === "error" ? (
              <button type="button" onClick={refresh} className="btn btn-secondary">
                Refresh
              </button>
            ) : null}
          </div>
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
  const commandsByGroup = useMemo(
    () => groupCommands(filteredCommands),
    [filteredCommands],
  );

  return (
    <div className="space-y-6">
      <GoalCommandGuide
        goals={goals}
        activeGoalId={activeGoalId}
        onGoalFilterChange={handleGoalFilterChange}
      />
      <WorkflowMap commands={data.commands} />
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
      <StatusLegendLine />
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

function StatusLegendLine() {
  return (
    <p className="text-[12px] leading-5 text-[var(--fg-3)]">
      <span className="text-emerald-300">Ready</span> = full web flow ·{" "}
      <span className="text-cyan-300">Builder</span> = web builds the command,
      CLI executes · CLI only = documented and copyable here.
    </p>
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
