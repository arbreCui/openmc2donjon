"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, HealthResponse, api } from "@/lib/api";
import type { DemoShortcut } from "@/lib/demoShortcuts";
import { HOME_DEMO_SHORTCUTS } from "@/lib/demoShortcuts";
import type { ProductionPathStep } from "@/lib/productionPath";
import { PRODUCTION_PATH_STEPS } from "@/lib/productionPath";
import type { TaskEntrypoint } from "@/lib/taskEntrypoints";
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
    <main className="min-h-screen px-6 py-12">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
              Converter-first production handoff
            </p>
            <h1 className="mt-2 text-4xl font-bold tracking-tight">
              <span className="grad-text">OpenMC MGXS to DONJON ASCII</span>
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
              The product center is the direct converter: take an OpenMC MGXS
              HDF5 handoff, run a no-write production check, write
              L_MULTICOMPO or L_MACROLIB ASCII, then hand that file to DONJON.
              If SPH is needed, prepare it upstream with OpenMC CE/MG first.
            </p>
          </div>
          <Link
            href="/convert?intent=direct-convert&format=multicompo&check=1&production=1"
            className="btn btn-primary shrink-0"
          >
            Start converter
          </Link>
        </header>

        <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
          <div className="space-y-5">
            <StartHere entries={TASK_ENTRYPOINTS} />
            <WorkflowSummary steps={PRODUCTION_PATH_STEPS} />
            <AdvancedTools />
          </div>

          <aside className="space-y-5">
            <BackendStatusCard status={status} onRefresh={refresh} />
            <DemoPanel
              state={demoBackendState(status)}
              shortcuts={HOME_DEMO_SHORTCUTS}
            />
          </aside>
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

function StartHere({ entries }: { entries: readonly TaskEntrypoint[] }) {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Start here
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Most users start with Convert. Use OpenMC SPH only when the HDF5
            still needs equivalence factors, and Inspect when you only need to
            understand a file before converting.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          3 choices
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {entries.map((entry, index) => (
          <Link
            key={entry.id}
            href={entry.href}
            className="group rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4 transition hover:border-[var(--edge-bright)] hover:bg-white/[0.045]"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="tab-num rounded-md border border-[var(--edge)] bg-black/20 px-2 py-1 text-[11px] font-semibold text-[var(--accent)]">
                {index + 1}
              </span>
              <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                {entry.eyebrow}
              </span>
            </div>
            <h3 className="mt-3 text-sm font-semibold tracking-tight text-[var(--fg-0)]">
              {entry.title}
            </h3>
            <p className="mt-2 min-h-[4rem] text-[12px] leading-5 text-[var(--fg-2)]">
              {entry.body}
            </p>
            <div className="mt-4 text-[12px] font-medium text-[var(--accent-2)] group-hover:underline">
              {entry.cta}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

function WorkflowSummary({ steps }: { steps: readonly ProductionPathStep[] }) {
  return (
    <section className="glass rounded-xl p-5">
      <h2 className="text-base font-semibold tracking-tight">What happens next</h2>
      <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
        The converter does not solve reactor physics. It serializes the
        homogenized data and optional equivalence factors that already exist in
        the HDF5 handoff.
      </p>
      <ol className="mt-4 grid gap-3 md:grid-cols-3">
        {steps.map((step) => (
          <li
            key={step.id}
            className="rounded-lg border border-[var(--edge)] bg-black/10 p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[11px] text-[var(--accent)]">
                {step.label}
              </span>
              <span className="text-[11px] text-[var(--fg-3)]">{step.result}</span>
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {step.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {step.body}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function AdvancedTools() {
  const links = [
    {
      href: "/commands",
      title: "Command catalog",
      body: "Reference map for every CLI command. Use it after the main flow is clear.",
    },
    {
      href: "/equivalence?kind=adf-sidecar",
      title: "ADF/SPH sidecar builders",
      body: "Command builders for sidecars. They do not replace the converter path.",
    },
    {
      href: "/builder?command=bundle",
      title: "Bundle handoff",
      body: "Package ASCII, HDF5, reports, and DONJON input cards.",
    },
    {
      href: "/pygan",
      title: "PyGan option",
      body: "Optional DRAGON/DONJON integration diagnostics; ASCII is default.",
    },
  ] as const;
  return (
    <details className="glass rounded-xl p-5">
      <summary className="cursor-pointer text-base font-semibold tracking-tight">
        Advanced tools
      </summary>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-3 transition hover:border-[var(--edge-bright)]"
          >
            <div className="text-sm font-semibold">{link.title}</div>
            <div className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {link.body}
            </div>
          </Link>
        ))}
      </div>
    </details>
  );
}

function BackendStatusCard({
  status,
  onRefresh,
}: {
  status: Status;
  onRefresh: () => void;
}) {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="text-base font-semibold tracking-tight">Backend</h2>
        <button
          type="button"
          onClick={onRefresh}
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
  );
}

function DemoPanel({
  state,
  shortcuts,
}: {
  state: ReturnType<typeof demoBackendState>;
  shortcuts: readonly DemoShortcut[];
}) {
  const primary = shortcuts[0];
  const secondary = shortcuts.slice(1);
  const enabled = state.kind === "ready" && state.mockMode;
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold tracking-tight">Demo</h2>
        <DemoBadge state={state} />
      </div>
      <p className="mt-2 text-sm leading-relaxed text-[var(--fg-2)]">
        Use this when showing the product without hunting for local files.
      </p>
      {enabled ? (
        <div className="mt-4 space-y-3">
          <Link href={primary.href} className="btn btn-primary w-full">
            {primary.cta}
          </Link>
          <div className="space-y-2">
            {secondary.map((shortcut) => (
              <Link
                key={shortcut.id}
                href={shortcut.href}
                className="block rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 text-[12px] text-[var(--fg-2)] transition hover:border-[var(--edge-bright)] hover:text-[var(--fg-0)]"
              >
                {shortcut.title}
              </Link>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-[var(--edge)] bg-white/[0.025] p-3 text-[12px] leading-5 text-[var(--fg-2)]">
          <DemoDisabledMessage state={state} />
        </div>
      )}
    </section>
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

function DemoDisabledMessage({ state }: { state: ReturnType<typeof demoBackendState> }) {
  if (state.kind === "checking") {
    return <>Checking backend mode before enabling demo shortcuts.</>;
  }
  if (state.kind === "unavailable") {
    return (
      <>
        Start the backend with{" "}
        <code className="font-mono">openmc2donjon serve --mock</code> to enable
        bundled demos.
      </>
    );
  }
  return (
    <>
      Demo shortcuts are hidden in live mode so real runs do not accidentally
      use <code className="font-mono">/mock</code> paths.
    </>
  );
}

function DemoBadge({ state }: { state: ReturnType<typeof demoBackendState> }) {
  if (state.kind === "checking") {
    return (
      <span className="rounded-full border border-[var(--edge)] px-2.5 py-1 text-[11px] text-[var(--fg-2)]">
        checking
      </span>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <span className="rounded-full border border-rose-400/20 bg-rose-400/10 px-2.5 py-1 text-[11px] text-rose-200">
        offline
      </span>
    );
  }
  return (
    <span
      className={
        state.mockMode
          ? "rounded-full border border-amber-300/30 bg-amber-300/10 px-2.5 py-1 text-[11px] text-amber-200"
          : "rounded-full border border-[var(--edge)] px-2.5 py-1 text-[11px] text-[var(--fg-2)]"
      }
    >
      {state.mockMode ? "mock" : "live"}
    </span>
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
