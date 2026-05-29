import type { ConvertResponse } from "./api";
import { convertObjectLabel } from "./convertNextSteps";

export type ConvertResultOverviewTileId = "write" | "target" | "next";
export type ConvertResultOverviewTone = "ready" | "pending" | "blocked";

export interface ConvertResultOverviewTile {
  id: ConvertResultOverviewTileId;
  label: string;
  value: string;
  body: string;
  tone: ConvertResultOverviewTone;
  mono?: boolean;
}

export function convertResultOverview(
  data: ConvertResponse,
): ConvertResultOverviewTile[] {
  const objectLabel = convertObjectLabel(data.format);
  const converted = data.converted && data.output_exists;
  const dryRunPassed = data.ok && data.dry_run;

  if (converted) {
    return [
      {
        id: "write",
        label: "Write status",
        value: "ASCII written",
        body: `${objectLabel} was created and confirmed on disk.`,
        tone: "ready",
      },
      {
        id: "target",
        label: "DONJON file",
        value: data.output_path,
        body: "Use this ASCII path in DONJON, or put it into a bundle.",
        tone: "ready",
        mono: true,
      },
      {
        id: "next",
        label: "Next click",
        value: "Preview / bundle",
        body: "Preview the LCM blocks, then package the handoff record.",
        tone: "ready",
      },
    ];
  }

  if (dryRunPassed) {
    return [
      {
        id: "write",
        label: "Write status",
        value: "Dry-run only",
        body: "No ASCII file was written or replaced.",
        tone: "pending",
      },
      {
        id: "target",
        label: "Target path",
        value: data.output_path,
        body: `Convert will write the ${objectLabel} ASCII handoff here.`,
        tone: "pending",
        mono: true,
      },
      {
        id: "next",
        label: "Next click",
        value: "Convert now",
        body: "The checks passed; write the DONJON-facing ASCII file next.",
        tone: "pending",
      },
    ];
  }

  return [
    {
      id: "write",
      label: "Write status",
      value: "No ASCII written",
      body: "The converter stopped before creating a handoff file.",
      tone: "blocked",
    },
    {
      id: "target",
      label: "Target path",
      value: data.output_path,
      body: "This target was not written by the failed run.",
      tone: "blocked",
      mono: true,
    },
    {
      id: "next",
      label: "Next click",
      value: "Fix checks",
      body: "Resolve the reported issue and rerun dry-run before converting.",
      tone: "blocked",
    },
  ];
}
