export type OpenmcSphWorkflowStepId =
  | "ce-flux"
  | "mg-flux"
  | "sph-sidecar"
  | "apply-sph"
  | "convert";

export interface OpenmcSphWorkflowStep {
  id: OpenmcSphWorkflowStepId;
  title: string;
  badge: string;
  body: string;
  commandId: string;
  href: string;
  cli: string;
}

const CE_EXPORT_HREF =
  "/builder?command=export-volume-flux" +
  "&tally_name=openmc_ce_volume_flux" +
  "&dataset_name=openmc_volume_flux" +
  "&output=openmc_ce_flux.h5" +
  "&summary_json=openmc_ce_flux_summary.json";

const MG_EXPORT_HREF =
  "/builder?command=export-volume-flux" +
  "&tally_name=openmc_mg_volume_flux" +
  "&dataset_name=openmc_mg_flux" +
  "&output=openmc_mg_flux.h5" +
  "&summary_json=openmc_mg_flux_summary.json";

export const OPENMC_SPH_WORKFLOW_STEPS: readonly OpenmcSphWorkflowStep[] = [
  {
    id: "ce-flux",
    title: "Export CE reference flux",
    badge: "CE",
    body:
      "Run the fine continuous-energy OpenMC reference model and export one region/group flux vector for every equivalence domain declared by the project.",
    commandId: "export-volume-flux",
    href: CE_EXPORT_HREF,
    cli:
      "openmc2donjon export-volume-flux ce_statepoint.h5 --mgxs mgxs_library.h5 " +
      "--tally-name openmc_ce_volume_flux --dataset-name openmc_volume_flux " +
      "-o openmc_ce_flux.h5",
  },
  {
    id: "mg-flux",
    title: "Export MG macro flux",
    badge: "MG",
    body:
      "Run the homogenized OpenMC MG model on the same boundary, selected energy mesh, and stable project-declared domain order, then export matching region/group flux with uncertainty.",
    commandId: "export-volume-flux",
    href: MG_EXPORT_HREF,
    cli:
      "openmc2donjon export-volume-flux mg_statepoint.h5 --mgxs mgxs_library.h5 " +
      "--tally-name openmc_mg_volume_flux --dataset-name openmc_mg_flux " +
      "-o openmc_mg_flux.h5",
  },
  {
    id: "sph-sidecar",
    title: "Compute SPH factors",
    badge: "SPH",
    body:
      "Compute the domain-wise rate-preserving CE/MG update, apply it to the homogenized MG model, re-run MG, and repeat with the previous sidecar until the raw update residual converges. No k-effective fitting is allowed.",
    commandId: "make-openmc-sph-sidecar",
    href: "/equivalence?kind=openmc-sph-sidecar&contract=physical-sph",
    cli:
      "openmc2donjon make-openmc-sph-sidecar mgxs_library.h5 -o openmc_sph.h5 " +
      "--reference-flux openmc_ce_flux.h5::openmc_volume_flux " +
      "--mg-flux openmc_mg_flux.h5::openmc_mg_flux " +
      "--table-output openmc_sph.csv --flux-normalization auto " +
      "--sph-target rate",
  },
  {
    id: "apply-sph",
    title: "Apply SPH to the Converter handoff",
    badge: "XS",
    body:
      "After convergence and independent validation, write a converter-layout MGXS copy with macroscopic cross sections divided by the physical NSPH factors. Preserve the manifest-declared domain identity and ordering.",
    commandId: "apply-sph",
    href: "/equivalence?kind=apply-sph",
    cli:
      "openmc2donjon apply-sph mgxs_library.h5 --input-format converter " +
      "--sph-source openmc_sph.h5 -o mgxs_sph_applied.h5",
  },
  {
    id: "convert",
    title: "Convert for DONJON",
    badge: "ASCII",
    body:
      "Run Converter on the completed handoff and write the checked DONJON object selected by the project. The manifest decides whether other components are required.",
    commandId: "direct-convert",
    href: "/convert?intent=openmc-sph&input=mgxs_sph_applied.h5&format=multicompo&check=1&production=1",
    cli:
      "openmc2donjon mgxs_sph_applied.h5 -o out.mcompo.txt " +
      "--format multicompo --check --production",
  },
] as const;

export function isOpenmcSphWorkflowCommand(commandId: string): boolean {
  return (
    OPENMC_SPH_WORKFLOW_STEPS.some((step) => step.commandId === commandId) ||
    commandId === "make-sph-update-table"
  );
}

export function isOpenmcSphEquivalenceKind(kind: string): boolean {
  return kind === "openmc-sph-sidecar" || kind === "apply-sph" || kind === "augment-sph";
}

export function openmcSphWorkflowSteps(
  activeCommandId: string | null,
): readonly (OpenmcSphWorkflowStep & { active: boolean })[] {
  return OPENMC_SPH_WORKFLOW_STEPS.map((step) => ({
    ...step,
    active:
      activeCommandId != null &&
      (step.commandId === activeCommandId ||
        (step.id === "sph-sidecar" && activeCommandId === "make-sph-update-table")),
  }));
}
