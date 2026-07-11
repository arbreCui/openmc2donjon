import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("baseUrl fallback", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("falls back to the localhost default when NEXT_PUBLIC_API_BASE_URL is empty", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ status: "ok", mock_mode: false, version: "0.1.0" }),
        { status: 200 },
      ),
    );

    await api.health();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/health",
      { cache: "no-store" },
    );
  });
});

describe("api.pyganDoctor", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("falls back to /api/health when the dedicated PyGan doctor route is missing", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Not Found" }), {
          status: 404,
          statusText: "Not Found",
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "ok",
            mock_mode: true,
            version: "0.1.2",
            pygan_backend: {
              available: false,
              role: "optional PyGan writer backend",
              install_hint: "install PyGan",
              modules: [],
              missing_modules: ["lcm"],
            },
          }),
          { status: 200 },
        ),
      );

    const status = await api.pyganDoctor();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/pygan/doctor",
      { cache: "no-store" },
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/health",
      { cache: "no-store" },
    );
    expect(status).toMatchObject({
      available: false,
      role: "optional PyGan writer backend",
      schema: "openmc2donjon.pygan-doctor.v1",
      mock_mode: true,
      missing_modules: ["lcm"],
    });
  });

  it("keeps surfacing the original 404 if health has no PyGan payload", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Not Found" }), {
          status: 404,
          statusText: "Not Found",
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "ok",
            mock_mode: false,
            version: "0.1.2",
          }),
          { status: 200 },
        ),
      );

    await expect(api.pyganDoctor()).rejects.toMatchObject({
      status: 404,
      detail: "Not Found",
    });
  });
});
