import type { ConvertFormat } from "./api";

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

export const C5G7_PRODUCTION_DEMO: ConvertDemoPreset = {
  id: "c5g7-production",
  label: "C5G7 production demo",
  description:
    "Walk through a realistic direct conversion: inspect the OpenMC MGXS HDF5, dry-run production gates, write MULTICOMPO ASCII, then review the handoff artifact.",
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

export function isProductionMinicasePath(path: string): boolean {
  return path.trim().startsWith(PRODUCTION_MINICASE_RUN_ROOT);
}

export function convertDemoHref(preset: ConvertDemoPreset): string {
  const params = new URLSearchParams({
    intent: "direct-convert",
    format: preset.format,
    check: preset.check ? "1" : "0",
    production: preset.production ? "1" : "0",
  });
  return `/convert?${params.toString()}`;
}

export function convertDemoInspectHref(preset: ConvertDemoPreset): string {
  return `/inspect?path=${encodeURIComponent(preset.inputPath)}`;
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
      title: "Dry-run gates",
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
      href: "/builder?command=bundle",
    },
  ] as const;
}
