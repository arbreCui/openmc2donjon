"use client";

import Link from "next/link";
import type { CommandCatalogEntry, CommandGroup } from "@/lib/api";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { StatusBadge } from "@/components/commands/CommandPrimitives";

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
      <div className="grid gap-2">
        {commands.map((command) => (
          <CommandRow key={command.id} command={command} />
        ))}
      </div>
    </section>
  );
}

function CommandRow({ command }: { command: CommandCatalogEntry }) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-white/[0.025] px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href={`/commands/${command.id}`}
          className="font-mono text-[13px] font-semibold tracking-tight text-[var(--fg-0)] hover:text-emerald-200"
        >
          {command.name}
        </Link>
        <StatusBadge status={command.status} label={command.status_label} />
        <p className="min-w-0 flex-1 truncate text-[12px] text-[var(--fg-2)]">
          {command.summary}
        </p>
        {command.web_path ? (
          <Link href={command.web_path} className="btn btn-primary shrink-0">
            Open
          </Link>
        ) : (
          <Link
            href={`/commands/${command.id}`}
            className="btn btn-secondary shrink-0"
          >
            Details
          </Link>
        )}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="min-w-0 flex-1 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-2 py-1.5">
          <code className="whitespace-nowrap font-mono text-[12px] text-[var(--fg-1)]">
            {command.cli}
          </code>
        </div>
        <CopyCliButton value={command.cli} compact />
      </div>
    </article>
  );
}
