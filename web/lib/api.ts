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
 * ``openmc2donjon.sph-loop.v1``. M6-A only models the headline-card
 * fields; the endpoint returns the full payload and later slices
 * (convergence chart, acceptance table, audit rows) will extend this
 * interface as they consume more.
 */
export interface SphLoopAcceptanceCheck {
  name: string;
  passed: boolean;
  actual: number | string | boolean | null;
  limit: number | string | boolean | null;
  units?: string | null;
  message?: string | null;
}

export interface SphLoopAcceptance {
  enabled: boolean;
  passed: boolean;
  checks: SphLoopAcceptanceCheck[];
}

export interface SphLoopProductionAudit {
  passed: boolean;
  errors: string[];
  checks: SphLoopAcceptanceCheck[];
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
  acceptance: SphLoopAcceptance;
  production_audit: SphLoopProductionAudit;
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
