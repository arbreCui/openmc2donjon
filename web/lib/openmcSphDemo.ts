import type { ConvertFormat, OpenmcEquivalenceMode, OpenmcWorkflowKind } from "./api";

export interface OpenmcSphDemoPreset {
  id: "mock-openmc-sph" | "live-openmc-sph";
  label: string;
  description: string;
  runRoot: string;
  mgxs: string;
  ceStatepoint: string;
  mgStatepoint: string;
  ceFlux: string;
  mgFlux: string;
  sphSidecar: string;
  sphTable: string;
  augmentedH5: string;
  ascii: string;
  physicsSummary: string;
  command: string;
}

export interface OpenmcSphPlannerPrefill {
  workflow: OpenmcWorkflowKind;
  equivalence: OpenmcEquivalenceMode;
  format: ConvertFormat;
  production: boolean;
  check: boolean;
  runDir: string;
  keepHdf5Path: string;
  outputPath: string;
  sphSource: string;
  recipePath: string;
  statepointPath: string;
  loadStatepoint: boolean;
}

export const MOCK_OPENMC_SPH_DEMO: OpenmcSphDemoPreset = {
  id: "mock-openmc-sph",
  label: "Mock OpenMC-side SPH minicase",
  description:
    "Prefill the OpenMC planner with bundled mock paths for the CE/MG SPH route.",
  runRoot: "/mock/home/openmc-runs/openmc-sph-minicase",
  mgxs: "/mock/home/openmc-runs/openmc-sph-minicase/mgxs_library.h5",
  ceStatepoint: "/mock/home/openmc-runs/openmc-sph-minicase/ce_statepoint.h5",
  mgStatepoint: "/mock/home/openmc-runs/openmc-sph-minicase/mg_statepoint.h5",
  ceFlux: "/mock/home/openmc-runs/openmc-sph-minicase/openmc_ce_flux.h5",
  mgFlux: "/mock/home/openmc-runs/openmc-sph-minicase/openmc_mg_flux.h5",
  sphSidecar: "/mock/home/openmc-runs/openmc-sph-minicase/openmc_sph_sidecar.h5",
  sphTable: "/mock/home/openmc-runs/openmc-sph-minicase/openmc_sph.csv",
  augmentedH5: "/mock/home/openmc-runs/openmc-sph-minicase/mgxs_with_openmc_sph.h5",
  ascii: "/mock/home/openmc-runs/openmc-sph-minicase/out.macrolib.txt",
  physicsSummary: "/mock/home/openmc-runs/openmc-sph-minicase/physics_summary.json",
  command: "openmc2donjon serve --mock",
};

const LIVE_OPENMC_SPH_PRODUCTION_COMMAND = [
  "OPENMC2DONJON_COLORSET_VARIANT=two_region",
  "RUN_ROOT=/private/tmp/openmc2donjon_two_region_production_20260709",
  "BATCHES=80 INACTIVE=10 PARTICLES=20000",
  "MG_BATCHES=80 MG_INACTIVE=10 MG_PARTICLES=20000",
  "MAX_CE_FLUX_REL_STD=0.06",
  "MAX_MG_FLUX_REL_STD=0.06",
  "SPH_ITERATIONS=3",
  "bash examples/openmc_ce_mg_33g_sph_minicase/run_workflow.sh",
].join(" \\\n");

export const LIVE_OPENMC_SPH_DEMO: OpenmcSphDemoPreset = {
  id: "live-openmc-sph",
  label: "Two-region OpenMC-side SPH production minicase",
  description:
    "Run the minimal CE/MG colorset where two output regions produce two SPH factors per energy group, then prefill production-quality corrected artifacts.",
  runRoot: "/private/tmp/openmc2donjon_two_region_production_20260709",
  mgxs: "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/mgxs_library.h5",
  ceStatepoint:
    "/private/tmp/openmc2donjon_two_region_production_20260709/ce_case/statepoint.80.h5",
  mgStatepoint:
    "/private/tmp/openmc2donjon_two_region_production_20260709/mg_case_iter03/statepoint.80.h5",
  ceFlux: "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/openmc_ce_flux.h5",
  mgFlux: "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/openmc_mg_flux.h5",
  sphSidecar:
    "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/openmc_sph_sidecar.h5",
  sphTable: "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/openmc_sph.csv",
  augmentedH5:
    "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/mgxs_with_openmc_sph.h5",
  ascii:
    "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/out_with_openmc_sph.macrolib.txt",
  physicsSummary:
    "/private/tmp/openmc2donjon_two_region_production_20260709/handoff/physics_summary.json",
  command: LIVE_OPENMC_SPH_PRODUCTION_COMMAND,
};

export function openmcSphPlannerPrefill(
  preset: OpenmcSphDemoPreset,
): OpenmcSphPlannerPrefill {
  return {
    workflow: "two-step",
    equivalence: "sph",
    format: "macrolib",
    production: true,
    check: true,
    runDir: preset.runRoot,
    keepHdf5Path: preset.augmentedH5,
    outputPath: preset.ascii,
    sphSource: preset.sphSidecar,
    recipePath:
      preset.id === "live-openmc-sph"
        ? "examples/openmc_ce_mg_33g_sph_minicase/export_recipe.py"
        : "",
    statepointPath: preset.id === "mock-openmc-sph" ? preset.mgStatepoint : "",
    loadStatepoint: false,
  };
}

export function openmcSphFluxExportHref(
  preset: OpenmcSphDemoPreset,
  side: "ce" | "mg",
): string {
  const params = new URLSearchParams({
    command: "export-volume-flux",
    statepoint: side === "ce" ? preset.ceStatepoint : preset.mgStatepoint,
    output: side === "ce" ? preset.ceFlux : preset.mgFlux,
    mgxs: preset.mgxs,
    tally_name: side === "ce" ? "openmc_ce_volume_flux" : "openmc_mg_volume_flux",
    dataset_name: side === "ce" ? "openmc_volume_flux" : "openmc_mg_flux",
    summary_json:
      side === "ce"
        ? `${preset.runRoot}/openmc_ce_flux_summary.json`
        : `${preset.runRoot}/openmc_mg_flux_summary.json`,
  });
  return `/builder?${params.toString()}`;
}

export function openmcSphSidecarHref(preset: OpenmcSphDemoPreset): string {
  const params = new URLSearchParams({
    kind: "openmc-sph-sidecar",
  });
  return `/equivalence?${params.toString()}#${encodeURIComponent(preset.sphSidecar)}`;
}

export function openmcSphEvidenceHref(preset: OpenmcSphDemoPreset): string {
  const params = new URLSearchParams({
    workflow: "two-step",
    equivalence: "sph",
    format: "macrolib",
    production: "1",
    summary: preset.physicsSummary,
  });
  return `/openmc?${params.toString()}#openmc-sph-summary`;
}

export function openmcSphConvertHref(preset: OpenmcSphDemoPreset): string {
  const params = new URLSearchParams({
    intent: "openmc-sph",
    input: preset.augmentedH5,
    output: preset.ascii,
    format: "macrolib",
    writer_backend: "ascii",
    check: "1",
    production: "1",
    require_known_mesh: "0",
    comment: "OpenMC-side SPH corrected handoff",
  });
  return `/convert?${params.toString()}`;
}

export function openmcSphBundleHref(preset: OpenmcSphDemoPreset): string {
  const params = new URLSearchParams({
    command: "bundle",
    output_dir: `${parentDir(preset.ascii)}/bundle`,
    mgxs: preset.augmentedH5,
    macrolib: preset.ascii,
  });
  return `/builder?${params.toString()}`;
}

function parentDir(path: string): string {
  const index = path.lastIndexOf("/");
  if (index <= 0) return ".";
  return path.slice(0, index);
}
