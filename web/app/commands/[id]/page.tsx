"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  CommandCatalog,
  CommandCatalogEntry,
  CommandStatus,
  api,
} from "@/lib/api";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { commandWorkflowMapping } from "@/lib/commandWorkflowMapping";

type State =
  | { kind: "loading" }
  | { kind: "ok"; data: CommandCatalog }
  | { kind: "error"; message: string };

export default function CommandDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
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

  const command = useMemo(() => {
    if (state.kind !== "ok") return null;
    return state.data.commands.find((entry) => entry.id === id) ?? null;
  }, [id, state]);

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-4xl">
        <Link
          href="/commands"
          className="text-sm text-[var(--fg-2)] hover:text-[var(--fg-0)]"
        >
          Back to commands
        </Link>

        {state.kind === "loading" ? (
          <section className="glass mt-6 rounded-lg p-5 text-sm text-[var(--fg-2)]">
            Loading command details…
          </section>
        ) : null}

        {state.kind === "error" ? (
          <section className="glass mt-6 rounded-lg p-5">
            <div className="text-sm font-semibold text-rose-300">
              Command catalog failed
            </div>
            <div className="mt-1 text-sm text-[var(--fg-2)]">
              {state.message}
            </div>
          </section>
        ) : null}

        {state.kind === "ok" && !command ? (
          <section className="glass mt-6 rounded-lg p-5">
            <div className="text-sm font-semibold text-rose-300">
              Command not found
            </div>
            <div className="mt-1 font-mono text-sm text-[var(--fg-2)]">{id}</div>
          </section>
        ) : null}

        {command ? <CommandDetail command={command} /> : null}
      </div>
    </main>
  );
}

function CommandDetail({ command }: { command: CommandCatalogEntry }) {
  const mapping = commandWorkflowMapping(command);
  return (
    <div className="mt-6 space-y-4">
      <section className="glass rounded-xl p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={command.status} label={command.status_label} />
              <span className="font-mono text-[12px] text-[var(--fg-3)]">
                {command.name}
              </span>
            </div>
            <h1 className="mt-3 text-2xl font-bold tracking-tight">
              {command.title}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[var(--fg-2)]">
              {command.summary}
            </p>
          </div>
          {command.web_path ? (
            <Link href={command.web_path} className="btn btn-primary shrink-0">
              Open web workflow
            </Link>
          ) : (
            <span className="rounded-md border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              CLI surface
            </span>
          )}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <ExplainerCard title="Use When" body={command.use_when} />
        <ExplainerCard title="Produces" body={command.produces} />
        <ExplainerCard title="Next Step" body={command.next_step} />
      </section>

      <section className="glass rounded-xl p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight">
                Web workflow mapping
              </h2>
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
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--fg-2)]">
              {mapping.summary}
            </p>
          </div>
          {mapping.href ? (
            <Link href={mapping.href} className="btn btn-primary shrink-0">
              Open configured workflow
            </Link>
          ) : null}
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <MappingList title="Preselected in web" items={mapping.presets} />
          <MappingList title="You still provide" items={mapping.requiredInputs} />
        </div>
      </section>

      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">CLI form</h2>
        <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-start">
          <pre className="min-w-0 flex-1 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
            {command.cli}
          </pre>
          <CopyCliButton value={command.cli} />
        </div>
        {command.aliases.length > 0 ? (
          <p className="mt-3 text-sm text-[var(--fg-2)]">
            Alias:{" "}
            <span className="font-mono text-[var(--fg-1)]">
              {command.aliases.join(", ")}
            </span>
          </p>
        ) : null}
      </section>

      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">Tags</h2>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {command.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-md border border-[var(--edge)] bg-white/[0.03] px-2 py-0.5 text-[11px] text-[var(--fg-2)]"
            >
              {tag}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}

function MappingList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {title}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className="rounded border border-[var(--edge)] bg-white/[0.03] px-2 py-1 text-[12px] text-[var(--fg-1)]"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function ExplainerCard({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {title}
      </div>
      <p className="mt-2 text-sm leading-6 text-[var(--fg-1)]">{body}</p>
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

function statusBadgeClass(status: CommandStatus) {
  if (status === "ready") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  }
  if (status === "partial") {
    return "border-cyan-300/30 bg-cyan-300/10 text-cyan-200";
  }
  return "border-[var(--edge-bright)] bg-white/[0.04] text-[var(--fg-2)]";
}
