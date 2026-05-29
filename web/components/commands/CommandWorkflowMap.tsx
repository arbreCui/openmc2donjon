"use client";

import Link from "next/link";
import type { CommandCatalogEntry } from "@/lib/api";
import { COMMAND_WORKFLOW_LANES } from "@/lib/commandWorkflowLanes";
import { CommandChip } from "@/components/commands/CommandPrimitives";

export function WorkflowMap({ commands }: { commands: CommandCatalogEntry[] }) {
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
        For SPH, OpenMC CE is the high-fidelity reference. OpenMC MG is the
        macro calculation on the selected energy mesh and the same
        geometry/output regions. openmc2donjon carries the resulting NSPH
        factors; it does not run a DONJON feedback loop.
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
