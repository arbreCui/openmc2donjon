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
import TaskLauncher from "@/components/TaskLauncher";
import { CommandCoverage, commandCoverage } from "@/lib/commandCoverage";
import {
  commandGoalCommandIds,
  commandGoals,
  type CommandGoal,
  type CommandGoalId,
} from "@/lib/commandGoals";
import type { CommandWorkflowMapping } from "@/lib/commandWorkflowMapping";
import { commandWorkflowMapping } from "@/lib/commandWorkflowMapping";
import { COMMAND_WORKFLOW_LANES } from "@/lib/commandWorkflowLanes";
import { TASK_ENTRYPOINTS } from "@/lib/taskEntrypoints";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: CommandCatalog }
  | { kind: "error"; message: string };

const STATUS_ORDER: CommandStatus[] = ["ready", "partial", "planned"];
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

        <TaskLauncher
          title="Start from the user task"
          summary="Use these shortcuts when you know your current artifact. The full command catalog remains below for lower-level tools."
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
      <GoalCommandGuide
        goals={goals}
        activeGoalId={activeGoalId}
        onGoalFilterChange={handleGoalFilterChange}
      />
      <WorkflowMap commands={data.commands} />
      <CoverageDashboard coverage={coverage} />
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

function GoalCommandGuide({
  goals,
  activeGoalId,
  onGoalFilterChange,
}: {
  goals: CommandGoal[];
  activeGoalId: CommandGoalId | "all";
  onGoalFilterChange: (value: CommandGoalId | "all") => void;
}) {
  return (
    <section className="glass rounded-lg p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Choose by user goal
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Start from what the user is trying to accomplish. Each card shows
            the web entry point plus the CLI commands that support that goal.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          goal -&gt; command
        </span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {goals.map((goal) => {
          const isActive = activeGoalId === goal.id;
          return (
            <article
              key={goal.id}
              className={
                "rounded-lg border p-4 transition " +
                (isActive
                  ? "border-emerald-400/35 bg-emerald-400/[0.07]"
                  : "border-[var(--edge)] bg-white/[0.025]")
              }
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                    {goal.eyebrow}
                  </div>
                  <h3 className="mt-2 text-sm font-semibold tracking-tight">
                    {goal.title}
                  </h3>
                </div>
                <GoalStatusPill goal={goal} />
              </div>
              <p className="mt-2 min-h-[3.75rem] text-[12px] leading-5 text-[var(--fg-2)]">
                {goal.body}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {goal.commands.slice(0, 6).map((command) => (
                  <CommandChip key={`${goal.id}-${command.id}`} command={command} />
                ))}
                {goal.commands.length > 6 ? (
                  <span className="rounded border border-[var(--edge)] bg-white/[0.02] px-2 py-0.5 text-[10px] text-[var(--fg-3)]">
                    +{goal.commands.length - 6} more
                  </span>
                ) : null}
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onGoalFilterChange(isActive ? "all" : goal.id)}
                    className="btn btn-secondary"
                    aria-pressed={isActive}
                  >
                    {isActive ? "Clear filter" : "Show commands"}
                  </button>
                  <Link href={goal.href} className="btn btn-primary">
                    {goal.cta}
                  </Link>
                </div>
                <span className="text-[11px] text-[var(--fg-3)] tab-num">
                  {goal.commands.length}/{goal.commandIds.length} commands listed
                </span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function GoalStatusPill({ goal }: { goal: CommandGoal }) {
  const parts = [
    goal.readyCount > 0 ? `${goal.readyCount} ready` : null,
    goal.partialCount > 0 ? `${goal.partialCount} builder` : null,
    goal.plannedCount > 0 ? `${goal.plannedCount} CLI` : null,
  ].filter((part): part is string => part != null);
  return (
    <span className="rounded border border-cyan-300/25 bg-cyan-300/[0.06] px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100">
      {parts.length > 0 ? parts.join(" · ") : "catalog"}
    </span>
  );
}

function CoverageDashboard({ coverage }: { coverage: CommandCoverage }) {
  return (
    <section className="glass rounded-lg p-5">
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

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
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

function WorkflowMap({ commands }: { commands: CommandCatalogEntry[] }) {
  const commandById = new Map(commands.map((command) => [command.id, command]));
  return (
    <section className="glass rounded-lg p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Workflow map</h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            The production paths share the same converter core. Keep SPH
            equivalence upstream in OpenMC, then use the converter to deliver
            corrected handoffs to DONJON.
          </p>
        </div>
        <span className="rounded border border-cyan-300/20 bg-cyan-300/[0.06] px-2 py-1 text-[11px] text-cyan-100">
          direct / OpenMC-side equivalence
        </span>
      </div>
      <div className="space-y-3">
        {COMMAND_WORKFLOW_LANES.map((lane) => (
          <WorkflowLaneRow key={lane.id} lane={lane} commandById={commandById} />
        ))}
      </div>
      <p className="mt-3 text-[12px] leading-5 text-[var(--fg-3)]">
        For SPH, OpenMC CE is the high-fidelity reference and OpenMC MG 33g is
        the macro calculation. openmc2donjon carries the resulting SPH factors;
        it does not run a DONJON feedback loop.
      </p>
    </section>
  );
}

function WorkflowLaneRow({
  lane,
  commandById,
}: {
  lane: (typeof COMMAND_WORKFLOW_LANES)[number];
  commandById: Map<string, CommandCatalogEntry>;
}) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">{lane.title}</h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            {lane.summary}
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] bg-white/[0.03] px-2 py-1 text-[11px] text-[var(--fg-2)] tab-num">
          {lane.steps.length} stages
        </span>
      </div>
      <div className="grid gap-2 lg:grid-cols-4 xl:grid-cols-5">
        {lane.steps.map((step, index) => (
          <WorkflowStepCard
            key={step.id}
            step={step}
            index={index}
            commandById={commandById}
            isLast={index === lane.steps.length - 1}
          />
        ))}
      </div>
    </article>
  );
}

function WorkflowStepCard({
  step,
  index,
  commandById,
  isLast,
}: {
  step: (typeof COMMAND_WORKFLOW_LANES)[number]["steps"][number];
  index: number;
  commandById: Map<string, CommandCatalogEntry>;
  isLast: boolean;
}) {
  const commands = step.commandIds
    .map((id) => commandById.get(id))
    .filter((command): command is CommandCatalogEntry => command != null);
  return (
    <div className="rounded-md border border-[var(--edge)] bg-white/[0.025] p-3">
      <Link href={step.href} className="block hover:text-emerald-200">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            {String(index + 1).padStart(2, "0")}
          </span>
          <span className="text-[11px] text-[var(--fg-3)]">
            {isLast ? "done" : "then"}
          </span>
        </div>
        <div className="mt-2 text-sm font-semibold tracking-tight">{step.title}</div>
        <p className="mt-1 min-h-[3rem] text-[12px] leading-5 text-[var(--fg-2)]">
          {step.body}
        </p>
      </Link>
      {commands.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {commands.map((command) => (
            <CommandChip key={`${step.id}-${command.id}`} command={command} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CommandChip({ command }: { command: CommandCatalogEntry }) {
  return (
    <Link
      href={`/commands/${command.id}`}
      title={command.title}
      className={
        "max-w-full break-all rounded border px-2 py-0.5 font-mono text-[10px] transition " +
        commandChipClass(command.status)
      }
    >
      {command.name}
    </Link>
  );
}

function CommandFilters({
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

function statusBadgeClass(status: CommandStatus) {
  if (status === "ready") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }
  if (status === "partial") {
    return "border-cyan-300/30 bg-cyan-300/10 text-cyan-200";
  }
  return "border-[var(--edge-bright)] bg-white/[0.04] text-[var(--fg-2)]";
}

function commandChipClass(status: CommandStatus) {
  if (status === "ready") {
    return "border-emerald-400/25 bg-emerald-400/[0.08] text-emerald-200 hover:border-emerald-300/50";
  }
  if (status === "partial") {
    return "border-cyan-300/25 bg-cyan-300/[0.08] text-cyan-200 hover:border-cyan-200/50";
  }
  return "border-[var(--edge)] bg-white/[0.03] text-[var(--fg-2)] hover:border-[var(--edge-bright)]";
}

function statusTextClass(status: CommandStatus) {
  if (status === "ready") return "text-emerald-300";
  if (status === "partial") return "text-cyan-300";
  return "text-[var(--fg-1)]";
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
