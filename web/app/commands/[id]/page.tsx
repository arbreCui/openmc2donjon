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
import {
  WorkflowOccurrence,
  commandWorkflowOccurrences,
} from "@/lib/commandWorkflowLanes";
import { commandGoalsForCommand } from "@/lib/commandGoals";

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

      <CommandUsePath command={command} />

      <CommandGoalContext command={command} />

      <CommandWorkflowPosition command={command} />

      {command.id === "direct-convert" ? <DirectConvertArtifactMap /> : null}

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

function CommandGoalContext({ command }: { command: CommandCatalogEntry }) {
  const goals = commandGoalsForCommand(command.id);
  if (goals.length === 0) {
    return null;
  }
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            User goals that use this command
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Commands are lower-level tools; most users should start from the
            goal card that matches their artifact or physics workflow.
          </p>
        </div>
        <Link href="/commands" className="btn btn-secondary shrink-0">
          Back to goal cards
        </Link>
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-2">
        {goals.map((goal) => (
          <article
            key={goal.id}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4"
          >
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {goal.eyebrow}
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {goal.title}
            </h3>
            <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
              {goal.body}
            </p>
            <Link href={goal.href} className="btn btn-secondary mt-4">
              {goal.cta}
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}

const DIRECT_CONVERT_ARTIFACTS = [
  {
    label: "Input",
    title: "OpenMC MGXS HDF5",
    value: "mgxs_library.h5",
    body:
      "The converter reads the exported multigroup cross sections, mixture/state metadata, optional ADF, and optional SPH factors.",
    tone: "source",
  },
  {
    label: "Gate",
    title: "Preflight decision",
    value: "--check / --production",
    body:
      "Dry run validates the HDF5 contract, energy mesh, physics consistency, uncertainty visibility, and output safety before writing.",
    tone: "gate",
  },
  {
    label: "Writes",
    title: "DONJON ASCII handoff",
    value: ".mcompo.txt / .macrolib.txt",
    body:
      "Convert writes L_MULTICOMPO for mapped domain-wise libraries or L_MACROLIB for direct one-state macrolib handoffs.",
    tone: "output",
  },
  {
    label: "Deliver",
    title: "Bundle record",
    value: "manifest.json",
    body:
      "The bundle command can collect the source HDF5, ASCII output, summaries, and logs into a manifest-backed handoff directory.",
    tone: "record",
  },
] as const;

function DirectConvertArtifactMap() {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            What gets handed to DONJON
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Direct conversion is a file handoff. The OpenMC HDF5 remains the
            source evidence; DONJON consumes the generated ASCII library. Use a
            bundle when you need a portable production record.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/convert?intent=direct-convert&format=multicompo&check=1&production=1"
            className="btn btn-secondary shrink-0"
          >
            Open converter
          </Link>
          <Link
            href="/builder?command=bundle"
            className="btn btn-secondary shrink-0"
          >
            Open bundle builder
          </Link>
        </div>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-4">
        {DIRECT_CONVERT_ARTIFACTS.map((artifact, index) => (
          <article
            key={artifact.label}
            className={
              "rounded-lg border p-3 " + artifactCardClass(artifact.tone)
            }
          >
            <div className="flex items-center justify-between gap-2">
              <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
                {artifact.label}
              </span>
              <span className="font-mono text-[11px] text-[var(--fg-3)]">
                {String(index + 1).padStart(2, "0")}
              </span>
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {artifact.title}
            </h3>
            <div className="mt-1 truncate font-mono text-[12px] text-[var(--fg-1)]">
              {artifact.value}
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
              {artifact.body}
            </p>
          </article>
        ))}
      </div>

      <div className="mt-4 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.045] px-3 py-2 text-sm text-cyan-100">
        <span className="font-semibold">Consumption rule:</span>{" "}
        <span className="text-[var(--fg-1)]">
          DONJON receives the ASCII handoff, not the OpenMC HDF5. Use
          L_MULTICOMPO when the downstream map needs mixture/domain indexing;
          use L_MACROLIB when the low-order solve expects a direct one-state
          macrolib object.
        </span>
      </div>

      <div className="mt-3 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.045] px-3 py-2 text-sm text-emerald-100">
        <span className="font-semibold">Web loop:</span>{" "}
        <span className="text-[var(--fg-1)]">
          Open converter writes or dry-runs the ASCII handoff. After a successful
          convert, the result panel opens a prefilled bundle builder so the MGXS
          source, ASCII output, and bundle directory stay linked.
        </span>
      </div>
    </section>
  );
}

function CommandWorkflowPosition({ command }: { command: CommandCatalogEntry }) {
  const occurrences = commandWorkflowOccurrences(command.id);
  if (occurrences.length === 0) {
    return (
      <section className="glass rounded-xl p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-base font-semibold tracking-tight">
              Workflow position
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--fg-2)]">
              This command is documented in the catalog but is not part of the
              main production workflow map yet. Use the command guide and CLI
              form as the source of truth.
            </p>
          </div>
          <Link href="/commands" className="btn btn-secondary shrink-0">
            Open workflow map
          </Link>
        </div>
      </section>
    );
  }
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Workflow position
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Where this command sits in the production map. Some commands appear
            in more than one lane because the same artifact can be useful in
            direct conversion, equivalence, or SPH feedback workflows.
          </p>
        </div>
        <Link href="/commands" className="btn btn-secondary shrink-0">
          Open workflow map
        </Link>
      </div>
      <div className="mt-4 grid gap-3">
        {occurrences.map((occurrence) => (
          <WorkflowOccurrenceCard
            key={`${occurrence.lane.id}-${occurrence.step.id}`}
            occurrence={occurrence}
          />
        ))}
      </div>
    </section>
  );
}

function WorkflowOccurrenceCard({
  occurrence,
}: {
  occurrence: WorkflowOccurrence;
}) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            {occurrence.lane.title}
          </div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            {String(occurrence.stepIndex + 1).padStart(2, "0")} ·{" "}
            {occurrence.step.title}
          </h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            {occurrence.step.body}
          </p>
        </div>
        <Link href={occurrence.step.href} className="btn btn-secondary shrink-0">
          Open stage
        </Link>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <NeighborStep label="Before" step={occurrence.previousStep} />
        <NeighborStep label="After" step={occurrence.nextStep} />
      </div>
    </article>
  );
}

function NeighborStep({
  label,
  step,
}: {
  label: "Before" | "After";
  step: WorkflowOccurrence["previousStep"];
}) {
  return (
    <div className="rounded-md border border-[var(--edge)] bg-black/10 p-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      {step ? (
        <>
          <Link
            href={step.href}
            className="mt-1 block text-[12px] font-semibold tracking-tight text-[var(--fg-1)] hover:text-emerald-200"
          >
            {step.title}
          </Link>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            {step.body}
          </p>
        </>
      ) : (
        <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
          This command is at the {label === "Before" ? "start" : "end"} of this
          lane.
        </p>
      )}
    </div>
  );
}

function artifactCardClass(
  tone: (typeof DIRECT_CONVERT_ARTIFACTS)[number]["tone"],
) {
  if (tone === "source") {
    return "border-cyan-300/20 bg-cyan-300/[0.05]";
  }
  if (tone === "gate") {
    return "border-amber-300/20 bg-amber-300/[0.055]";
  }
  if (tone === "output") {
    return "border-emerald-400/20 bg-emerald-400/[0.055]";
  }
  return "border-[var(--edge)] bg-white/[0.025]";
}

function CommandUsePath({ command }: { command: CommandCatalogEntry }) {
  const mapping = commandWorkflowMapping(command);
  return (
    <section className="glass rounded-xl p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            How to use this command
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            Web form when available, CLI fallback always, and the intended next
            workflow step.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {command.status_label}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <UsePathCard
          title="Web form"
          badge={mapping.available ? mapping.surface : "not yet"}
          body={
            mapping.available
              ? mapping.summary
              : "No dedicated web form is available yet. Use the CLI form and copy button below."
          }
          href={mapping.href}
          hrefLabel={mapping.available ? "Open form" : null}
          tone={mapping.available ? "pass" : "neutral"}
        />
        <UsePathCard
          title="CLI fallback"
          badge="always available"
          body="The CLI form is the authoritative execution path. Web command builders only assemble this command; they do not mutate production files."
          tone="accent"
        />
        <UsePathCard
          title="Next step"
          badge="workflow"
          body={command.next_step}
          tone="neutral"
        />
      </div>
    </section>
  );
}

function UsePathCard({
  title,
  badge,
  body,
  href,
  hrefLabel,
  tone,
}: {
  title: string;
  badge: string;
  body: string;
  href?: string | null;
  hrefLabel?: string | null;
  tone: "pass" | "accent" | "neutral";
}) {
  return (
    <article className={"rounded-lg border p-4 " + usePathCardClass(tone)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        <span className="rounded border border-[var(--edge-bright)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[var(--fg-2)]">
          {badge}
        </span>
      </div>
      <p className="mt-3 text-sm leading-6 text-[var(--fg-2)]">{body}</p>
      {href && hrefLabel ? (
        <Link href={href} className="btn btn-secondary mt-4">
          {hrefLabel}
        </Link>
      ) : null}
    </article>
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

function usePathCardClass(tone: "pass" | "accent" | "neutral") {
  if (tone === "pass") {
    return "border-emerald-400/20 bg-emerald-400/[0.06]";
  }
  if (tone === "accent") {
    return "border-cyan-300/20 bg-cyan-300/[0.06]";
  }
  return "border-[var(--edge)] bg-white/[0.02]";
}
