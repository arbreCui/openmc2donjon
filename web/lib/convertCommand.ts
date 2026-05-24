import type { ConvertFormat } from "./api";

const DEFAULT_ROOT_NAME = "CPO";

export interface ConvertCliPreviewOptions {
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
  check: boolean;
  production: boolean;
  warnUnknownEnergyMesh: boolean;
  requireKnownEnergyMesh: boolean;
  rootName: string;
  comment: string;
  burnup: string;
  hFactorDefault: string;
  mixturesText: string;
}

export interface ConvertAdvancedPayload {
  root_name?: string;
  comment: string | null;
  burnup: number | null;
  h_factor_default: number | null;
  mixtures: string[] | null;
}

export function convertAdvancedPayload(
  options: Pick<
    ConvertCliPreviewOptions,
    "rootName" | "comment" | "burnup" | "hFactorDefault" | "mixturesText"
  >,
): ConvertAdvancedPayload {
  return {
    root_name: normalizedRootName(options.rootName),
    comment: normalizedOptionalString(options.comment),
    burnup: normalizedOptionalNumber(options.burnup),
    h_factor_default: normalizedOptionalNumber(options.hFactorDefault),
    mixtures: parseMixtures(options.mixturesText),
  };
}

export function buildConvertCliPreview(options: ConvertCliPreviewOptions): string {
  const input = options.inputPath.trim() || "<input.h5>";
  const output = options.outputPath.trim() || defaultOutputName(options.format);
  const command = [
    "openmc2donjon",
    input,
    "--format",
    options.format,
    "-o",
    output,
  ];
  const rootName = normalizedRootName(options.rootName);
  if (options.format === "multicompo" && rootName !== DEFAULT_ROOT_NAME) {
    command.push("--root-name", rootName);
  }
  const comment = normalizedOptionalString(options.comment);
  if (comment !== null) command.push("--comment", comment);
  const burnup = normalizedOptionalString(options.burnup);
  if (burnup !== null) command.push("--burnup", burnup);
  const hFactorDefault = normalizedOptionalString(options.hFactorDefault);
  if (hFactorDefault !== null) {
    command.push("--h-factor-default", hFactorDefault);
  }
  for (const mixture of parseMixtures(options.mixturesText) ?? []) {
    command.push("--mixture", mixture);
  }
  if (options.check) command.push("--check");
  if (options.production) command.push("--production");
  const preflightRequested = options.check || options.production;
  if (preflightRequested && options.warnUnknownEnergyMesh) {
    command.push("--warn-unknown-energy-mesh");
  }
  if (preflightRequested && options.requireKnownEnergyMesh) {
    command.push("--require-known-energy-mesh");
  }
  return command.map(shellQuote).join(" ");
}

export function parseMixtures(value: string): string[] | null {
  const mixtures = value
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  return mixtures.length > 0 ? mixtures : null;
}

function normalizedRootName(value: string): string {
  return value.trim() || DEFAULT_ROOT_NAME;
}

function normalizedOptionalString(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function normalizedOptionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const number = Number(trimmed);
  if (!Number.isFinite(number)) {
    throw new Error("numeric convert option must be finite");
  }
  return number;
}

function defaultOutputName(format: ConvertFormat): string {
  return format === "macrolib" ? "out.macrolib.txt" : "out.mcompo.txt";
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}
