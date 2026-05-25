import type { CommandCatalogEntry } from "./api";

export type CommandGoalId =
  | "openmc-handoff"
  | "direct-convert"
  | "inspect-check"
  | "equivalence"
  | "sph-loop"
  | "package";

export interface CommandGoalDefinition {
  id: CommandGoalId;
  eyebrow: string;
  title: string;
  body: string;
  href: string;
  cta: string;
  actionHint: string;
  commandIds: readonly string[];
}

export interface CommandGoal extends CommandGoalDefinition {
  commands: CommandCatalogEntry[];
  missingCommandIds: string[];
  readyCount: number;
  partialCount: number;
  plannedCount: number;
}

export const COMMAND_GOALS: readonly CommandGoalDefinition[] = [
  {
    id: "openmc-handoff",
    eyebrow: "I need OpenMC to export",
    title: "Create the MGXS HDF5 handoff",
    body:
      "Start here when the high-fidelity OpenMC run still needs to produce the spatially resolved MGXS input.",
    href: "/openmc?workflow=two-step&production=1",
    cta: "Open OpenMC planner",
    actionHint:
      "Use the planner first if the MGXS HDF5 handoff does not exist yet.",
    commandIds: [
      "openmc2donjon-export",
      "openmc2donjon-from-openmc",
      "prepare-openmc-sph-loop",
    ],
  },
  {
    id: "direct-convert",
    eyebrow: "I already have MGXS HDF5",
    title: "Convert HDF5 to DONJON ASCII",
    body:
      "Dry-run production gates, write L_MULTICOMPO or L_MACROLIB, preview the ASCII blocks, then bundle the handoff.",
    href: "/convert?intent=direct-convert&format=multicompo&check=1&production=1",
    cta: "Open converter",
    actionHint:
      "Start with a production dry-run, then write the ASCII handoff once gates pass.",
    commandIds: ["direct-convert", "check", "inspect", "bundle"],
  },
  {
    id: "inspect-check",
    eyebrow: "I need evidence before converting",
    title: "Inspect and compare handoffs",
    body:
      "Use this when you want to look at mixtures, energy mesh, scatter, preflight issues, or semantic diffs before writing output.",
    href: "/inspect",
    cta: "Open inspector",
    actionHint:
      "Open the inspector first; use check or diff when you need CLI evidence.",
    commandIds: ["inspect", "check", "diff", "doctor"],
  },
  {
    id: "equivalence",
    eyebrow: "I need ADF / DF / SPH factors",
    title: "Build or inject sidecar factors",
    body:
      "Prepare face-flux or low-order inputs, build ADF/SPH sidecars, inject them into HDF5, then return to the converter.",
    href: "/equivalence?kind=adf-sidecar",
    cta: "Open equivalence builders",
    actionHint:
      "Build the sidecar command, run it in the CLI, then return to conversion.",
    commandIds: [
      "export-surface-flux",
      "check-face-flux",
      "make-low-order-driver",
      "make-adf-sidecar",
      "augment-adf",
      "make-sph-sidecar",
      "augment-sph",
    ],
  },
  {
    id: "sph-loop",
    eyebrow: "I need iterative SPH feedback",
    title: "Run and audit the DONJON SPH loop",
    body:
      "Freeze OpenMC as the reference, iterate DONJON flux feedback into NSPH, then review convergence and production acceptance.",
    href: "/audit",
    cta: "Open SPH audit",
    actionHint:
      "Use the audit viewer to review a completed loop; loop execution remains a CLI production workflow.",
    commandIds: [
      "prepare-openmc-sph-loop",
      "make-sph-loop-scaffold",
      "make-donjon-sph-loop-config",
      "run-sph-loop",
      "run-sph-iteration",
      "extract-donjon-volume-flux",
      "make-sph-update-table",
    ],
  },
  {
    id: "package",
    eyebrow: "I need to deliver the run",
    title: "Bundle and validate production artifacts",
    body:
      "Collect source HDF5, ASCII output, summaries, logs, and manifest checks before sharing with DONJON users.",
    href: "/builder?command=bundle",
    cta: "Open bundle builder",
    actionHint:
      "Bundle only after the HDF5, ASCII output, summaries, and logs are in place.",
    commandIds: ["bundle", "validate-bundle", "doctor"],
  },
] as const;

export function commandGoals(commands: readonly CommandCatalogEntry[]): CommandGoal[] {
  const commandById = new Map(commands.map((command) => [command.id, command]));
  return COMMAND_GOALS.map((goal) => {
    const goalCommands = goal.commandIds
      .map((id) => commandById.get(id))
      .filter((command): command is CommandCatalogEntry => command != null);
    return {
      ...goal,
      commands: goalCommands,
      missingCommandIds: goal.commandIds.filter((id) => !commandById.has(id)),
      readyCount: goalCommands.filter((command) => command.status === "ready").length,
      partialCount: goalCommands.filter((command) => command.status === "partial").length,
      plannedCount: goalCommands.filter((command) => command.status === "planned").length,
    };
  });
}

export function commandGoalsForCommand(commandId: string): CommandGoalDefinition[] {
  return COMMAND_GOALS.filter((goal) => goal.commandIds.includes(commandId));
}

export function commandGoalCommandIds(goalId: CommandGoalId): readonly string[] {
  return COMMAND_GOALS.find((goal) => goal.id === goalId)?.commandIds ?? [];
}
