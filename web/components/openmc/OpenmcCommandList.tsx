"use client";

import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { OpenmcWorkflowCommand } from "@/lib/api";

export default function OpenmcCommandList({
  commands,
  primaryCommandText,
}: {
  commands: OpenmcWorkflowCommand[];
  primaryCommandText: string;
}) {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">CLI commands</h2>
          <p className="mt-1 text-sm text-[var(--fg-2)]">
            Copy these commands into a terminal in order. Each command maps to one
            production handoff stage.
          </p>
        </div>
        {primaryCommandText ? (
          <CopyCliButton
            value={primaryCommandText}
            label="Copy primary"
            ariaLabel="Copy primary OpenMC workflow command"
          />
        ) : null}
      </div>

      <div className="mt-4 space-y-3">
        {commands.map((command, index) => (
          <article
            key={`${command.label}-${index}`}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.02] p-3"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                  {command.label}
                </div>
                <p className="mt-1 text-sm text-[var(--fg-2)]">
                  {commandDescription(command.label)}
                </p>
              </div>
              <CopyCliButton
                value={command.text}
                label="Copy"
                ariaLabel={`Copy ${command.label} command`}
                compact
              />
            </div>
            <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
              {command.text}
            </pre>
          </article>
        ))}
      </div>
    </section>
  );
}

function commandDescription(label: string): string {
  if (label === "One-step OpenMC handoff") {
    return "Exports MGXS, applies selected checks/equivalence, converts to DONJON ASCII, and writes the managed handoff bundle.";
  }
  if (label === "Export MGXS HDF5") {
    return "Creates the converter-facing HDF5 handoff from the OpenMC recipe and statepoint.";
  }
  if (label === "Inject ADF/DF") {
    return "Writes an augmented HDF5 handoff with ADF/DF values attached before conversion.";
  }
  if (label === "Inject SPH") {
    return "Writes an augmented HDF5 handoff with NSPH factors attached before conversion.";
  }
  if (label === "Convert HDF5 to ASCII") {
    return "Converts the selected HDF5 handoff into L_MULTICOMPO or L_MACROLIB ASCII for DONJON.";
  }
  return "Planned shell command for this workflow stage.";
}
