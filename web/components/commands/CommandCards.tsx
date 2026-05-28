"use client";

import Link from "next/link";
import type { CommandCatalogEntry, CommandGroup } from "@/lib/api";
import { commandWorkflowMapping } from "@/lib/commandWorkflowMapping";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import {
  AliasText,
  CliLine,
  StatusBadge,
  TagRow,
  WorkflowMappingHint,
} from "@/components/commands/CommandPrimitives";

export function FeaturedCommand({ command }: { command: CommandCatalogEntry }) {
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

export function CommandGroupSection({
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
