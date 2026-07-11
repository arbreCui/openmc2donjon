"use client";

import Link from "next/link";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { OpenmcWorkflowCommand } from "@/lib/api";
import {
  OPENMC_SPH_SIDECAR_FORM_HREF,
  type OpenmcSphPrerequisiteCommand,
} from "@/lib/openmcWorkflowWalkthrough";

export default function OpenmcCommandList({
  commands,
  primaryCommandText,
  prerequisites = [],
}: {
  commands: OpenmcWorkflowCommand[];
  primaryCommandText: string;
  prerequisites?: OpenmcSphPrerequisiteCommand[];
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

      {prerequisites.length > 0 ? (
        <div className="mt-4 rounded-lg border border-amber-300/25 bg-amber-300/[0.05] p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold tracking-tight text-amber-100">
                Build the SPH sidecar first
              </h3>
              <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
                This plan consumes an SPH sidecar that its own commands do not
                build. Run these commands before the planned sequence, or fill
                them on the sidecar form.
              </p>
            </div>
            <Link
              href={OPENMC_SPH_SIDECAR_FORM_HREF}
              className="text-[12px] font-medium text-[var(--accent-2)] hover:underline"
            >
              Open the sidecar form
            </Link>
          </div>
          <div className="mt-3 space-y-2">
            {prerequisites.map((step) => (
              <article
                key={step.id}
                className="rounded-md border border-[var(--edge)] bg-black/15 p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="rounded border border-amber-300/30 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-amber-200">
                      {step.badge}
                    </span>
                    <span className="text-sm font-medium text-[var(--fg-1)]">
                      {step.title}
                    </span>
                  </div>
                  <CopyCliButton
                    value={step.cli}
                    label="Copy"
                    ariaLabel={`Copy ${step.title} command`}
                    compact
                  />
                </div>
                <pre className="mt-2 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
                  {step.cli}
                </pre>
              </article>
            ))}
          </div>
        </div>
      ) : null}

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
    return "Exports MGXS, applies selected checks/equivalence, converts to DONJON ASCII, and packages the run as a bundle.";
  }
  if (label === "Export MGXS HDF5") {
    return "Creates the MGXS HDF5 handoff from the OpenMC recipe and statepoint.";
  }
  // The backend plan labels these steps; accept the canonical "Augment"
  // spelling plus the legacy "Inject"/"Attach" ones so the description
  // survives a backend/frontend version skew.
  if (
    label === "Augment ADF/DF" ||
    label === "Inject ADF/DF" ||
    label === "Attach ADF/DF"
  ) {
    return "Writes an augmented MGXS HDF5 with ADF/DF values attached before conversion.";
  }
  if (
    label === "Augment SPH" ||
    label === "Inject SPH" ||
    label === "Attach SPH"
  ) {
    return "Writes an augmented MGXS HDF5 with NSPH factors attached before conversion.";
  }
  if (label === "Convert HDF5 to ASCII") {
    return "Converts the selected HDF5 handoff into L_MULTICOMPO or L_MACROLIB ASCII for DONJON.";
  }
  return "Planned shell command for this workflow stage.";
}
