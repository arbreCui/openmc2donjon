"use client";

import { useCallback, useEffect, useState } from "react";
import HomeDemoShortcuts from "@/components/HomeDemoShortcuts";
import ProductionPathStrip from "@/components/ProductionPathStrip";
import TaskLauncher from "@/components/TaskLauncher";
import { ApiError, HealthResponse, api } from "@/lib/api";
import { HOME_DEMO_SHORTCUTS } from "@/lib/demoShortcuts";
import { PRODUCTION_PATH_STEPS } from "@/lib/productionPath";
import { TASK_ENTRYPOINTS } from "@/lib/taskEntrypoints";

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
      <div className="mx-auto max-w-6xl">
        <header className="mb-10">
          <h1 className="text-4xl font-bold tracking-tight">
            <span className="grad-text">openmc2donjon</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Local workflow cockpit for OpenMC{" "}
            <span className="font-mono">→</span> DRAGON/DONJON handoff
            production: prepare OpenMC CE/MG equivalence evidence, inspect the
            HDF5 contract, convert to ASCII, apply ADF/SPH sidecars, and bundle
            the DONJON handoff.
          </p>
        </header>

        <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
          <div className="space-y-5">
            <ProductionPathStrip steps={PRODUCTION_PATH_STEPS} />

            <TaskLauncher
              title="What are you doing now?"
              summary="Pick the entry that matches the artifact you already have. Each path stays local and keeps the equivalent CLI visible."
              entries={TASK_ENTRYPOINTS}
            />

            <HomeDemoShortcuts
              state={demoBackendState(status)}
              shortcuts={HOME_DEMO_SHORTCUTS}
            />
          </div>

          <section className="glass rounded-xl p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
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
        </div>

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

function demoBackendState(status: Status) {
  if (status.kind === "idle" || status.kind === "loading") {
    return { kind: "checking" } as const;
  }
  if (status.kind === "error") {
    return { kind: "unavailable" } as const;
  }
  return { kind: "ready", mockMode: status.data.mock_mode } as const;
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
