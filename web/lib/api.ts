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

export class ApiError extends Error {
  constructor(message: string, public status: number) {
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

async function getJson<T>(path: string): Promise<T> {
  const url = `${baseUrl()}${path}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(
      `GET ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => getJson<HealthResponse>("/api/health"),
};
