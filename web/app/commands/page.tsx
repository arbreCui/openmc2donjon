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
  const commandsByGroup = useMemo(() => groupCommands(data.commands), [data]);
  const featured = data.commands.find((command) => command.id === "direct-convert");

  return (
    <div className="space-y-6">
      {featured ? <FeaturedCommand command={featured} /> : null}
      {data.groups.map((group) => {
        const commands = commandsByGroup.get(group.id) ?? [];
        if (commands.length === 0) return null;
        return (
          <CommandGroupSection key={group.id} group={group} commands={commands} />
        );
      })}
    </div>
  );
}

function FeaturedCommand({ command }: { command: CommandCatalogEntry }) {
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
        </div>
        {command.web_path ? (
          <Link href={command.web_path} className="btn btn-primary shrink-0">
            Open converter
          </Link>
        ) : null}
      </div>
      <CliLine value={command.cli} />
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
      <TagRow tags={command.tags} />
      <CliLine value={command.cli} compact />
      <div className="mt-3 flex items-center justify-between gap-3">
        <AliasText aliases={command.aliases} />
        {command.web_path ? (
          <Link href={command.web_path} className="btn btn-secondary">
            Open
          </Link>
        ) : (
          <span className="text-[12px] text-[var(--fg-3)]">CLI surface</span>
        )}
      </div>
    </article>
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
