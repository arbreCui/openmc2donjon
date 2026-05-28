import Link from "next/link";
import { useEffect, useState } from "react";

import { CopyCliButton } from "@/components/commands/CopyCliButton";
import {
  ApiError,
  api,
} from "@/lib/api";
import {
  PRODUCTION_MINICASE_ARTIFACTS,
  PRODUCTION_MINICASE_COMMAND,
  PRODUCTION_MINICASE_DEMO,
  convertDemoWalkthrough,
  productionMinicaseAvailability,
  type ConvertDemoArtifactRole,
  type ProductionMinicaseAvailabilityTone,
} from "@/lib/convertDemo";
import {
  fileStatusLabel,
  fileStatusTone,
  type FileStatusState,
} from "@/lib/fileStatus";

type ArtifactStatusMap = Record<string, FileStatusState>;

export default function LiveMinicaseCard({ onApply }: { onApply: () => void }) {
  const steps = convertDemoWalkthrough(PRODUCTION_MINICASE_DEMO);
  const [statuses, setStatuses] = useState<ArtifactStatusMap>(
    loadingArtifactStatuses,
  );
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatuses(loadingArtifactStatuses());
    Promise.all(
      PRODUCTION_MINICASE_ARTIFACTS.map(async (artifact) => {
        try {
          return {
            id: artifact.id,
            state: {
              kind: "ok",
              status: await api.fileStatus(artifact.path),
            } satisfies FileStatusState,
          };
        } catch (err) {
          const message =
            err instanceof ApiError
              ? err.detail ?? err.message
              : err instanceof Error
                ? err.message
                : "status check failed";
          return {
            id: artifact.id,
            state: { kind: "error", message } satisfies FileStatusState,
          };
        }
      }),
    ).then((items) => {
      if (cancelled) return;
      setStatuses(Object.fromEntries(items.map((item) => [item.id, item.state])));
    });
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  const loadingCount = PRODUCTION_MINICASE_ARTIFACTS.filter(
    (artifact) => statuses[artifact.id]?.kind === "loading",
  ).length;
  const errorCount = PRODUCTION_MINICASE_ARTIFACTS.filter(
    (artifact) => statuses[artifact.id]?.kind === "error",
  ).length;
  const starterMissingCount = countMissingMinicaseArtifacts(statuses, "starter");
  const downstreamMissingCount = countMissingMinicaseArtifacts(
    statuses,
    "downstream",
  );
  const availability = productionMinicaseAvailability({
    loadingCount,
    errorCount,
    starterMissingCount,
    downstreamMissingCount,
  });
  const mgxsArtifact = PRODUCTION_MINICASE_ARTIFACTS.find(
    (artifact) => artifact.id === "mgxs",
  );
  const bundleArtifact = PRODUCTION_MINICASE_ARTIFACTS.find(
    (artifact) => artifact.id === "bundle",
  );

  return (
    <section
      className={
        "mb-5 rounded-xl border p-4 " +
        liveMinicaseCardClass(availability.tone)
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <LiveMinicaseToneBadge tone={availability.tone} />
            <span className="text-[10px] uppercase tracking-[0.14em] text-emerald-200/80">
              Live production minicase
            </span>
          </div>
          <h2 className="mt-1 text-sm font-semibold tracking-tight text-emerald-100">
            {availability.title}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--fg-2)]">
            {availability.body}
          </p>
          <p className="mt-2 max-w-3xl text-[12px] leading-5 text-[var(--fg-3)]">
            {PRODUCTION_MINICASE_DEMO.description}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {availability.canUsePaths ? (
            <>
              <button
                type="button"
                onClick={onApply}
                className="btn btn-primary"
              >
                Use generated paths
              </button>
              {mgxsArtifact?.href ? (
                <Link href={mgxsArtifact.href} className="btn btn-secondary">
                  Inspect MGXS
                </Link>
              ) : null}
              {bundleArtifact?.href ? (
                <Link href={bundleArtifact.href} className="btn btn-secondary">
                  Bundle
                </Link>
              ) : null}
            </>
          ) : (
            <CopyCliButton
              value={PRODUCTION_MINICASE_COMMAND}
              compact
              label="Copy smoke command"
              copiedLabel="Copied"
            />
          )}
          <button
            type="button"
            onClick={() => setRefreshToken((value) => value + 1)}
            className="btn btn-secondary"
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[12px] font-semibold tracking-tight text-emerald-100">
              {availability.canUsePaths
                ? "Regenerate the real handoff when needed"
                : "Generate the real handoff first"}
            </div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              This smoke builds a tiny OpenMC case, exports MGXS, runs production
              checks, and writes the managed output directory used by this card.
            </p>
          </div>
          <CopyCliButton
            value={PRODUCTION_MINICASE_COMMAND}
            compact
            label="Copy command"
            copiedLabel="Copied"
          />
        </div>
        <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
          {PRODUCTION_MINICASE_COMMAND}
        </pre>
      </div>

      <div className="mt-4 grid gap-2 lg:grid-cols-4">
        {PRODUCTION_MINICASE_ARTIFACTS.map((artifact) => (
          <article
            key={artifact.id}
            className="min-w-0 rounded-lg border border-[var(--edge)] bg-black/10 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="rounded border border-emerald-200/25 bg-emerald-200/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-emerald-100">
                  {artifact.label}
                </span>
                <span className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                  {artifactRoleLabel(artifact.role)}
                </span>
              </div>
              {artifact.href ? (
                <Link
                  href={artifact.href}
                  className="text-[11px] text-[var(--accent-2)] hover:underline"
                >
                  open
                </Link>
              ) : null}
            </div>
            <div className="mt-2">
              <ArtifactStatusBadge state={statuses[artifact.id]} />
            </div>
            <h3 className="mt-2 text-[12px] font-semibold tracking-tight text-emerald-50">
              {artifact.title}
            </h3>
            <div
              className="mt-1 truncate font-mono text-[11px] text-[var(--fg-1)]"
              title={artifact.path}
            >
              {artifact.path}
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
              {artifact.body}
            </p>
            <div className="mt-2">
              <CopyCliButton
                value={artifact.path}
                compact
                label="Copy path"
                copiedLabel="Copied"
                ariaLabel={`Copy ${artifact.label} path`}
              />
            </div>
          </article>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--edge)] bg-black/10 px-3 py-2 text-[12px] text-[var(--fg-2)]">
        <span>{availability.statusMessage}</span>
        <button
          type="button"
          onClick={() => setRefreshToken((value) => value + 1)}
          className="text-[var(--accent-2)] hover:underline"
        >
          Refresh status
        </button>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-4">
        {steps.map((step) => (
          <div key={step.id} className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded border border-emerald-200/25 bg-emerald-200/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-emerald-100">
                {step.label}
              </span>
              <h3 className="text-[12px] font-semibold tracking-tight text-emerald-50">
                {step.title}
              </h3>
            </div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {step.body}
            </p>
            {step.href ? (
              <Link
                href={step.href}
                className="mt-1 inline-flex text-[12px] text-[var(--accent-2)] hover:underline"
              >
                Open after run
              </Link>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function loadingArtifactStatuses(): ArtifactStatusMap {
  return Object.fromEntries(
    PRODUCTION_MINICASE_ARTIFACTS.map((artifact) => [
      artifact.id,
      { kind: "loading" } satisfies FileStatusState,
    ]),
  );
}

function countMissingMinicaseArtifacts(
  statuses: ArtifactStatusMap,
  role: ConvertDemoArtifactRole,
): number {
  return PRODUCTION_MINICASE_ARTIFACTS.filter((artifact) => {
    if (artifact.role !== role) return false;
    const state = statuses[artifact.id];
    return (
      state?.kind === "ok" &&
      (!state.status.exists || state.status.kind === "missing")
    );
  }).length;
}

function artifactRoleLabel(role: ConvertDemoArtifactRole): string {
  return role === "starter" ? "starter" : "after convert";
}

function liveMinicaseCardClass(tone: ProductionMinicaseAvailabilityTone): string {
  if (tone === "ready") {
    return "border-emerald-300/20 bg-emerald-300/[0.05]";
  }
  if (tone === "missing") {
    return "border-amber-300/25 bg-amber-300/[0.06]";
  }
  if (tone === "error") {
    return "border-rose-300/25 bg-rose-300/[0.06]";
  }
  return "border-white/10 bg-white/[0.03]";
}

function LiveMinicaseToneBadge({
  tone,
}: {
  tone: ProductionMinicaseAvailabilityTone;
}) {
  const label = {
    loading: "checking",
    ready: "ready",
    missing: "missing",
    error: "attention",
  }[tone];
  const className = {
    loading: "border-white/10 bg-white/[0.04] text-[var(--fg-2)]",
    ready: "border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-200",
    missing: "border-amber-300/25 bg-amber-300/[0.08] text-amber-200",
    error: "border-rose-300/25 bg-rose-300/[0.08] text-rose-200",
  }[tone];
  return (
    <span
      className={
        "inline-flex rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] " +
        className
      }
    >
      {label}
    </span>
  );
}

function ArtifactStatusBadge({
  state,
}: {
  state: FileStatusState | undefined;
}) {
  if (state === undefined || state.kind === "loading") {
    return (
      <span className="inline-flex rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-2)]">
        checking
      </span>
    );
  }
  if (state.kind === "error") {
    return (
      <span
        className="inline-flex max-w-full rounded border border-amber-300/25 bg-amber-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-amber-200"
        title={state.message}
      >
        status unknown
      </span>
    );
  }

  const tone = fileStatusTone(state.status);
  const label = fileStatusLabel(state.status);
  if (tone === "ready") {
    return (
      <span className="inline-flex rounded border border-emerald-300/25 bg-emerald-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-emerald-200">
        {label}
      </span>
    );
  }
  if (tone === "missing") {
    return (
      <span
        className="inline-flex rounded border border-rose-300/25 bg-rose-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-rose-200"
        title={state.status.detail ?? undefined}
      >
        {label}
      </span>
    );
  }
  return (
    <span
      className="inline-flex rounded border border-amber-300/25 bg-amber-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-amber-200"
      title={state.status.detail ?? undefined}
    >
      {label}
    </span>
  );
}
