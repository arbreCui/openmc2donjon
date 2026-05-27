export type EquivalenceKind =
  | "adf-sidecar"
  | "augment-adf"
  | "openmc-sph-sidecar"
  | "sph-sidecar"
  | "augment-sph";

export type AdfSidecarMode = "unity" | "flux-ratio";
export type SphSidecarMode = "unity" | "macrolib" | "table";
export type BooleanChoice = "" | "true" | "false";

export interface EquivalenceCommandOptions {
  kind: EquivalenceKind;
  inputH5: string;
  outputPath: string;
  force: boolean;
  summaryJson: string;
  adfMode: AdfSidecarMode;
  adfValue: string;
  faces: string;
  surfaceFlux: string;
  homogeneousFaceFlux: string;
  invalidFill: string;
  clipMin: string;
  clipMax: string;
  adfSource: string;
  sphMode: SphSidecarMode;
  sphValue: string;
  macrolib: string;
  table: string;
  referenceFlux: string;
  mgFlux: string;
  tableOutput: string;
  previousSph: string;
  damping: string;
  fluxNormalization: "none" | "total" | "power" | "auto";
  sphSource: string;
  sphApplied: BooleanChoice;
}

export interface EquivalenceKindInfo {
  kind: EquivalenceKind;
  commandId: string;
  label: string;
  title: string;
  summary: string;
  outputPlaceholder: string;
}

export const EQUIVALENCE_KINDS: readonly EquivalenceKindInfo[] = [
  {
    kind: "adf-sidecar",
    commandId: "make-adf-sidecar",
    label: "ADF sidecar",
    title: "Build ADF/DF sidecar",
    summary:
      "Generate an ADF/DF HDF5 sidecar from an MGXS handoff. Unity mode is for plumbing; flux-ratio mode needs heterogeneous and homogeneous face flux.",
    outputPlaceholder: "adf_sidecar.h5",
  },
  {
    kind: "augment-adf",
    commandId: "augment-adf",
    label: "Inject ADF",
    title: "Inject ADF/DF into MGXS",
    summary:
      "Attach computed discontinuity factors to the MGXS HDF5 before conversion. The converter then carries the ADF blocks into DONJON ASCII.",
    outputPlaceholder: "mgxs_with_adf.h5",
  },
  {
    kind: "openmc-sph-sidecar",
    commandId: "make-openmc-sph-sidecar",
    label: "OpenMC SPH",
    title: "Build OpenMC-side SPH sidecar",
    summary:
      "Compare OpenMC CE reference flux and OpenMC MG macro flux from the same geometry, then write an auditable SPH table plus HDF5 sidecar.",
    outputPlaceholder: "sph_sidecar.h5",
  },
  {
    kind: "sph-sidecar",
    commandId: "make-sph-sidecar",
    label: "SPH sidecar",
    title: "Build SPH sidecar",
    summary:
      "Create SPH factors as an HDF5 sidecar. Unity mode is for plumbing; table/macrolib modes import factors from an external source.",
    outputPlaceholder: "sph_sidecar.h5",
  },
  {
    kind: "augment-sph",
    commandId: "augment-sph",
    label: "Inject SPH",
    title: "Inject SPH into MGXS",
    summary:
      "Attach SPH factors to the MGXS HDF5 before conversion. This records NSPH equivalence data for the DONJON handoff.",
    outputPlaceholder: "mgxs_with_sph.h5",
  },
] as const;

export function parseEquivalenceKind(value: string | null): EquivalenceKind {
  if (
    value === "adf-sidecar" ||
    value === "augment-adf" ||
    value === "openmc-sph-sidecar" ||
    value === "sph-sidecar" ||
    value === "augment-sph"
  ) {
    return value;
  }
  return "adf-sidecar";
}

export function equivalenceKindInfo(kind: EquivalenceKind): EquivalenceKindInfo {
  return EQUIVALENCE_KINDS.find((item) => item.kind === kind) ?? EQUIVALENCE_KINDS[0];
}

export function defaultEquivalenceOptions(kind: EquivalenceKind): EquivalenceCommandOptions {
  return {
    kind,
    inputH5: "",
    outputPath: equivalenceKindInfo(kind).outputPlaceholder,
    force: false,
    summaryJson: "",
    adfMode: "unity",
    adfValue: "1.0",
    faces: "FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX",
    surfaceFlux: "",
    homogeneousFaceFlux: "",
    invalidFill: "",
    clipMin: "",
    clipMax: "",
    adfSource: "",
    sphMode: "unity",
    sphValue: "1.0",
    macrolib: "",
    table: "",
    referenceFlux: "",
    mgFlux: "",
    tableOutput: "",
    previousSph: "",
    damping: "1.0",
    fluxNormalization: "none",
    sphSource: "",
    sphApplied: "",
  };
}

export function buildEquivalenceCli(options: EquivalenceCommandOptions): string {
  if (options.kind === "adf-sidecar") return buildAdfSidecarCli(options);
  if (options.kind === "augment-adf") return buildAugmentAdfCli(options);
  if (options.kind === "openmc-sph-sidecar") return buildOpenmcSphSidecarCli(options);
  if (options.kind === "sph-sidecar") return buildSphSidecarCli(options);
  return buildAugmentSphCli(options);
}

function buildAdfSidecarCli(options: EquivalenceCommandOptions): string {
  const command = [
    "openmc2donjon",
    "make-adf-sidecar",
    pathOrPlaceholder(options.inputH5, "<mgxs_library.h5>"),
    "-o",
    pathOrPlaceholder(options.outputPath, "adf_sidecar.h5"),
    "--mode",
    options.adfMode,
  ];
  pushOptional(command, "--faces", options.faces);
  if (options.adfMode === "unity") {
    pushOptional(command, "--value", options.adfValue);
  } else {
    pushOptional(command, "--surface-flux", options.surfaceFlux);
    pushOptional(command, "--homogeneous-face-flux", options.homogeneousFaceFlux);
    pushOptional(command, "--invalid-fill", options.invalidFill);
    pushOptional(command, "--clip-min", options.clipMin);
    pushOptional(command, "--clip-max", options.clipMax);
  }
  pushCommon(command, options);
  return command.map(shellQuote).join(" ");
}

function buildAugmentAdfCli(options: EquivalenceCommandOptions): string {
  const command = [
    "openmc2donjon",
    "augment-adf",
    pathOrPlaceholder(options.inputH5, "<mgxs_library.h5>"),
    "--adf-source",
    pathOrPlaceholder(options.adfSource, "<adf_sidecar.h5>"),
    "-o",
    pathOrPlaceholder(options.outputPath, "mgxs_with_adf.h5"),
  ];
  pushOptional(command, "--faces", options.faces);
  pushCommon(command, options);
  return command.map(shellQuote).join(" ");
}

function buildSphSidecarCli(options: EquivalenceCommandOptions): string {
  const command = [
    "openmc2donjon",
    "make-sph-sidecar",
    pathOrPlaceholder(options.inputH5, "<mgxs_library.h5>"),
    "-o",
    pathOrPlaceholder(options.outputPath, "sph_sidecar.h5"),
    "--mode",
    options.sphMode,
  ];
  if (options.sphMode === "unity") {
    pushOptional(command, "--value", options.sphValue);
  } else if (options.sphMode === "macrolib") {
    pushOptional(command, "--macrolib", options.macrolib);
  } else {
    pushOptional(command, "--table", options.table);
  }
  pushCommon(command, options);
  return command.map(shellQuote).join(" ");
}

function buildOpenmcSphSidecarCli(options: EquivalenceCommandOptions): string {
  const command = [
    "openmc2donjon",
    "make-openmc-sph-sidecar",
    pathOrPlaceholder(options.inputH5, "<mgxs_library.h5>"),
    "-o",
    pathOrPlaceholder(options.outputPath, "sph_sidecar.h5"),
    "--reference-flux",
    pathOrPlaceholder(options.referenceFlux, "<openmc_ce_flux.h5::openmc_volume_flux>"),
    "--mg-flux",
    pathOrPlaceholder(options.mgFlux, "<openmc_mg_flux.h5::openmc_mg_flux>"),
  ];
  pushOptional(command, "--table-output", options.tableOutput);
  pushOptional(command, "--previous-sph", options.previousSph);
  pushOptional(command, "--damping", options.damping);
  pushOptional(command, "--flux-normalization", options.fluxNormalization);
  pushOptional(command, "--clip-min", options.clipMin);
  pushOptional(command, "--clip-max", options.clipMax);
  pushCommon(command, options);
  return command.map(shellQuote).join(" ");
}

function buildAugmentSphCli(options: EquivalenceCommandOptions): string {
  const command = [
    "openmc2donjon",
    "augment-sph",
    pathOrPlaceholder(options.inputH5, "<mgxs_library.h5>"),
    "--sph-source",
    pathOrPlaceholder(options.sphSource, "<sph_sidecar.h5>"),
    "-o",
    pathOrPlaceholder(options.outputPath, "mgxs_with_sph.h5"),
  ];
  pushOptional(command, "--sph-applied", options.sphApplied);
  pushCommon(command, options);
  return command.map(shellQuote).join(" ");
}

function pushCommon(command: string[], options: EquivalenceCommandOptions) {
  pushOptional(command, "--summary-json", options.summaryJson);
  if (options.force) command.push("--force");
}

function pushOptional(command: string[], flag: string, value: string) {
  const trimmed = value.trim();
  if (trimmed !== "") command.push(flag, trimmed);
}

function pathOrPlaceholder(value: string, placeholder: string): string {
  return value.trim() || placeholder;
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_@%+=:,./<>-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}
