/**
 * Typed client for the openmc2donjon FastAPI backend.
 *
 * The base URL comes from `NEXT_PUBLIC_API_BASE_URL` (see
 * `.env.local.example`) and defaults to the localhost dev address.
 */

export interface HealthResponse {
  status: "ok" | "degraded";
  mock_mode: boolean;
  version: string;
}

export interface MeshMatch {
  id: string;
  name: string | null;
  short: string | null;
  n_groups: number;
  purpose: string | null;
  description: string | null;
}

export interface MixtureSummary {
  name: string;
  state_points: number;
  fissionable: boolean | null;
  volume: number | null;
  required_present: number;
  required_total: number;
  optional_datasets: string[];
  adf_faces: string[];
  sph: boolean;
  scatter_shape: number[] | null;
  scatter_axes: string | null;
  attr_keys: string[];
}

export type HandoffAttrValue =
  | string
  | number
  | boolean
  | null
  | (string | number | boolean | null)[];

export interface HandoffRootAttr {
  name: string;
  value: HandoffAttrValue;
}

export interface TopLevelEntry {
  name: string;
  kind: "group" | "dataset";
  shape: number[] | null;
  dtype: string | null;
}

export interface HandoffInspection {
  schema: string;
  path: string;
  ok: boolean;
  energy_groups: number | null;
  legendre_order: number | null;
  energy_bounds_shape: number[] | null;
  energy_bounds: number[] | null;
  energy_min: number | null;
  energy_max: number | null;
  mesh_match: MeshMatch | null;
  /** Scalar / short-vector root HDF5 attributes (file-level metadata
   * such as ``schema_version`` / ``source`` / ``batches``). Capped at
   * the backend so a pathological file with hundreds of attributes
   * can't blow up the payload. */
  root_attrs: HandoffRootAttr[];
  /** One-level peek of HDF5 root groups + datasets. Always present;
   * lets the UI tell a user that a non-handoff file is, say, an
   * OpenMC tally export rather than a corrupted MGXS input. Also
   * capped on the backend. */
  top_level_keys: TopLevelEntry[];
  /** Total root attribute count in the file (before backend cap or
   * unsupported-value drops). */
  root_attrs_total: number;
  /** Total root-level entry count in the file (before backend cap). */
  top_level_keys_total: number;
  /** True when either ``root_attrs`` or ``top_level_keys`` was
   * shortened against its total; the UI surfaces a "showing X of Y"
   * hint when this is set. */
  peek_truncated: boolean;
  root_attr_keys: string[];
  burnup_axis: string | null;
  burnup_axis_values: number | null;
  mixture_count: number;
  calculation_count: number;
  state_points: number | null;
  fissionable_mixtures: number;
  required_complete: number;
  transport_total: number;
  h_factor: number;
  inverse_velocity: number;
  flux_weight: number;
  adf_mixtures: number;
  adf_faces: string[];
  sph_calculations: number;
  scatter_axes: string[];
  scatter_shapes: number[][];
  mixtures: MixtureSummary[];
  issues: string[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function baseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
    "http://localhost:8000"
  );
}

async function getJson<T>(
  path: string,
  query?: Record<string, string | number | undefined>,
): Promise<T> {
  let url = `${baseUrl()}${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined) continue;
      params.set(key, String(value));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(
      detail ?? `GET ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
      detail,
    );
  }
  return (await response.json()) as T;
}

export interface CrossSections {
  total: number[] | null;
  absorption: number[] | null;
  fission: number[] | null;
  nu_fission: number[] | null;
  chi: number[] | null;
}

export interface ScatterMoment {
  axes: string | null;
  shape: number[];
  moment_index: number;
  values: number[][];
}

export interface MixtureDetail {
  schema: string;
  path: string;
  mixture: string;
  energy_groups: number | null;
  legendre_order: number | null;
  volume: number | null;
  temperature: number | null;
  cross_sections: CrossSections;
  scatter: ScatterMoment | null;
}

export interface FileEntry {
  name: string;
  kind: "dir" | "file";
  size: number | null;
}

export interface FileListing {
  schema: string;
  path: string;
  parent: string | null;
  entries: FileEntry[];
}

/**
 * The ``run-sph-loop`` summary JSON, schema
 * ``openmc2donjon.sph-loop.v1``. The endpoint returns the full payload;
 * the interface grows as the audit page consumes more sections.
 */
export interface SphLoopAcceptanceCheck {
  name: string;
  passed: boolean;
  actual?: number | string | boolean | null;
  limit?: number | string | boolean | null;
  units?: string | null;
  message?: string | null;
}

export interface SphLoopAcceptance {
  enabled: boolean;
  passed: boolean;
  decision?: string | null;
  fail_on_violation?: boolean | null;
  checks: SphLoopAcceptanceCheck[];
}

export type JsonScalar = string | number | boolean | null;
export type JsonValue =
  | JsonScalar
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface SphLoopProductionAudit {
  passed: boolean;
  errors: string[];
  checks: SphLoopAcceptanceCheck[];
  artifact_counts?: Record<string, number> | null;
  flux_map?: Record<string, JsonValue> | null;
  openmc_xs_policy?: string | null;
  reference?: Record<string, JsonValue> | null;
}

export interface SphLoopResidualBin {
  mixture?: string | null;
  group?: number | null;
  residual?: number | null;
  signed_residual?: number | null;
  raw_update?: number | null;
  sph?: number | null;
  previous_sph?: number | null;
  unclipped_sph?: number | null;
  reference_flux?: number | null;
  low_order_flux?: number | null;
  clipped?: boolean | null;
}

export interface SphLoopConvergencePoint {
  iteration: number;
  sph_max_abs_change: number | null;
  sph_max_rel_change: number | null;
  flux_ratio_max_residual: number | null;
  clipped_count: number;
  clipped_fraction: number;
  worst_residual_bins: SphLoopResidualBin[];
  clipped_bins: SphLoopResidualBin[];
  converged: boolean;
}

export interface SphLoopAuditRow {
  stage: string;
  iteration: number;
  keff: number | null;
  sph_minimum: number | null;
  sph_maximum: number | null;
  sph_max_abs_change: number | null;
  sph_max_rel_change: number | null;
  flux_ratio_max_residual: number | null;
  worst_residual_mixture: string | null;
  worst_residual_group: number | null;
  worst_residual_raw_update: number | null;
  worst_residual: number | null;
  converged: boolean | null;
  solve_result: string | null;
  ascii_output: string | null;
  postprocess_output: string | null;
}

export interface SphLoopSolve {
  iteration: number;
  command: string[];
  cwd: string;
  ascii_input: string;
  result: string;
  stdout: string;
  stderr: string;
  returncode: number;
  result_bytes: number;
  flux_vector_count: number;
  flux_unknown_count: number;
  keff: number | null;
}

export interface SphLoopPostprocess {
  iteration: number;
  command: string[];
  cwd: string;
  workflow_ascii: string;
  output: string;
  sph_sidecar: string;
  stdout: string;
  stderr: string;
  returncode: number;
  output_bytes: number;
  block_count: number;
}

export interface SphLoopWorkflow {
  iteration: number;
  summary_json: string;
  donjon_volume_flux_h5: string;
  sph_sidecar: string;
  augmented_h5: string;
  ascii_output: string;
  sph_minimum: number | null;
  sph_maximum: number | null;
  flux_normalization: string | null;
  normalization_factor: number | null;
}

export interface SphLoopQuality {
  initial_flux_ratio_max_residual: number | null;
  final_flux_ratio_max_residual: number | null;
  final_to_initial_flux_residual_ratio: number | null;
  flux_residual_improved: boolean | null;
  final_clipped_count: number | null;
  final_clipped_fraction: number | null;
  maximum_clipped_count: number | null;
  maximum_clipped_fraction: number | null;
  clipping_observed: boolean | null;
  final_sph_minimum: number | null;
  final_sph_maximum: number | null;
  initial_worst_residual_bin: SphLoopResidualBin | null;
  final_worst_residual_bin: SphLoopResidualBin | null;
  final_worst_residual_bins: SphLoopResidualBin[];
  final_clipped_bins: SphLoopResidualBin[];
}

export interface SphLoopSummary {
  schema: string;
  decision: string;
  package_version: string;
  iterations: number;
  completed_iterations: number;
  converged: boolean;
  convergence_enabled: boolean;
  stop_reason: string;
  sph_change_tolerance: number | null;
  flux_ratio_tolerance: number | null;
  min_iterations?: number | null;
  // Present in summaries written by current openmc2donjon; optional so the
  // viewer can still inspect older archived summaries.
  fail_on_nonconvergence?: boolean | null;
  convergence: SphLoopConvergencePoint[];
  acceptance: SphLoopAcceptance;
  production_audit: SphLoopProductionAudit;
  quality: SphLoopQuality;
  audit_rows: SphLoopAuditRow[];
  solves: SphLoopSolve[];
  postprocesses?: SphLoopPostprocess[];
  workflows?: SphLoopWorkflow[];
}

export const api = {
  health: () => getJson<HealthResponse>("/api/health"),
  inspect: (path: string) =>
    getJson<HandoffInspection>("/api/inspect", { path }),
  inspectMixture: (path: string, mixture: string, moment: number = 0) =>
    getJson<MixtureDetail>("/api/inspect/mixture", {
      path,
      mixture,
      moment,
    }),
  listFiles: (path: string) => getJson<FileListing>("/api/files", { path }),
  audit: (path: string) => getJson<SphLoopSummary>("/api/audit", { path }),
};
