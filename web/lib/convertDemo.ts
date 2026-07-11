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

export interface ConvertDemoClickStep {
  id: "fill" | "dry-run" | "convert";
  label: string;
  title: string;
  body: string;
}

export interface ConvertDemoArtifact {
  id: string;
  label: string;
  title: string;
  role: ConvertDemoArtifactRole;
  path: string;
  body: string;
  href?: string;
}

export type ConvertDemoArtifactRole = "starter" | "downstream";

export type ProductionMinicaseAvailabilityTone =
  | "loading"
  | "ready"
  | "missing"
  | "error";

export interface ProductionMinicaseArtifactCounts {
  loadingCount: number;
  errorCount: number;
  starterMissingCount: number;
  downstreamMissingCount: number;
}

export interface ProductionMinicaseAvailability {
  tone: ProductionMinicaseAvailabilityTone;
  title: string;
  body: string;
  statusMessage: string;
  canUsePaths: boolean;
}

export const C5G7_PRODUCTION_DEMO: ConvertDemoPreset = {
  id: "c5g7-production",
  label: "C5G7 production demo",
  description:
    "Walk through a realistic direct conversion: inspect the OpenMC MGXS HDF5, run a production dry run, write MULTICOMPO ASCII, then review the ASCII output.",
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
    role: "starter",
    path: PRODUCTION_MINICASE_RUN_ROOT,
    body: "The smoke recreates this directory; remove it or rerun the script when you need a fresh handoff.",
  },
  {
    id: "mgxs",
    label: "MGXS",
    title: "OpenMC HDF5 handoff",
    role: "starter",
    path: PRODUCTION_MINICASE_DEMO.inputPath,
    body: "The converter reads this file. Inspect it first to confirm mesh, mixtures, std_dev, and H-FACTOR visibility.",
    href: convertDemoInspectHref(PRODUCTION_MINICASE_DEMO),
  },
  {
    id: "ascii",
    label: "ASCII",
    title: "Web repeat output",
    role: "downstream",
    path: PRODUCTION_MINICASE_DEMO.outputPath,
    body: "The web demo writes a repeat MULTICOMPO file here so the original smoke output stays comparable.",
    href: convertDemoHref(PRODUCTION_MINICASE_DEMO),
  },
  {
    id: "bundle",
    label: "Bundle",
    title: "Manifest-backed bundle",
    role: "downstream",
    path: `${parentDir(PRODUCTION_MINICASE_DEMO.outputPath)}/bundle`,
    body: "The bundle builder is prefilled from these paths after the ASCII file exists.",
    href: convertDemoBundleHref(PRODUCTION_MINICASE_DEMO),
  },
];

export function isProductionMinicasePath(path: string): boolean {
  return path.trim().startsWith(PRODUCTION_MINICASE_RUN_ROOT);
}

export function productionMinicaseAvailability({
  loadingCount,
  errorCount,
  starterMissingCount,
  downstreamMissingCount,
}: ProductionMinicaseArtifactCounts): ProductionMinicaseAvailability {
  if (loadingCount > 0) {
    return {
      tone: "loading",
      title: "Checking live minicase files",
      body:
        "The web UI is checking whether the local smoke run has already " +
        "generated the MGXS handoff.",
      statusMessage: "Checking starter and downstream artifact status on this machine.",
      canUsePaths: false,
    };
  }
  if (errorCount > 0) {
    return {
      tone: "error",
      title: "Status check failed",
      body:
        "At least one localhost filesystem status check failed. Refresh the " +
        "status or rerun the smoke before using these paths.",
      statusMessage: `${errorCount} status check${errorCount === 1 ? "" : "s"} failed.`,
      canUsePaths: false,
    };
  }
  if (starterMissingCount > 0) {
    return {
      tone: "missing",
      title: "Generate minicase first",
      body:
        "The smoke-generated run directory or MGXS HDF5 is missing. Run the " +
        "smoke command from the repository root, then refresh this card.",
      statusMessage: `${starterMissingCount} starter artifact${
        starterMissingCount === 1 ? "" : "s"
      } missing — run the smoke command before using the live paths.`,
      canUsePaths: false,
    };
  }
  if (downstreamMissingCount > 0) {
    return {
      tone: "ready",
      title: "Ready for web repeat",
      body:
        "The real MGXS handoff is present. Dry run and convert from this page; " +
        "ASCII preview and bundle artifacts appear after those web actions.",
      statusMessage: `${downstreamMissingCount} downstream artifact${
        downstreamMissingCount === 1 ? "" : "s"
      } not written yet — this is expected before convert and bundle.`,
      canUsePaths: true,
    };
  }
  return {
    tone: "ready",
    title: "Full minicase artifacts ready",
    body:
      "The smoke handoff, repeat ASCII output, and bundle directory are all " +
      "visible on this machine.",
    statusMessage: "Starter and downstream artifacts are ready for the current localhost filesystem.",
    canUsePaths: true,
  };
}

export function convertDemoHref(preset: ConvertDemoPreset): string {
  const params = new URLSearchParams({
    intent: "direct-convert",
    input: preset.inputPath,
    output: preset.outputPath,
    format: preset.format,
    require_known_mesh: preset.requireKnownMesh ? "1" : "0",
    comment: `${preset.label} web walkthrough`,
  });
  // check/production now default to true on the form; only carry the params
  // when a preset needs to downgrade them.
  if (!preset.check) params.set("check", "0");
  if (!preset.production) params.set("production", "0");
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

export function convertDemoPreviewHref(preset: ConvertDemoPreset): string {
  void preset;
  return "#ascii-output-preview";
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
    writer_backend: "ascii",
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

export function convertDemoClickSteps(): readonly ConvertDemoClickStep[] {
  return [
    {
      id: "fill",
      label: "01",
      title: "Fill demo",
      body:
        "Load the C5G7 HDF5 path, MULTICOMPO output path, and production checks.",
    },
    {
      id: "dry-run",
      label: "02",
      title: "Dry run",
      body:
        "Validate the handoff without writing or replacing the ASCII output.",
    },
    {
      id: "convert",
      label: "03",
      title: "Convert",
      body:
        "Write the mock MULTICOMPO file, then preview and bundle it below.",
    },
  ] as const;
}
