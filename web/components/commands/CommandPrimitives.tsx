"use client";

import Link from "next/link";
import type { CommandCatalogEntry, CommandStatus } from "@/lib/api";

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
