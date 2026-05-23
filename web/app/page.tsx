"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, HealthResponse, api } from "@/lib/api";

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: HealthResponse }
  | { kind: "error"; message: string };

export default function Home() {
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  const refresh = useCallback(async () => {
    setStatus({ kind: "loading" });
    try {
      const data = await api.health();
      setStatus({ kind: "ok", data });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.message}`
          : err instanceof Error
            ? err.message
            : "Unknown error";
      setStatus({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <main className="min-h-screen px-6 py-16">
      <div className="mx-auto max-w-3xl">
        <header className="mb-10">
          <h1 className="text-4xl font-bold tracking-tight">
            <span className="grad-text">openmc2donjon</span>
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-2)]">
            Web interface for the OpenMC{" "}
            <span className="font-mono">→</span> DRAGON/DONJON handoff
            pipeline. M0 scaffold: the home page just confirms the FastAPI
            backend is reachable.
          </p>
        </header>

        <section className="glass rounded-xl p-6">
          <div className="flex items-baseline justify-between gap-4 flex-wrap">
            <h2 className="text-base font-semibold tracking-tight">
              Backend status
            </h2>
            <button
              type="button"
              onClick={refresh}
              className="btn btn-secondary tab-num"
              aria-label="Refresh backend health"
            >
              Refresh
            </button>
          </div>

          <div className="mt-4 text-sm tab-num">
            <StatusView status={status} />
          </div>
        </section>

        <p className="mt-8 text-[12px] text-[var(--fg-3)]">
          Set <code className="font-mono">NEXT_PUBLIC_API_BASE_URL</code> in{" "}
          <code className="font-mono">web/.env.local</code> if the backend is
          not on{" "}
          <code className="font-mono">http://localhost:8000</code>.
        </p>
      </div>
    </main>
  );
}

function StatusView({ status }: { status: Status }) {
  if (status.kind === "idle" || status.kind === "loading") {
    return <span className="text-[var(--fg-2)]">Checking…</span>;
  }
  if (status.kind === "error") {
    return (
      <div className="space-y-1">
        <div className="text-rose-300">Cannot reach backend.</div>
        <div className="text-[var(--fg-2)]">{status.message}</div>
        <div className="text-[var(--fg-3)] text-[12px]">
          Start it with{" "}
          <code className="font-mono">openmc2donjon serve</code>.
        </div>
      </div>
    );
  }
  const { data } = status;
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5">
      <dt className="text-[var(--fg-2)]">status</dt>
      <dd>
        <span
          className={
            data.status === "ok" ? "text-emerald-300" : "text-amber-300"
          }
        >
          {data.status}
        </span>
      </dd>
      <dt className="text-[var(--fg-2)]">version</dt>
      <dd>{data.version}</dd>
      <dt className="text-[var(--fg-2)]">mock mode</dt>
      <dd>
        {data.mock_mode ? (
          <span className="text-amber-300">on</span>
        ) : (
          <span className="text-[var(--fg-1)]">off</span>
        )}
      </dd>
    </dl>
  );
}
