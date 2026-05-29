export type OpenmcSphWorkflowStepId =
  | "ce-flux"
  | "mg-flux"
  | "sph-sidecar"
  | "apply-sph"
  | "augment"
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
      "Run the continuous-energy OpenMC reference and export region/group flux in the canonical HDF5 layout.",
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
      "Run OpenMC MG on the selected energy mesh with the same geometry/output regions and export the matching region/group flux.",
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
      "Compare CE and MG OpenMC fluxes, then write an auditable SPH table plus HDF5 sidecar.",
    commandId: "make-openmc-sph-sidecar",
    href: "/equivalence?kind=openmc-sph-sidecar",
    cli:
      "openmc2donjon make-openmc-sph-sidecar mgxs_library.h5 -o openmc_sph.h5 " +
      "--reference-flux openmc_ce_flux.h5::openmc_volume_flux " +
      "--mg-flux openmc_mg_flux.h5::openmc_mg_flux " +
      "--table-output openmc_sph.csv",
  },
  {
    id: "apply-sph",
    title: "Optional damped MG rerun",
    badge: "OPT",
    body:
      "If one-shot SPH is not enough, write an MGXS copy with XS divided by NSPH and rerun OpenMC MG. Treat this as a damping-sensitive review step, not the default production claim.",
    commandId: "apply-sph",
    href: "/builder?command=apply-sph",
    cli:
      "openmc2donjon apply-sph mg_case/mgxs_unapplied.h5 --input-format openmc-mgxs " +
      "--sph-source openmc_sph.h5 -o mg_case/mgxs.h5",
  },
  {
    id: "augment",
    title: "Inject SPH into HDF5",
    badge: "HDF5",
    body:
      "Attach the accepted SPH sidecar to the converter-facing HDF5. The current production demo uses the one-shot sidecar unless a damped rerun has been explicitly reviewed.",
    commandId: "augment-sph",
    href: "/equivalence?kind=augment-sph",
    cli:
      "openmc2donjon augment-sph mgxs_library.h5 --sph-source openmc_sph.h5 " +
      "-o mgxs_with_sph.h5",
  },
  {
    id: "convert",
    title: "Convert for DONJON",
    badge: "ASCII",
    body:
      "Run the normal converter on the corrected HDF5 and write L_MACROLIB ASCII with NSPH for DONJON consumption.",
    commandId: "direct-convert",
    href: "/convert?intent=openmc-sph&format=macrolib&check=1&production=1",
    cli:
      "openmc2donjon mgxs_with_sph.h5 -o out.macrolib.txt " +
      "--format macrolib --check --production --require-sph",
  },
] as const;

export function isOpenmcSphWorkflowCommand(commandId: string): boolean {
  return (
    OPENMC_SPH_WORKFLOW_STEPS.some((step) => step.commandId === commandId) ||
    commandId === "make-sph-update-table"
  );
}

export function isOpenmcSphEquivalenceKind(kind: string): boolean {
  return kind === "openmc-sph-sidecar" || kind === "augment-sph";
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
