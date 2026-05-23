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

export interface HandoffInspection {
  schema: string;
  path: string;
  ok: boolean;
  energy_groups: number | null;
  legendre_order: number | null;
  energy_bounds_shape: number[] | null;
  energy_min: number | null;
  energy_max: number | null;
  mesh_match: MeshMatch | null;
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

export const api = {
  health: () => getJson<HealthResponse>("/api/health"),
  inspect: (path: string) =>
    getJson<HandoffInspection>("/api/inspect", { path }),
};
