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
  pygan_backend?: PyGanBackendStatus;
}

export interface PyGanModuleStatus {
  name: string;
  available: boolean;
  module_file: string | null;
  error: string | null;
}

export interface PyGanBackendStatus {
  available: boolean;
  role: string;
  install_hint: string;
  modules: PyGanModuleStatus[];
  missing_modules: string[];
  schema?: string;
  mock_mode?: boolean;
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
  std_dev_datasets?: number;
  std_dev_expected_datasets?: number;
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

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(
      detail ??
        `POST ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
      detail,
    );
  }
  return (await response.json()) as T;
}

async function pyganDoctor(): Promise<PyGanBackendStatus> {
  try {
    return await getJson<PyGanBackendStatus>("/api/pygan/doctor");
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      const health = await getJson<HealthResponse>("/api/health");
      if (health.pygan_backend) {
        return {
          ...health.pygan_backend,
          schema:
            health.pygan_backend.schema ?? "openmc2donjon.pygan-doctor.v1",
          mock_mode: health.pygan_backend.mock_mode ?? health.mock_mode,
        };
      }
    }
    throw err;
  }
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

export interface FileStatus {
  schema: string;
  path: string;
  exists: boolean;
  kind: "file" | "dir" | "missing" | "other" | "unknown";
  size: number | null;
  detail: string | null;
}

export type JsonScalar = string | number | boolean | null;
export type JsonValue =
  | JsonScalar
  | JsonValue[]
  | { [key: string]: JsonValue };

export interface OpenmcSphPhysicsSummaryDecision {
  openmc_sph: string | null;
  sph_augment: string | null;
}

export interface OpenmcSphPhysicsSummaryNormalization {
  method: string | null;
  factor: number | null;
  formula: string | null;
}

export interface OpenmcSphPhysicsSummaryFluxUncertainty {
  ce_max_relative_std_dev: number;
  mg_max_relative_std_dev: number;
  ce_dataset: string | null;
  mg_dataset: string | null;
}

export interface OpenmcSphPhysicsSummarySph {
  kind: string | null;
  real: boolean;
  applied_to_xs: boolean;
  minimum: number;
  maximum: number;
  mean: number;
  max_abs_delta_from_unity: number;
  clipped_count: number;
}

export interface OpenmcSphPhysicsSummaryHandoff {
  augmented_hdf5_has_sph: boolean;
  ascii_nsp_block_count: number;
  ascii_path: string | null;
  accepted_sph_consumption_format?: "macrolib" | "multicompo" | string;
  multicompo_ascii_nsp_block_count?: number;
  multicompo_ascii_path?: string | null;
  macrolib_ascii_nsp_block_count?: number;
  macrolib_ascii_path?: string | null;
  augmented_hdf5_path: string | null;
}

export interface OpenmcSphPhysicsSummaryMixture {
  mixture: string;
  ce_flux_min: number;
  ce_flux_max: number;
  mg_flux_min: number;
  mg_flux_max: number;
  normalized_mg_over_ce_min: number;
  normalized_mg_over_ce_max: number;
  sph_min: number;
  sph_max: number;
  sph_mean: number;
  max_abs_sph_minus_1: number;
}

export interface OpenmcSphPhysicsSummaryScatter {
  format?: string;
  scatter_format?: string;
  legendre_order?: number | null;
  histogram_bins?: number | null;
}

export interface OpenmcSphPhysicsSummary {
  schema: string;
  route: string;
  requested_path?: string;
  handoff_dir: string;
  mixture_count: number;
  energy_groups: number;
  legendre_order: number;
  handoff_scatter?: OpenmcSphPhysicsSummaryScatter;
  mg_macro_scatter?: OpenmcSphPhysicsSummaryScatter;
  mixture_names: string[];
  decisions: OpenmcSphPhysicsSummaryDecision;
  normalization: OpenmcSphPhysicsSummaryNormalization;
  flux_uncertainty: OpenmcSphPhysicsSummaryFluxUncertainty;
  sph: OpenmcSphPhysicsSummarySph;
  handoff: OpenmcSphPhysicsSummaryHandoff;
  per_mixture: OpenmcSphPhysicsSummaryMixture[];
}

export type ConvertFormat = "multicompo" | "macrolib";
export type ConvertWriterBackend = "ascii" | "pygan";

export interface ConvertRequest {
  input_path: string;
  output_path?: string | null;
  format: ConvertFormat;
  writer_backend?: ConvertWriterBackend;
  dry_run: boolean;
  overwrite: boolean;
  check: boolean;
  production: boolean;
  warn_unknown_energy_mesh: boolean;
  require_known_energy_mesh: boolean;
  root_name?: string;
  comment?: string | null;
  burnup?: number | null;
  h_factor_default?: number | null;
  mixtures?: string[] | null;
}

export interface ConvertPreflightInput {
  path: string;
  ok: boolean;
  energy_groups: number | null;
  legendre_order: number | null;
  energy_mesh_id?: string | null;
  energy_mesh_name?: string | null;
  mixtures?: number | null;
  calculations?: number | null;
  state_points?: number | null;
  fissionable_mixtures?: number | null;
  adf_mixtures?: number | null;
  adf_faces?: string[];
  sph_calculations?: number | null;
  scatter_row_balance?: {
    checked?: boolean;
    max_abs?: number | null;
    max_rel?: number | null;
    worst?: string | null;
  };
  physics_checks?: {
    chi_checked?: number | null;
    chi_sum_max_abs_error?: number | null;
    nu_ratio_warning_count?: number | null;
    transport_p1_checked?: number | null;
  };
  uncertainty?: {
    checked?: boolean;
    expected_datasets?: number | null;
    datasets?: number | null;
    missing_datasets?: number | null;
    max_rel?: number | null;
  };
  issues: string[];
  warnings: string[];
}

export interface ConvertPreflightSummary {
  schema: string;
  decision: string;
  output_issue: string | null;
  inputs: ConvertPreflightInput[];
}

export interface ConvertResponse {
  schema: string;
  ok: boolean;
  dry_run: boolean;
  converted: boolean;
  format: ConvertFormat;
  writer_backend: ConvertWriterBackend;
  input_path: string;
  output_path: string;
  summary_path: string | null;
  summary_written: boolean;
  output_exists: boolean;
  output_size: number | null;
  preflight_ok: boolean;
  preflight: ConvertPreflightSummary | null;
  cli_command: string[];
  cli_command_text: string;
}

export interface TextPreview {
  schema: string;
  path: string;
  file_size: number;
  preview_bytes: number;
  max_bytes: number;
  displayed_lines: number;
  decoded_lines: number;
  max_lines: number;
  truncated: boolean;
  truncated_by: string[];
  text: string;
}

export interface BundleArtifactInspection {
  label: string;
  path: string;
  bundled_path: string | null;
  ok: boolean;
  messages: string[];
  size_bytes: number | null;
  sha256: string | null;
  summary_schema: string | null;
  summary_decision: string | null;
  acceptance_decision: string | null;
}

export interface BundleDonjonDefaults {
  format: ConvertFormat | null;
  ascii_path: string | null;
  mixture_count: number | null;
  summary_path: string | null;
  summary_schema: string | null;
  ok: boolean | null;
  converted: boolean | null;
  dry_run: boolean | null;
  preflight_ok: boolean | null;
  preflight_decision: string | null;
  production_requested: boolean | null;
}

export interface BundleInspection {
  schema: string;
  manifest_path: string;
  manifest_schema: string | null;
  output_dir: string | null;
  package_version: string | null;
  created_at_utc: string | null;
  ok: boolean;
  decision: string;
  artifact_count: number;
  messages: string[];
  artifacts: BundleArtifactInspection[];
  donjon_defaults: BundleDonjonDefaults | null;
}

export interface WriterComparisonIssue {
  path: string;
  message: string;
}

export interface WriterComparisonRequest {
  input_h5: string;
  format: ConvertFormat;
  root_name?: string;
  comment?: string | null;
  burnup?: number | null;
  h_factor_default?: number | null;
  mixtures?: string[] | null;
  rtol?: number;
  atol?: number;
  summary_json?: string | null;
  keep_dir?: string | null;
}

export interface WriterComparisonResponse {
  schema: string;
  web_schema: string;
  mock_mode: boolean;
  input_h5: string;
  format: ConvertFormat;
  ok: boolean;
  rtol: number;
  atol: number;
  compared_payloads: number;
  compared_real_payloads: number;
  max_abs_diff: number;
  max_rel_diff: number;
  issue_count: number;
  issues: WriterComparisonIssue[];
  cli_command: string[];
  cli_command_text: string;
  summary_json: string | null;
  keep_dir: string | null;
}

export type OpenmcWorkflowKind = "one-step" | "two-step";
export type OpenmcEquivalenceMode = "direct" | "adf" | "sph" | "flux-ratio-adf";

export interface OpenmcWorkflowRequest {
  workflow: OpenmcWorkflowKind;
  recipe_path: string;
  statepoint_path: string;
  load_statepoint: boolean;
  format: ConvertFormat;
  output_path: string;
  run_dir: string;
  keep_hdf5_path: string;
  check: boolean;
  production: boolean;
  strict_dry_run: boolean;
  h_factor_default: number | null;
  require_known_energy_mesh: boolean;
  warn_unknown_energy_mesh: boolean;
  equivalence: OpenmcEquivalenceMode;
  adf_source: string;
  sph_source: string;
  build_flux_ratio_adf: boolean;
}

export interface OpenmcWorkflowStep {
  id: string;
  title: string;
  summary: string;
}

export interface OpenmcWorkflowArtifact {
  label: string;
  path: string;
  kind: string;
  will_write: boolean;
}

export interface OpenmcWorkflowCheck {
  name: string;
  status: "pass" | "warn" | "fail" | "skipped";
  message: string;
}

export interface OpenmcWorkflowCommand {
  label: string;
  argv: string[];
  text: string;
}

export interface OpenmcWorkflowPlan {
  schema: string;
  ok: boolean;
  mock_mode: boolean;
  workflow: OpenmcWorkflowKind;
  workflow_label: string;
  equivalence: OpenmcEquivalenceMode;
  steps: OpenmcWorkflowStep[];
  artifacts: OpenmcWorkflowArtifact[];
  checks: OpenmcWorkflowCheck[];
  commands: OpenmcWorkflowCommand[];
  primary_command_text: string;
  next_actions: string[];
}

export type CommandStatus = "ready" | "partial" | "planned";

export interface CommandGroup {
  id: string;
  label: string;
  summary: string;
  command_count: number;
}

export interface CommandCatalogEntry {
  id: string;
  kind: "default" | "entrypoint" | "subcommand";
  name: string;
  aliases: string[];
  group: string;
  title: string;
  summary: string;
  cli_help: string;
  status: CommandStatus;
  status_label: string;
  web_path: string | null;
  cli: string;
  tags: string[];
  use_when: string;
  produces: string;
  next_step: string;
}

export interface CommandCatalog {
  schema: string;
  groups: CommandGroup[];
  commands: CommandCatalogEntry[];
  status_counts: Record<string, number>;
}

export const api = {
  health: () => getJson<HealthResponse>("/api/health"),
  pyganDoctor,
  pyganCompareWriters: (request: WriterComparisonRequest) =>
    postJson<WriterComparisonResponse>("/api/pygan/compare-writers", request),
  commands: () => getJson<CommandCatalog>("/api/commands"),
  convert: (request: ConvertRequest) =>
    postJson<ConvertResponse>("/api/convert", request),
  textPreview: (path: string, maxBytes = 32768, maxLines = 220) =>
    getJson<TextPreview>("/api/text-preview", {
      path,
      max_bytes: maxBytes,
      max_lines: maxLines,
    }),
  inspectBundle: (manifest: string) =>
    getJson<BundleInspection>("/api/bundle/inspect", { manifest }),
  openmcWorkflowPlan: (request: OpenmcWorkflowRequest) =>
    postJson<OpenmcWorkflowPlan>("/api/openmc-workflow/plan", request),
  inspect: (path: string) =>
    getJson<HandoffInspection>("/api/inspect", { path }),
  inspectMixture: (path: string, mixture: string, moment: number = 0) =>
    getJson<MixtureDetail>("/api/inspect/mixture", {
      path,
      mixture,
      moment,
    }),
  listFiles: (path: string) => getJson<FileListing>("/api/files", { path }),
  fileStatus: (path: string) =>
    getJson<FileStatus>("/api/file-status", { path }),
  openmcSphSummary: (path: string) =>
    getJson<OpenmcSphPhysicsSummary>("/api/openmc-sph-summary", { path }),
};
