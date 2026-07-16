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

export interface OpenmcProvenanceArtifact {
  role: string;
  path: string;
  required: boolean;
  present: boolean;
  size_bytes: number | null;
  sha256: string | null;
}

export interface OpenmcProvenance {
  schema: string | null;
  status: "complete" | "incomplete" | "legacy";
  issues: string[];
  missing: string[];
  digest_sha256: string | null;
  integrity?: { ok: boolean; issues: string[] };
  capabilities: {
    reference_bound: boolean;
    export_replayable: boolean;
    transport_reproducible: boolean;
  };
  fingerprints: {
    model_sha256: string | null;
    transport_sha256: string | null;
  };
  producer: {
    name: string | null;
    version: string | null;
    python_version: string | null;
    platform: string | null;
  };
  openmc: {
    version: string | null;
    git_sha1: string | null;
    statepoint_format_version: string | null;
  };
  statepoint: {
    filetype: string | null;
    is_openmc_statepoint: boolean;
    date_and_time: string | null;
  };
  source_mode: string;
  statepoint_loaded: boolean | null;
  evidence: {
    simulation_sources: Record<string, Record<string, unknown>>;
    openmc_version_sources: Record<string, unknown>;
  };
  input_closure: {
    attested_complete: boolean;
    method: string | null;
  };
  handoff: {
    algorithm: string;
    payload_sha256: string | null;
  };
  artifacts: OpenmcProvenanceArtifact[];
  simulation: {
    run_mode: string | null;
    particles: number | null;
    batches: number | null;
    inactive: number | null;
    generations_per_batch: number | null;
    seed: number | null;
    stride: number | null;
    threads: number | null;
    mpi_ranks: number | null;
  };
  temperature: Record<string, string | number | object> | null;
  nuclear_data: {
    cross_sections: OpenmcProvenanceArtifact | null;
    cross_sections_source: string | null;
    selection: string;
    library_count: number;
    total_size_bytes: number;
    libraries_manifest_sha256: string | null;
    libraries: OpenmcProvenanceArtifact[];
  };
  user_metadata: Record<string, unknown>;
}

export interface HandoffInspection {
  schema: string;
  path: string;
  /** True when the backend returned the bundled demonstration fixture
   * instead of reading ``path``.  Optional for older recorded payloads. */
  mock_mode?: boolean;
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
  openmc_provenance: OpenmcProvenance | null;
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
  sph_applied: boolean;
  sph_applied_source: string | null;
  sph_apply_operator: string | null;
  sph_kind: string | null;
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
  // `||` (not `??`) so a *blank* NEXT_PUBLIC_API_BASE_URL in
  // web/.env.local still falls back to the default instead of issuing
  // every request against the Next server, which has no /api routes.
  return (
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
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
  total_entries?: number;
  entry_limit?: number;
  truncated?: boolean;
}

export interface FileStatus {
  schema: string;
  path: string;
  exists: boolean;
  kind: "file" | "dir" | "missing" | "other" | "unknown";
  size: number | null;
  detail: string | null;
}

export type ProjectArtifactState =
  | "missing"
  | "not-required"
  | "present"
  | "accepted"
  | "rejected";

export interface ProjectArtifactStatus {
  state: ProjectArtifactState;
  issues: string[];
}

export interface ProjectEvidencePath {
  id: string;
  label: string;
  path: string;
}

export interface ProjectComponentPaths {
  directory: string;
  input: string;
  output: string;
  /** Production Converter receipt for the converted object. */
  receipt: string;
  /** Native-SPH physics summary; never aliases the Converter receipt. */
  physics_summary: string;
  evidence: ProjectEvidencePath[];
  // Compatibility fields exposed for the IRENA guided pages.
  sph_applied: string;
  cpo: string;
  cpo_receipt: string;
}

export interface ProjectNativeSphDeclaration {
  /** Absolute project-confined path resolved from the manifest declaration. */
  deck_path: string;
  /** Absolute project-confined directory used to resolve deck FILE clauses. */
  working_directory: string;
  /** Optional compatibility map; named validation evidence remains in paths.evidence. */
  evidence_paths?: Record<string, string>;
}

export interface ProjectConversionPolicy {
  writer_backend: ConvertWriterBackend;
  root_name: string;
  comment: string | null;
  burnup: number | null;
  h_factor_default: number | null;
  mixtures: string[];
}

export interface ProjectComponentStatus {
  id: string;
  label: string;
  role: string;
  target: string;
  neighbors: string;
  required: boolean;
  contract:
    | "converter-hdf5"
    | "physical-sph"
    | "native-sph"
    | "irena30-colorset-sph"
    | "physical-colorset-sph";
  format: ConvertFormat;
  identity: string | null;
  metadata: Record<string, JsonScalar>;
  /** Exact Converter writer/state policy declared for this component. */
  conversion: ProjectConversionPolicy;
  native_sph: ProjectNativeSphDeclaration | null;
  paths: ProjectComponentPaths;
  evidence: ProjectArtifactStatus;
  output: ProjectArtifactStatus;
  // Compatibility aliases.
  source_pair: ProjectArtifactStatus;
  handoff: ProjectArtifactStatus;
  cpo: ProjectArtifactStatus;
}

export type ProjectColorsetPaths = ProjectComponentPaths;
export type ProjectColorsetStatus = ProjectComponentStatus;

export interface ProjectConsumerRun {
  id: string;
  label: string;
  state: "missing" | "completed";
  deck_path: string | null;
  result_path: string | null;
  k_effective: number | null;
}

export interface ProjectConsumerStatus {
  kind: string;
  label: string;
  href: string | null;
  runs: ProjectConsumerRun[];
}

export interface ProjectAcceptanceEvidence {
  label: string;
  path: string;
  state: "present" | "missing" | "hash-unverified" | "hash-mismatch";
  sha256?: string | null;
}

export interface ProjectAcceptanceCriterion {
  id: string;
  label: string;
  status: "pending" | "passed" | "failed";
  evidence: ProjectAcceptanceEvidence[];
}

export interface ProjectMachineValidationEvidence {
  id: string;
  path: string | null;
  state:
    | "present"
    | "missing"
    | "invalid-path"
    | "hash-unverified"
    | "hash-mismatch";
  sha256: string | null;
}

export interface ProjectMachineValidationStatus {
  declared: boolean;
  contract: string | null;
  component: string | null;
  state: "not-declared" | "missing" | "passed" | "rejected" | "invalid";
  summary_path: string | null;
  summary_sha256: string | null;
  checks_passed: number;
  checks_total: number;
  evidence: ProjectMachineValidationEvidence[];
  issues: string[];
}

export interface ProjectAcceptanceStatus {
  declared: boolean;
  /** Who establishes this result: the project ledger alone or a bound validator. */
  basis: "not-required" | "project-declared" | "machine-verified";
  state:
    | "not-required"
    | "missing"
    | "pending"
    | "accepted"
    | "rejected"
    | "invalid";
  decision_path: string | null;
  decision_sha256: string | null;
  summary: string;
  criteria: ProjectAcceptanceCriterion[];
  issues: string[];
  machine_validation: ProjectMachineValidationStatus;
}

export interface ProjectStatus {
  schema: string;
  manifest_schema: string | null;
  manifest_path: string;
  configured: boolean;
  configuration_issues: string[];
  name: string;
  description: string;
  template: string | null;
  workflow: string | null;
  /** Whether validated handoffs are sufficient or a project acceptance ledger must close. */
  acceptance_mode: "handoff-only" | "physics-gated" | null;
  acceptance_required: boolean;
  root: string;
  root_exists: boolean;
  required_components: number;
  accepted_inputs: number;
  accepted_outputs: number;
  ready_components: number;
  /** Every required input and exact Converter/native-SPH output is live and validated. */
  handoffs_ready: boolean;
  /** Compatibility verdict for an accepted project gate; inspect acceptance_basis. */
  physics_accepted: boolean;
  acceptance_basis: "not-required" | "project-declared" | "machine-verified";
  /** The accepted ledger is additionally proven by its declared machine validator. */
  machine_verified_acceptance: boolean;
  /** The model owner accepted the external criteria without a machine validator. */
  project_declared_acceptance: boolean;
  /** Handoffs are ready and, when declared, the physics acceptance gate is accepted. */
  ready_for_consumer: boolean;
  components: ProjectComponentStatus[];
  consumer: ProjectConsumerStatus;
  acceptance: ProjectAcceptanceStatus;
  // Compatibility aliases.
  required_colorsets: number;
  accepted_handoffs: number;
  accepted_cpos: number;
  ready_for_core: boolean;
  colorsets: ProjectComponentStatus[];
  core: {
    directory: string;
    sn: ProjectCoreSolveStatus;
    spn: ProjectCoreSolveStatus;
    closure_state: "pending-reference-comparison";
  };
}

export type ProjectManifest = Record<string, JsonValue>;

export interface ProjectManifestResponse {
  schema: "openmc2donjon.project-manifest.v1";
  root: string;
  manifest_path: string;
  manifest: ProjectManifest;
}

export interface ProjectCoreSolveStatus {
  state: "missing" | "completed";
  deck_path: string;
  result_path: string;
  k_effective: number | null;
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

export interface OpenmcSphPhysicsSummaryQuality {
  decision: string;
  structural_passed: boolean;
  production_ready: boolean;
  demonstration_quality: boolean;
  max_flux_relative_std_dev: number;
  production_flux_relative_std_dev_threshold: number;
  demonstration_flux_relative_std_dev_threshold: number;
  notes: string[];
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
  reference_macrolib_path?: string | null;
  verification_macrolib_path?: string | null;
  result_listing_path?: string | null;
  execution_deck_path?: string | null;
  energy_coverage_path?: string | null;
  converter_receipt_path?: string | null;
  evidence_sha256?: Record<string, string>;
}

export interface NativeDragonSphConvergence {
  solver: string;
  solver_family?: "sn" | "spn" | string;
  scattering_moments_used?: number | null;
  iterations: number;
  epsilon: number;
  final_max_factor_update?: number | null;
  final_rms_factor_update: number;
  converged: boolean;
  one_speed_convergence_provable?: boolean;
  final_flux_solve_converged?: boolean;
  flux_nonconvergence_count?: number;
  flux_nonconvergence_markers?: Record<string, number>;
  factors_unmodified?: boolean;
  negative_factor_correction_count?: number;
  oscillation_stop_count?: number;
  normal_end: boolean;
}

export interface NativeDragonSphEigenvalueValidation {
  openmc_keff: number;
  openmc_keff_std_dev: number;
  reference_physical_balance_kind?: string;
  reference_physical_balance_keff?: number;
  reference_physical_balance_delta_pcm?: number;
  reference_physical_balance_z?: number;
  reference_collision_balance_kinf?: number;
  reference_collision_balance_tally_kinf?: number | null;
  reference_collision_balance_macrolib_vs_tally_delta_pcm?: number | null;
  reference_collision_balance_macrolib_vs_tally_z?: number | null;
  reference_collision_balance_std_dev?: number | null;
  reference_finite_balance_available?: boolean;
  reference_finite_balance_keff?: number | null;
  reference_finite_balance_std_dev?: number | null;
  reference_leakage?: number | null;
  reference_leakage_std_dev?: number | null;
  /** Compatibility fields: new summaries report the selected physical balance. */
  reference_rate_balance_keff: number;
  reference_rate_balance_delta_pcm: number;
  reference_rate_balance_z: number;
  donjon_keff: number;
  donjon_delta_pcm: number;
  donjon_z: number;
  max_abs_z: number;
}

export interface NativeDragonSphComponentBalanceRow {
  mixture_index: number;
  net_loss_reference: number;
  net_loss_donjon: number;
  net_loss_relative_residual: number;
  flux_rms_relative_residual: number;
  flux_max_relative_residual: number;
}

export interface NativeDragonSphComponentBalance {
  reference_net_loss: number;
  donjon_net_loss: number;
  net_loss_relative_residual: number;
  flux_rms_relative_residual: number;
  flux_max_relative_residual: number;
  power_normalization_factor: number;
  per_component: NativeDragonSphComponentBalanceRow[];
}

export interface NativeDragonSphEnergyCoverage {
  decision: string;
  energy_mesh_id?: string | null;
  mg_energy_min_ev?: number | null;
  mg_energy_max_ev?: number | null;
  max_outside_fraction?: number | null;
}

export interface NativeDragonSphAcceptanceChecks {
  donjon_normal_end: boolean;
  native_sph_converged: boolean;
  native_sph_factors_unmodified?: boolean;
  native_sph_not_stopped_by_oscillation?: boolean;
  one_speed_convergence_provable?: boolean;
  final_flux_solve_converged?: boolean;
  energy_coverage_passed: boolean;
  leakage_balance_available_when_required?: boolean;
  reference_physical_balance_within_openmc_uncertainty?: boolean;
  reference_rate_balance_within_openmc_uncertainty: boolean;
  reference_macrolib_matches_direct_collision_balance_tally?: boolean;
  flux_uncertainty_within_production_limit?: boolean;
  donjon_keff_within_openmc_uncertainty: boolean;
  empirical_eigenvalue_multiplier_used: boolean | null;
  adf_used: boolean | null;
}

export interface NativeDragonSphGeometry {
  kind: string;
  boundary_conditions: string;
  coarse_node_side_cm?: number | null;
  homogenization_volume_includes_node_catchall?: boolean;
  center_kind?: string | null;
  neighbor_kinds?: string[] | null;
}

export interface OpenmcSphReactionRateResidual {
  max_relative_residual: number;
  mean_relative_residual?: number | null;
  valid_bins?: number | null;
  worst?: {
    reaction?: string | null;
    mixture?: string | null;
    group?: number | null;
    relative_residual?: number | null;
  } | null;
}

export interface OpenmcSphReactionRatePreservation {
  reference?: string | null;
  current_solve?: OpenmcSphReactionRateResidual | null;
  after_sph_update_frozen_flux?: OpenmcSphReactionRateResidual | null;
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

export interface OpenmcSphDonjonConsumption {
  status: "passed" | "failed" | "not_run" | string;
  mode?: string | null;
  script?: string | null;
  result_path?: string | null;
  expected_mix3_g1?: number | null;
  target_mix?: number | null;
  expected_g1?: number | null;
  pn_var_value?: number | null;
  sn_var_value?: number | null;
  pn_ntot0_ratio?: number | null;
  sn_ntot0_ratio?: number | null;
}

export interface OpenmcSphDonjonSolveMode {
  k_effective?: number | null;
  vs_openmc_ce?: {
    flux_shape_max_relative_residual?: number | null;
    flux_shape_mean_relative_residual?: number | null;
    scaled_flux_max_relative_residual?: number | null;
    scaled_flux_mean_relative_residual?: number | null;
  } | null;
}

export interface OpenmcSphDonjonSolveDiagnostic {
  status?: "recorded" | "not_run" | "failed" | string;
  decision?: string | null;
  script?: string | null;
  geometry?: string | null;
  note?: string | null;
  modes?: {
    diffusion?: OpenmcSphDonjonSolveMode | null;
    spn3?: OpenmcSphDonjonSolveMode | null;
  } | null;
}

export interface OpenmcSphEvidenceArtifact {
  label: "augmented_hdf5" | "ascii" | string;
  path: string | null;
  status: "present" | "missing" | "not_declared" | "outside_scope" | "fixture" | string;
  manifest_key?: string | null;
  expected_sha256?: string | null;
  actual_sha256?: string | null;
  hash_matches?: boolean | null;
}

export interface NativeSphCorrectionEvidenceItem {
  used: boolean | null;
  evidence_status: "verified_absent" | "observed" | "not_provable" | string;
  issues: string[];
}

export interface NativeSphCorrectionPolicyEvidence {
  status: "verified_absent" | "forbidden_correction_observed" | "not_provable" | string;
  execution_deck_path?: string | null;
  execution_deck_sha256?: string | null;
  deck_reproduced_in_result_listing?: boolean;
  adf?: NativeSphCorrectionEvidenceItem;
  empirical_eigenvalue_multiplier?: NativeSphCorrectionEvidenceItem & {
    unclassified_evaluate_statements?: string[];
  };
  issues?: string[];
}

export interface OpenmcSphEvidenceIntegrity {
  verified: boolean | null;
  issues: string[];
  handoff_sha256_manifest_complete: boolean | null;
  all_handoff_sha256_match: boolean | null;
  converter_receipt?: { valid: boolean; issues: string[] } | null;
  openmc_provenance?: {
    valid: boolean;
    status?: string | null;
    digest_sha256?: string | null;
    payload_sha256?: string | null;
    issues: string[];
  } | null;
  forbidden_corrections?: NativeSphCorrectionPolicyEvidence | null;
}

export interface OpenmcSphEvidenceAudit {
  origin: "live_file" | "mock_fixture" | "recorded_fixture" | string;
  summary_path: string | null;
  summary_file_present: boolean;
  referenced_handoff_artifacts: OpenmcSphEvidenceArtifact[];
  all_referenced_handoff_artifacts_present: boolean | null;
  all_referenced_handoff_artifacts_hash_verified?: boolean | null;
  evidence_integrity?: OpenmcSphEvidenceIntegrity | null;
  physics_acceptance: "not_evaluated" | string;
  reactor_acceptance: "not_evaluated" | string;
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
  sph_target?: string | null;
  zero_flux_policy?: string | null;
  identity_bin_count?: number | null;
  flux_floor_rel?: number | null;
  floored_bin_count?: number | null;
  freeze_groups?: number[] | null;
  frozen_group_bin_count?: number | null;
  flux_uncertainty: OpenmcSphPhysicsSummaryFluxUncertainty;
  quality?: OpenmcSphPhysicsSummaryQuality;
  sph: OpenmcSphPhysicsSummarySph;
  reaction_rate_preservation?: OpenmcSphReactionRatePreservation;
  handoff: OpenmcSphPhysicsSummaryHandoff;
  donjon_consumption?: OpenmcSphDonjonConsumption | null;
  donjon_solve_diagnostic?: OpenmcSphDonjonSolveDiagnostic | null;
  native_sph?: NativeDragonSphConvergence | null;
  geometry?: NativeDragonSphGeometry | null;
  eigenvalue_validation?: NativeDragonSphEigenvalueValidation | null;
  component_balance?: NativeDragonSphComponentBalance | null;
  energy_coverage?: NativeDragonSphEnergyCoverage | null;
  acceptance_checks?: NativeDragonSphAcceptanceChecks | null;
  evidence_audit?: OpenmcSphEvidenceAudit;
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
  require_physical_sph?: boolean;
  warn_unknown_energy_mesh: boolean;
  require_known_energy_mesh: boolean;
  root_name?: string;
  comment?: string | null;
  burnup?: number | null;
  h_factor_default?: number | null;
  mixtures?: string[] | null;
  project_root?: string | null;
  component_id?: string | null;
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
  openmc_provenance?: OpenmcProvenance | null;
  adf_mixtures?: number | null;
  adf_faces?: string[];
  sph_calculations?: number | null;
  sph_applied?: boolean | null;
  sph_applied_source?: string | null;
  sph_apply_operator?: string | null;
  sph_kind?: string | null;
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
  root_name?: string;
  comment?: string | null;
  burnup?: number | null;
  h_factor_default?: number | null;
  mixtures?: string[] | null;
  project_root?: string | null;
  component_id?: string | null;
  physical_sph_required?: boolean;
  production_requested?: boolean;
  preflight_policy?: {
    level: "none" | "engineering" | "production";
    production_requested: boolean;
    preflight_executed: boolean;
  };
  input_path: string;
  openmc_provenance?: OpenmcProvenance | null;
  input_sha256?: string | null;
  output_path: string;
  output_sha256?: string | null;
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
  sha256: string | null;
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
  plan_scope: "export" | "complete";
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
  plan_scope: "export" | "complete";
  workflow_label: string;
  equivalence: OpenmcEquivalenceMode;
  steps: OpenmcWorkflowStep[];
  artifacts: OpenmcWorkflowArtifact[];
  checks: OpenmcWorkflowCheck[];
  commands: OpenmcWorkflowCommand[];
  primary_command_text: string;
  next_actions: string[];
}

export interface OpenmcExportExecutionRequest {
  recipe_path: string;
  statepoint_path: string;
  load_statepoint: boolean;
  output_path: string;
  overwrite: boolean;
}

export interface OpenmcExportExecutionResponse {
  schema: string;
  ok: boolean;
  mock_mode: boolean;
  output_path: string;
  energy_groups: number;
  legendre_order: number;
  mixtures: number;
  std_dev_datasets: number;
  std_dev_expected: number;
  openmc_provenance: OpenmcProvenance;
}

export interface SphSidecarExecutionRequest {
  strategy: "ratio";
  input_h5: string;
  output_path: string;
  reference_flux?: string;
  mg_flux?: string;
  previous_sph?: string;
  table_output?: string;
  damping?: number;
  flux_normalization?: "none" | "total" | "power" | "auto";
  sph_target?: "flux" | "rate";
  zero_flux_policy?: "reject" | "identity";
  flux_floor_rel?: number | null;
  freeze_groups?: number[];
  clip_min?: number | null;
  clip_max?: number | null;
  summary_json?: string;
  force: boolean;
}

export interface ApplySphExecutionRequest {
  input_h5: string;
  sph_source: string;
  output_path: string;
  input_format: "converter" | "openmc-mgxs";
  summary_json?: string;
  force: boolean;
}

export interface SphExecutionResponse {
  schema: string;
  ok: boolean;
  operation: "sph-sidecar" | "apply-sph";
  output_path: string;
  table_path?: string | null;
  summary_path?: string | null;
  mixtures: number;
  energy_groups: number;
  sph_min: number;
  sph_max: number;
  strategy?: "ratio";
  raw_update_minimum?: number;
  raw_update_maximum?: number;
  max_update_residual?: number;
  converged?: boolean;
  scaled_datasets?: number;
}

export interface DonjonExecutionRequest {
  deck_text: string;
  deck_filename: string;
  input_files?: { source_path: string; relative_path: string }[];
  donjon_root?: string;
  artifact_directory?: string;
  working_directory?: string;
  source_deck_path?: string;
  source_deck_sha256?: string;
  project_root?: string;
  component_id?: string;
  timeout_seconds?: number;
  expect_k_effective?: boolean;
}

export interface ExecutionJob {
  schema: string;
  job_id: string;
  run_id: string;
  operation: "donjon";
  status: "queued" | "running" | "completed" | "failed";
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  message: string;
  result_path: string | null;
  deck_path: string | null;
  deck_sha256?: string | null;
  source_deck_path?: string | null;
  source_deck_sha256?: string | null;
  project_root?: string | null;
  component_id?: string | null;
  declaration_sha256?: string | null;
  project_manifest_path?: string | null;
  project_manifest_sha256?: string | null;
  project_manifest_snapshot_path?: string | null;
  request_binding_sha256?: string | null;
  owner_path?: string | null;
  owner_token?: string | null;
  owner_pid?: number | null;
  artifacts_finalized?: boolean;
  k_effective: number | null;
  return_code: number | null;
  log_tail: string;
  working_directory: string | null;
  archive_root: string | null;
  run_directory: string | null;
  request_path: string | null;
  status_path: string | null;
  artifacts_path: string | null;
  completion_path?: string | null;
  completion_sha256?: string | null;
  log_path: string | null;
  staged_manifest_path: string | null;
  runtime_output_directory: string | null;
}

export interface ExecutionJobList {
  schema: "openmc2donjon.web-donjon-job-list.v1";
  artifact_directory: string;
  jobs: ExecutionJob[];
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
  executeOpenmcExport: (request: OpenmcExportExecutionRequest) =>
    postJson<OpenmcExportExecutionResponse>("/api/execute/openmc-export", request),
  executeSphSidecar: (request: SphSidecarExecutionRequest) =>
    postJson<SphExecutionResponse>("/api/execute/sph-sidecar", request),
  executeApplySph: (request: ApplySphExecutionRequest) =>
    postJson<SphExecutionResponse>("/api/execute/apply-sph", request),
  executeDonjon: (request: DonjonExecutionRequest) =>
    postJson<ExecutionJob>("/api/execute/donjon", request),
  executionJob: (jobId: string, artifactDirectory?: string) =>
    getJson<ExecutionJob>(
      `/api/execution/jobs/${encodeURIComponent(jobId)}`,
      { artifact_directory: artifactDirectory },
    ),
  executionJobs: (artifactDirectory: string) =>
    getJson<ExecutionJobList>("/api/execution/jobs", {
      artifact_directory: artifactDirectory,
    }),
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
  projectStatus: (root: string) =>
    getJson<ProjectStatus>("/api/project/status", { root }),
  projectManifest: (root: string) =>
    getJson<ProjectManifestResponse>("/api/project/manifest", { root }),
  saveProjectManifest: (root: string, manifest: ProjectManifest) =>
    postJson<ProjectManifestResponse>("/api/project/manifest", {
      root,
      manifest,
    }),
  createProject: (
    root: string,
    name?: string,
    acceptanceMode: "handoff-only" | "physics-gated" = "handoff-only",
    writerBackend: ConvertWriterBackend = "ascii",
  ) =>
    postJson<ProjectStatus>("/api/project/create", {
      root,
      name,
      acceptance_mode: acceptanceMode,
      writer_backend: writerBackend,
    }),
  openmcSphSummary: (path: string) =>
    getJson<OpenmcSphPhysicsSummary>("/api/openmc-sph-summary", { path }),
};
