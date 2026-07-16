export type ColorsetId =
  | "int_ext"
  | "ext_int"
  | "csd_int"
  | "dsdf_int"
  | "pnl_ext"
  | "refl_ext";

export interface ColorsetDefinition {
  id: ColorsetId;
  target: "INT" | "EXT" | "CSD" | "DSDF" | "PNL" | "REFL";
  neighbors: "INT" | "EXT";
  role: string;
  required: boolean;
  priorEvidence: string;
  outputName: string;
}

export const COLORSET_DEFINITIONS: readonly ColorsetDefinition[] = [
  {
    id: "int_ext",
    target: "INT",
    neighbors: "EXT",
    role: "Inner fuel component library",
    required: true,
    priorEvidence: "Fine-model reference comparison exists; strict OpenMC rate-SPH rerun is pending.",
    outputName: "irena30_int.mcompo.txt",
  },
  {
    id: "ext_int",
    target: "EXT",
    neighbors: "INT",
    role: "Outer fuel component library",
    required: true,
    priorEvidence: "Fine-model reference comparison exists; strict OpenMC rate-SPH rerun is pending.",
    outputName: "irena30_ext.mcompo.txt",
  },
  {
    id: "csd_int",
    target: "CSD",
    neighbors: "INT",
    role: "Control-assembly component library",
    required: true,
    priorEvidence: "Recorded rate-SPH recovered the CE/MG defect from -423 to -78 pcm; convergence must be completed without numerical exemptions.",
    outputName: "irena30_csd.mcompo.txt",
  },
  {
    id: "dsdf_int",
    target: "DSDF",
    neighbors: "INT",
    role: "Follower component library",
    required: true,
    priorEvidence: "Fine-model reference comparison exists; strict OpenMC rate-SPH rerun is pending.",
    outputName: "irena30_dsdf.mcompo.txt",
  },
  {
    id: "pnl_ext",
    target: "PNL",
    neighbors: "EXT",
    role: "Lateral protection component library",
    required: true,
    priorEvidence: "A prior core-transfer diagnostic exists; its archived factors do not meet the new strict provenance gate.",
    outputName: "irena30_pnl.mcompo.txt",
  },
  {
    id: "refl_ext",
    target: "REFL",
    neighbors: "EXT",
    role: "Optional recovered reflector library",
    required: false,
    priorEvidence: "Optional reference case; include only when the selected core layout uses a distinct REFL component.",
    outputName: "irena30_refl.mcompo.txt",
  },
] as const;

export const REQUIRED_COLORSET_COUNT = COLORSET_DEFINITIONS.filter(
  (item) => item.required,
).length;

export const WITHDRAWN_COLORSET_CONTRACT = "irena30-colorset-sph";
export const WITHDRAWN_COLORSET_DIAGNOSTIC = "withdrawn-five-colorset";

/**
 * The five-colorset IRENA route is retained only so archived inputs and
 * evidence can still be inspected.  A bare `colorset` query is deliberately
 * treated the same way as its old contracts: it must never opt a user into a
 * production or physical-SPH action implicitly.
 */
export function isWithdrawnColorsetWorkflow(
  colorset: string | null | undefined,
  contract: string | null | undefined,
  diagnostic?: string | null,
): boolean {
  return (
    colorset != null ||
    contract === WITHDRAWN_COLORSET_CONTRACT ||
    contract === "physical-colorset-sph" ||
    diagnostic === WITHDRAWN_COLORSET_DIAGNOSTIC
  );
}

export function colorsetDefinition(value: string | null | undefined): ColorsetDefinition {
  return (
    COLORSET_DEFINITIONS.find((item) => item.id === value) ??
    COLORSET_DEFINITIONS[0]
  );
}

export function colorsetOpenmcHref(id: ColorsetId, projectRoot?: string): string {
  const base = (
    "/openmc?workflow=two-step&equivalence=direct&format=multicompo" +
    `&production=0&colorset=${encodeURIComponent(id)}` +
    `&contract=${WITHDRAWN_COLORSET_CONTRACT}` +
    `&diagnostic=${WITHDRAWN_COLORSET_DIAGNOSTIC}`
  );
  return appendProject(base, projectRoot);
}

export function colorsetSphHref(id: ColorsetId, projectRoot?: string): string {
  const base = (
    "/equivalence?kind=openmc-sph-sidecar" +
    `&colorset=${encodeURIComponent(id)}` +
    `&contract=${WITHDRAWN_COLORSET_CONTRACT}` +
    `&diagnostic=${WITHDRAWN_COLORSET_DIAGNOSTIC}`
  );
  return appendProject(base, projectRoot);
}

export function colorsetConvertHref(
  id: ColorsetId,
  inputPath?: string,
  projectRoot?: string,
): string {
  const params = new URLSearchParams({
    intent: "direct-convert",
    format: "multicompo",
    check: "1",
    production: "0",
    colorset: id,
    component: id,
    contract: WITHDRAWN_COLORSET_CONTRACT,
    diagnostic: WITHDRAWN_COLORSET_DIAGNOSTIC,
  });
  if (inputPath?.trim()) params.set("input", inputPath.trim());
  if (projectRoot?.trim()) params.set("project", projectRoot.trim().replace(/\/+$/, ""));
  return `/convert?${params.toString()}#convert-component`;
}

function appendProject(href: string, projectRoot?: string): string {
  const root = projectRoot?.trim().replace(/\/+$/, "") ?? "";
  if (!root) return href;
  return `${href}&project=${encodeURIComponent(root)}`;
}
