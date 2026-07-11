"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { AcceptedValidationEntry } from "@/lib/acceptedValidation";
import { ACCEPTED_VALIDATION_ENTRIES } from "@/lib/acceptedValidation";
import { ApiError, HealthResponse, api } from "@/lib/api";
import type { DemoShortcut } from "@/lib/demoShortcuts";
import { HOME_DEMO_SHORTCUTS } from "@/lib/demoShortcuts";
import { HOME_HERO } from "@/lib/homeHero";
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
              {HOME_HERO.kicker}
            </p>
            <h1 className="mt-2 text-4xl font-bold tracking-tight">
              <span className="grad-text">{HOME_HERO.heading}</span>
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
              {HOME_HERO.paragraph}
            </p>
          </div>
          <Link
            href="/convert?intent=direct-convert&format=multicompo"
            className="btn btn-primary shrink-0"
          >
            Start converter
          </Link>
        </header>

        <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
          <div className="space-y-5">
            <StartHere entries={TASK_ENTRYPOINTS} />
            <AcceptedValidation entries={ACCEPTED_VALIDATION_ENTRIES} />
            <AfterYouConvert />
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
      <h2 className="text-base font-semibold tracking-tight">Start here</h2>
      <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
        Most users start with Convert. Use OpenMC SPH only when the HDF5
        still needs equivalence factors, and Inspect when you only need to
        understand a file before converting.
      </p>

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

function AcceptedValidation({
  entries,
}: {
  entries: readonly AcceptedValidationEntry[];
}) {
  return (
    <section className="glass rounded-xl p-5">
      <h2 className="text-base font-semibold tracking-tight">
        Accepted validation
      </h2>
      <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
        The route is validated against paired OpenMC references on Cartesian
        and hexagonal cores, not only on unit tests.
      </p>
      <ul className="mt-4 grid gap-3 md:grid-cols-3">
        {entries.map((entry) => (
          <li
            key={entry.id}
            className="rounded-lg border border-[var(--edge)] bg-black/10 p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[11px] text-[var(--accent)]">
                {entry.label}
              </span>
              <span className="text-[11px] text-[var(--fg-3)]">
                {entry.result}
              </span>
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {entry.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {entry.body}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AfterYouConvert() {
  const links = [
    {
      href: "/donjon",
      title: "DONJON deck guide",
      body: "Generate the editable deck skeleton and run commands that consume the ASCII output — works from the ASCII path directly.",
    },
    {
      href: "/builder?command=bundle",
      title: "Bundle",
      body: "Package the run when you want the manifest-backed record — recipients open the bundle on the DONJON page.",
    },
  ] as const;
  return (
    <section className="glass rounded-xl p-5">
      <h2 className="text-base font-semibold tracking-tight">
        After you convert
      </h2>
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
    </section>
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
        <div className="mt-4">
          <Link href={primary.href} className="btn btn-primary w-full">
            {primary.cta}
          </Link>
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
          <code className="font-mono">openmc2donjon serve</code> for real
          files, or <code className="font-mono">openmc2donjon serve --mock</code>{" "}
          for the bundled demo — run one or the other.
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
