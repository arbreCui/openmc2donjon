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
  ascii: "/mock/home/openmc-runs/openmc-sph-minicase/out.mcompo.txt",
  command: "openmc2donjon serve --mock",
};

export const LIVE_OPENMC_SPH_DEMO: OpenmcSphDemoPreset = {
  id: "live-openmc-sph",
  label: "Live OpenMC-side SPH minicase",
  description:
    "Run the repository smoke, then prefill the planner with the generated CE/MG SPH artifacts.",
  runRoot: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase",
  mgxs: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/inputs/mgxs_library.h5",
  ceStatepoint:
    "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/inputs/ce_statepoint.h5",
  mgStatepoint:
    "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/inputs/mg_statepoint.h5",
  ceFlux: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/inputs/openmc_ce_flux.h5",
  mgFlux: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/inputs/openmc_mg_flux.h5",
  sphSidecar: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/openmc_sph_sidecar.h5",
  sphTable: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/openmc_sph.csv",
  augmentedH5: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/mgxs_with_openmc_sph.h5",
  ascii: "/private/tmp/openmc2donjon_openmc_sph_sidecar_minicase/out.mcompo.txt",
  command: "bash examples/openmc_sph_sidecar_minicase/run_smoke.sh",
};

export function openmcSphPlannerPrefill(
  preset: OpenmcSphDemoPreset,
): OpenmcSphPlannerPrefill {
  return {
    workflow: "two-step",
    equivalence: "sph",
    format: "multicompo",
    production: true,
    check: true,
    runDir: preset.runRoot,
    keepHdf5Path: preset.augmentedH5,
    outputPath: preset.ascii,
    sphSource: preset.sphSidecar,
    recipePath: preset.id === "live-openmc-sph" ? "examples/openmc_sph_sidecar_minicase/run_smoke.sh" : "",
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
