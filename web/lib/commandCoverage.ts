import type { CommandCatalog, CommandCatalogEntry } from "./api";
import { commandWorkflowMapping } from "./commandWorkflowMapping";

export interface CommandSurfaceCount {
  surface: string;
  count: number;
}

export interface CommandGroupCoverage {
  id: string;
  label: string;
  total: number;
  webLinked: number;
  ready: number;
  partial: number;
  planned: number;
  coveragePercent: number;
}

export interface CommandCoverage {
  total: number;
  webLinked: number;
  ready: number;
  partial: number;
  planned: number;
  cliOnly: number;
  coveragePercent: number;
  surfaces: CommandSurfaceCount[];
  groups: CommandGroupCoverage[];
}

export function commandCoverage(data: CommandCatalog): CommandCoverage {
  const total = data.commands.length;
  const webLinked = data.commands.filter((command) => command.web_path).length;
  const ready = countStatus(data.commands, "ready");
  const partial = countStatus(data.commands, "partial");
  const planned = countStatus(data.commands, "planned");
  const cliOnly = total - webLinked;
  const surfaces = surfaceCounts(data.commands);
  const groups = data.groups.map((group) => {
    const commands = data.commands.filter((command) => command.group === group.id);
    const groupWebLinked = commands.filter((command) => command.web_path).length;
    return {
      id: group.id,
      label: group.label,
      total: commands.length,
      webLinked: groupWebLinked,
      ready: countStatus(commands, "ready"),
      partial: countStatus(commands, "partial"),
      planned: countStatus(commands, "planned"),
      coveragePercent: percent(groupWebLinked, commands.length),
    };
  });
  return {
    total,
    webLinked,
    ready,
    partial,
    planned,
    cliOnly,
    coveragePercent: percent(webLinked, total),
    surfaces,
    groups,
  };
}

function countStatus(
  commands: CommandCatalogEntry[],
  status: CommandCatalogEntry["status"],
): number {
  return commands.filter((command) => command.status === status).length;
}

function surfaceCounts(commands: CommandCatalogEntry[]): CommandSurfaceCount[] {
  const counts = new Map<string, number>();
  for (const command of commands) {
    const surface = commandWorkflowMapping(command).surface;
    counts.set(surface, (counts.get(surface) ?? 0) + 1);
  }
  return Array.from(counts, ([surface, count]) => ({ surface, count })).sort(
    (a, b) => b.count - a.count || a.surface.localeCompare(b.surface),
  );
}

function percent(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((100 * value) / total);
}
