import type { ConvertPreflightInput, ConvertResponse } from "./api";
import {
  convertArtifactPaths,
  convertArtifactStatusText,
  type ConvertArtifactStatusMap,
} from "./convertArtifactStatus";
import { convertObjectLabel } from "./convertNextSteps";
import { formatBytes } from "./fileStatus";

export function buildConvertRunSummary(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
  statuses?: ConvertArtifactStatusMap,
): string {
  const paths = convertArtifactPaths(data);
  const lines = [
    "openmc2donjon direct conversion summary",
    "",
    `run: ${runMode(data)}`,
    `decision: ${data.ok ? "PASS" : "FAIL"}`,
    `object: ${convertObjectLabel(data.format)} (${data.format})`,
    `preflight: ${preflightStatus(data)}`,
    `production preset: ${productionStatus(data)}`,
    "",
    "source and output:",
    `  input: ${data.input_path}`,
    `  output: ${data.output_path}`,
    `  conversion summary: ${summaryStatus(data)}`,
    `  output size: ${data.output_size === null ? "n/a" : formatBytes(data.output_size)}`,
    `  bundle target: ${paths.bundle}`,
    "",
    "handoff contents:",
    `  energy groups: ${value(input?.energy_groups)}`,
    `  Legendre order: ${value(input?.legendre_order)}`,
    `  mixtures: ${value(input?.mixtures)}`,
    `  calculations: ${value(input?.calculations)}`,
    `  state points: ${value(input?.state_points)}`,
    `  energy mesh: ${energyMesh(input)}`,
    `  ADF: ${adfSummary(input)}`,
    `  SPH: ${sphSummary(input)}`,
    "",
    "artifact status:",
    `  input: ${artifactStatus(statuses, "input")}`,
    `  output: ${artifactStatus(statuses, "output")}`,
    `  bundle: ${artifactStatus(statuses, "bundle")}`,
    "",
    "CLI:",
    `  ${data.cli_command_text}`,
  ];
  return lines.join("\n");
}

function runMode(data: ConvertResponse): string {
  if (data.dry_run) return "dry run (no file written)";
  if (data.converted) return "converted (ASCII written)";
  return "stopped (no file written)";
}

function preflightStatus(data: ConvertResponse): string {
  if (!data.preflight) return "skipped";
  return data.preflight_ok ? "pass" : "fail";
}

function productionStatus(data: ConvertResponse): string {
  const requested = data.cli_command.includes("--production");
  if (!requested) return "not requested";
  const decision = data.preflight?.decision;
  return decision ? `requested (${decision})` : "requested";
}

function summaryStatus(data: ConvertResponse): string {
  if (!data.summary_path) return "n/a";
  return data.summary_written ? data.summary_path : `${data.summary_path} (not written)`;
}

function energyMesh(input: ConvertPreflightInput | null): string {
  if (!input) return "n/a";
  if (input.energy_mesh_id && input.energy_mesh_name) {
    return `${input.energy_mesh_name} (${input.energy_mesh_id})`;
  }
  return input.energy_mesh_name ?? input.energy_mesh_id ?? "unknown";
}

function adfSummary(input: ConvertPreflightInput | null): string {
  if (!input) return "n/a";
  const mixtures = input.adf_mixtures ?? 0;
  const faces = input.adf_faces ?? [];
  if (mixtures <= 0 || faces.length === 0) return "none recorded";
  return `${mixtures} mixtures, faces ${faces.join(", ")}`;
}

function sphSummary(input: ConvertPreflightInput | null): string {
  if (!input) return "n/a";
  const calculations = input.sph_calculations ?? 0;
  if (calculations <= 0) return "none recorded";
  return `${calculations} calculation${calculations === 1 ? "" : "s"}`;
}

function artifactStatus(
  statuses: ConvertArtifactStatusMap | undefined,
  id: keyof ConvertArtifactStatusMap,
): string {
  if (!statuses) return "not queried";
  return convertArtifactStatusText(statuses[id]);
}

function value(item: number | null | undefined): string {
  return item === null || item === undefined ? "n/a" : String(item);
}
