import type { HandoffInspection } from "./api";

/**
 * Production-readiness read of an inspected MGXS HDF5, folded into the
 * summary card's stat grid. These four facts used to render a second
 * time in a standalone "Production hints" panel; the panel is gone and
 * the pass/warn tone + one-line rationale now live on the stats (and
 * the mesh badge) themselves.
 */

export type InspectProductionTone = "pass" | "warn";

export interface InspectProductionStat {
  value: string;
  tone: InspectProductionTone;
  detail: string;
}

export type InspectProductionInput = Pick<
  HandoffInspection,
  | "mesh_match"
  | "calculation_count"
  | "mixture_count"
  | "transport_total"
  | "h_factor"
  | "fissionable_mixtures"
  | "std_dev_datasets"
  | "std_dev_expected_datasets"
>;

export interface InspectProductionStats {
  mesh: InspectProductionStat;
  transport: InspectProductionStat;
  hFactor: InspectProductionStat;
  stdDev: InspectProductionStat;
}

export function inspectProductionStats(
  data: InspectProductionInput,
): InspectProductionStats {
  const calcCount = data.calculation_count || data.mixture_count;
  return {
    mesh: {
      value: data.mesh_match
        ? `${data.mesh_match.short ?? data.mesh_match.name ?? data.mesh_match.id} (${data.mesh_match.n_groups}g)`
        : "unknown mesh",
      tone: data.mesh_match ? "pass" : "warn",
      detail: data.mesh_match
        ? "Root energy_bounds match a bundled standard mesh."
        : "Production preflight will warn unless this custom mesh is expected.",
    },
    transport: {
      value: `${data.transport_total} / ${calcCount}`,
      tone: data.transport_total === calcCount ? "pass" : "warn",
      detail:
        "Explicit transport_total supports the deterministic diffusion/SPN route.",
    },
    hFactor: {
      value: `${data.h_factor} / ${data.mixture_count}`,
      tone: data.h_factor >= data.fissionable_mixtures ? "pass" : "warn",
      detail: "Needed for power normalization in fissionable mixtures.",
    },
    stdDev: {
      value: stdDevCoverageLabel(data),
      tone:
        (data.std_dev_expected_datasets ?? 0) === 0 ||
        data.std_dev_datasets === data.std_dev_expected_datasets
          ? "pass"
          : "warn",
      detail:
        "Tally uncertainty is optional by default but important for production audits.",
    },
  };
}

export function stdDevCoverageLabel(
  data: Pick<
    InspectProductionInput,
    "std_dev_datasets" | "std_dev_expected_datasets"
  >,
): string {
  const datasets = data.std_dev_datasets;
  const expected = data.std_dev_expected_datasets;
  if (datasets == null || expected == null) return "—";
  return `${datasets} / ${expected}`;
}

/**
 * Exit to /convert with the inspected file prefilled. MACROLIB is
 * preselected when the file carries SPH factors (the accepted MACROLIB
 * NSPH route); otherwise the converter keeps its own default format.
 */
export function inspectConvertHref(
  path: string,
  sphCalculations: number,
  sphApplied = false,
): string {
  const params = new URLSearchParams();
  params.set("input", path);
  if (sphApplied) {
    params.set("intent", "openmc-sph");
    params.set("format", "multicompo");
  } else if (sphCalculations > 0) {
    params.set("format", "macrolib");
  }
  return `/convert?${params.toString()}`;
}

/** Exit to the diff builder with the inspected file as the candidate. */
export function inspectDiffHref(path: string): string {
  const params = new URLSearchParams();
  params.set("command", "diff");
  params.set("candidate_h5", path);
  return `/builder?${params.toString()}`;
}
