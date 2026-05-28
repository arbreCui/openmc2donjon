"use client";

import Link from "next/link";
import type { CommandCatalogEntry, CommandStatus } from "@/lib/api";
import type { CommandWorkflowMapping } from "@/lib/commandWorkflowMapping";

export function CommandChip({ command }: { command: CommandCatalogEntry }) {
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

export function WorkflowMappingHint({
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

export function StatusBadge({
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

export function TagRow({ tags }: { tags: string[] }) {
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

export function CliLine({ value, compact = false }: { value: string; compact?: boolean }) {
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

export function AliasText({ aliases }: { aliases: string[] }) {
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
