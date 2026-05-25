import type { ConvertFormat, ConvertRequest } from "./api";

export interface ConvertDemoPreset {
  id: string;
  label: string;
  description: string;
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
}

export interface ConvertDemoStep {
  id: string;
  label: string;
  title: string;
  body: string;
  href?: string;
}

export interface ConvertDemoArtifact {
  id: string;
  label: string;
  title: string;
  path: string;
  body: string;
  href?: string;
}

export const C5G7_PRODUCTION_DEMO: ConvertDemoPreset = {
  id: "c5g7-production",
  label: "C5G7 production demo",
  description:
    "Walk through a realistic direct conversion: inspect the OpenMC MGXS HDF5, dry-run production checks, write MULTICOMPO ASCII, then review the handoff artifact.",
  inputPath: "/mock/home/openmc-runs/c5g7/handoff.h5",
  outputPath: "/mock/home/openmc-runs/c5g7/out.mcompo.txt",
  format: "multicompo",
  check: true,
  production: true,
  requireKnownMesh: false,
};

export const PRODUCTION_MINICASE_DEMO: ConvertDemoPreset = {
  id: "production-minicase-live",
  label: "Production minicase",
  description:
    "Generate a tiny real OpenMC handoff with the repository smoke, then review and repeat the direct MULTICOMPO conversion from the localhost UI.",
  inputPath:
    "/private/tmp/openmc2donjon_production_minicase_smoke/openmc2donjon_run/mgxs_library.h5",
  outputPath:
    "/private/tmp/openmc2donjon_production_minicase_smoke/openmc2donjon_run/web_repeat.mcompo.txt",
  format: "multicompo",
  check: true,
  production: true,
  requireKnownMesh: false,
};

export const PRODUCTION_MINICASE_COMMAND =
  "bash scripts/run_production_minicase_smoke.sh";

export const PRODUCTION_MINICASE_RUN_ROOT =
  "/private/tmp/openmc2donjon_production_minicase_smoke";

export const PRODUCTION_MINICASE_ARTIFACTS: readonly ConvertDemoArtifact[] = [
  {
    id: "run-root",
    label: "Run root",
    title: "Managed smoke directory",
    path: PRODUCTION_MINICASE_RUN_ROOT,
    body: "The smoke recreates this directory; remove it or rerun the script when you need a fresh handoff.",
  },
  {
    id: "mgxs",
    label: "MGXS",
    title: "OpenMC HDF5 handoff",
    path: PRODUCTION_MINICASE_DEMO.inputPath,
    body: "The converter reads this file. Inspect it first to confirm mesh, mixtures, std_dev, and H-FACTOR visibility.",
    href: convertDemoInspectHref(PRODUCTION_MINICASE_DEMO),
  },
  {
    id: "ascii",
    label: "ASCII",
    title: "Web repeat output",
    path: PRODUCTION_MINICASE_DEMO.outputPath,
    body: "The web demo writes a repeat MULTICOMPO file here so the original smoke output stays comparable.",
    href: convertDemoHref(PRODUCTION_MINICASE_DEMO),
  },
  {
    id: "bundle",
    label: "Bundle",
    title: "Portable delivery record",
    path: `${parentDir(PRODUCTION_MINICASE_DEMO.outputPath)}/bundle`,
    body: "The bundle builder is prefilled from these paths after the ASCII file exists.",
    href: convertDemoBundleHref(PRODUCTION_MINICASE_DEMO),
  },
];

export function isProductionMinicasePath(path: string): boolean {
  return path.trim().startsWith(PRODUCTION_MINICASE_RUN_ROOT);
}

export function convertDemoHref(preset: ConvertDemoPreset): string {
  const params = new URLSearchParams({
    intent: "direct-convert",
    input: preset.inputPath,
    output: preset.outputPath,
    format: preset.format,
    check: preset.check ? "1" : "0",
    production: preset.production ? "1" : "0",
    require_known_mesh: preset.requireKnownMesh ? "1" : "0",
    comment: `${preset.label} web walkthrough`,
  });
  return `/convert?${params.toString()}`;
}

export function convertDemoInspectHref(preset: ConvertDemoPreset): string {
  return `/inspect?path=${encodeURIComponent(preset.inputPath)}`;
}

export function convertDemoBundleHref(preset: ConvertDemoPreset): string {
  const params = new URLSearchParams({
    command: "bundle",
    output_dir: `${parentDir(preset.outputPath)}/bundle`,
    mgxs: preset.inputPath,
  });
  if (preset.format === "macrolib") {
    params.set("macrolib", preset.outputPath);
  } else {
    params.set("mcompo", preset.outputPath);
  }
  return `/builder?${params.toString()}`;
}

export function convertDemoRequest(
  preset: ConvertDemoPreset,
  {
    dryRun,
    overwrite = false,
    comment = `${preset.label} web walkthrough`,
  }: {
    dryRun: boolean;
    overwrite?: boolean;
    comment?: string | null;
  },
): ConvertRequest {
  return {
    input_path: preset.inputPath,
    output_path: preset.outputPath,
    format: preset.format,
    dry_run: dryRun,
    overwrite,
    check: preset.check,
    production: preset.production,
    warn_unknown_energy_mesh: true,
    require_known_energy_mesh: preset.requireKnownMesh,
    root_name: "CPO",
    comment,
  };
}

function parentDir(path: string): string {
  const trimmed = path.trim();
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return ".";
  return trimmed.slice(0, index);
}

export function convertDemoWalkthrough(
  preset: ConvertDemoPreset,
): readonly ConvertDemoStep[] {
  return [
    {
      id: "inspect",
      label: "01",
      title: "Inspect input",
      body: "Confirm mixture roster, group structure, ADF/SPH coverage, and std_dev visibility.",
      href: convertDemoInspectHref(preset),
    },
    {
      id: "dry-run",
      label: "02",
      title: "Validate without writing",
      body: "Run the converter in no-write mode with production checks enabled.",
    },
    {
      id: "convert",
      label: "03",
      title: "Write ASCII",
      body: "Generate the DONJON-facing MULTICOMPO handoff at the output path.",
      href: convertDemoHref(preset),
    },
    {
      id: "review",
      label: "04",
      title: "Review and package",
      body: "Preview the LCM ASCII blocks, then bundle the input, output, and summaries.",
      href: convertDemoBundleHref(preset),
    },
  ] as const;
}
