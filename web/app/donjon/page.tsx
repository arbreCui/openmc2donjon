"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import { ApiError, api, type BundleInspection } from "@/lib/api";
import {
  donjonBundleAsciiMismatch,
  donjonDeckChecklist,
  donjonDeckOptionsFromSearchParams,
  donjonDeckFilename,
  donjonDefaultsArtifact,
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  findDonjonBundleArtifact,
  donjonObjectLabel,
  donjonRunCommand,
  donjonShortName,
  inferDonjonFormat,
  placeholderAsciiPath,
  type DonjonBundleArtifact,
  type DonjonDeckBoundary,
  type DonjonDeckChecklistItem,
  type DonjonDeckGeometry,
  type DonjonDeckOptions,
  type DonjonDeckSolver,
  type DonjonGuideFormat,
} from "@/lib/donjonGuide";

type ManifestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | {
      kind: "ready";
      data: BundleInspection;
      artifact: DonjonBundleArtifact | null;
      summaryArtifact: DonjonBundleArtifact | null;
    }
  | { kind: "missing"; message: string }
  | { kind: "error"; message: string };

type BoundaryKey =
  | "xMinus"
  | "xPlus"
  | "yMinus"
  | "yPlus"
  | "zMinus"
  | "zPlus";

const BOUNDARY_FIELDS: Array<{
  key: BoundaryKey;
  label: string;
  dimension: "xy" | "z";
}> = [
  { key: "xMinus", label: "X-", dimension: "xy" },
  { key: "xPlus", label: "X+", dimension: "xy" },
  { key: "yMinus", label: "Y-", dimension: "xy" },
  { key: "yPlus", label: "Y+", dimension: "xy" },
  { key: "zMinus", label: "Z-", dimension: "z" },
  { key: "zPlus", label: "Z+", dimension: "z" },
];

export default function DonjonPage() {
  return (
    <Suspense fallback={<DonjonLoading />}>
      <DonjonPageContent />
    </Suspense>
  );
}

function DonjonLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading DONJON handoff guide…
        </section>
      </div>
    </main>
  );
}

function DonjonPageContent() {
  const searchParams = useSearchParams();
  const queryAscii = searchParams.get("ascii") ?? "";
  const queryFormat = searchParams.get("format");
  const queryManifest = searchParams.get("manifest") ?? "";
  const queryDeckFilename = searchParams.get("deck") ?? "";
  const queryMixtureCount = searchParams.get("nmix");
  const initialDeckOptions = donjonDeckOptionsFromSearchParams(searchParams);
  const initialFormat = inferDonjonFormat(queryAscii, queryFormat);
  const [asciiPath, setAsciiPath] = useState(queryAscii);
  const [asciiEdited, setAsciiEdited] = useState(Boolean(queryAscii.trim()));
  const [format, setFormat] = useState<DonjonGuideFormat>(initialFormat);
  const [manifestPath, setManifestPath] = useState(queryManifest);
  const [manifestState, setManifestState] = useState<ManifestState>({
    kind: "idle",
  });
  const [mixtureCount, setMixtureCount] = useState(initialDeckOptions.mixtureCount);
  const [mixtureCountEdited, setMixtureCountEdited] = useState(
    queryMixtureCount !== null,
  );
  const [geometry, setGeometry] = useState<DonjonDeckGeometry>(
    initialDeckOptions.geometry,
  );
  const [solver, setSolver] = useState<DonjonDeckSolver>(initialDeckOptions.solver);
  const [spnOrder, setSpnOrder] = useState(initialDeckOptions.spnOrder);
  const [snOrder, setSnOrder] = useState(initialDeckOptions.snOrder);
  const [hexSide, setHexSide] = useState(initialDeckOptions.hexSide);
  const [hexHeight, setHexHeight] = useState(initialDeckOptions.hexHeight);
  const [boundaries, setBoundaries] = useState({
    xMinus: initialDeckOptions.xMinus,
    xPlus: initialDeckOptions.xPlus,
    yMinus: initialDeckOptions.yMinus,
    yPlus: initialDeckOptions.yPlus,
    zMinus: initialDeckOptions.zMinus,
    zPlus: initialDeckOptions.zPlus,
  });
  const [solveDeckFilename, setSolveDeckFilename] = useState(
    queryDeckFilename.trim() ||
      donjonDeckFilename(queryAscii, initialFormat, "solve"),
  );
  const [deckFilenameEdited, setDeckFilenameEdited] = useState(
    Boolean(queryDeckFilename.trim()),
  );

  const deckOptions = useMemo<DonjonDeckOptions>(
    () => ({
      mixtureCount,
      geometry,
      solver,
      spnOrder,
      snOrder,
      hexSide,
      hexHeight,
      ...boundaries,
    }),
    [
      boundaries,
      geometry,
      hexHeight,
      hexSide,
      mixtureCount,
      snOrder,
      solver,
      spnOrder,
    ],
  );

  const objectLabel = donjonObjectLabel(format);
  const shortName = donjonShortName(format);
  const ingestSnippet = useMemo(
    () => donjonIngestSnippet(asciiPath, format, deckOptions),
    [asciiPath, deckOptions, format],
  );
  const dumpSnippet = useMemo(
    () => donjonIngestOnlySnippet(asciiPath, format),
    [asciiPath, format],
  );
  const ingestDeckFilename = useMemo(
    () => donjonDeckFilename(asciiPath, format, "ingest"),
    [asciiPath, format],
  );
  const selfHref = donjonGuideHref({
    asciiPath,
    format,
    manifestPath,
    deckFilename: solveDeckFilename,
    deckOptions,
  });
  const checklist = useMemo(
    () => donjonDeckChecklist(asciiPath, format, deckOptions),
    [asciiPath, deckOptions, format],
  );

  useEffect(() => {
    if (deckFilenameEdited) return;
    setSolveDeckFilename(donjonDeckFilename(asciiPath, format, "solve"));
  }, [asciiPath, deckFilenameEdited, format]);

  useEffect(() => {
    const trimmed = manifestPath.trim();
    if (!trimmed) {
      setManifestState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setManifestState({ kind: "loading" });
    api
      .inspectBundle(trimmed)
      .then((data) => {
        if (cancelled) return;
        setManifestState({
          kind: "ready",
          data,
          artifact: findDonjonBundleArtifact(data.artifacts),
          summaryArtifact: donjonDefaultsArtifact(data.donjon_defaults),
        });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setManifestState({
            kind: "missing",
            message: err.detail ?? `Bundle manifest was not found: ${trimmed}`,
          });
          return;
        }
        const message =
          err instanceof ApiError
            ? err.detail ?? err.message
            : err instanceof Error
              ? err.message
              : "Unknown bundle manifest error";
        setManifestState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [manifestPath]);

  useEffect(() => {
    if (manifestState.kind !== "ready") return;
    const preferredArtifact = manifestState.artifact ?? manifestState.summaryArtifact;
    if (!preferredArtifact) return;
    if (asciiEdited) return;
    setAsciiPath(preferredArtifact.asciiPath);
    setFormat(preferredArtifact.format);
  }, [asciiEdited, manifestState]);

  useEffect(() => {
    if (manifestState.kind !== "ready") return;
    if (mixtureCountEdited) return;
    const nextMixtureCount = manifestState.data.donjon_defaults?.mixture_count;
    if (typeof nextMixtureCount !== "number") return;
    setMixtureCount(nextMixtureCount);
  }, [manifestState, mixtureCountEdited]);

  function applyManifestArtifact(artifact: DonjonBundleArtifact) {
    setAsciiPath(artifact.asciiPath);
    setFormat(artifact.format);
    setAsciiEdited(true);
    if (!deckFilenameEdited) {
      setSolveDeckFilename(
        donjonDeckFilename(artifact.asciiPath, artifact.format, "solve"),
      );
    }
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--fg-3)]">
            DONJON consumption
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            <span className="grad-text">Use the ASCII handoff in DONJON</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            This page does not run DONJON. It turns the converter output path into
            the small deck fragments that DONJON users need: load the ASCII object,
            build or reuse a macrolib, then attach the case-specific geometry,
            tracking, and solver.
          </p>
        </header>

        <section className="glass rounded-xl p-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_220px]">
            <label className="block">
              <span className="text-sm font-semibold tracking-tight">
                ASCII handoff path
              </span>
              <input
                value={asciiPath}
                onChange={(event) => {
                  setAsciiPath(event.target.value);
                  setAsciiEdited(true);
                }}
                placeholder={placeholderAsciiPath(format)}
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)]"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold tracking-tight">Format</span>
              <select
                value={format}
                onChange={(event) => {
                  setFormat(event.target.value as DonjonGuideFormat);
                  setAsciiEdited(true);
                }}
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
              >
                <option value="multicompo">MULTICOMPO</option>
                <option value="macrolib">MACROLIB</option>
              </select>
            </label>
          </div>
          <label className="mt-3 block">
            <span className="text-sm font-semibold tracking-tight">
              Bundle manifest (optional)
            </span>
            <input
              value={manifestPath}
              onChange={(event) => setManifestPath(event.target.value)}
              placeholder="bundle/manifest.json"
              className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)]"
            />
          </label>
          <ManifestCasePanel
            state={manifestState}
            onUseArtifact={applyManifestArtifact}
            selectedAsciiPath={asciiPath}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <CopyCliButton value={selfHref} label="Copy page link" />
            <Link href="/convert" className="btn btn-secondary">
              Back to convert
            </Link>
            {manifestPath.trim() ? (
              <Link
                href={`/builder?command=validate-bundle&manifest=${encodeURIComponent(
                  manifestPath.trim(),
                )}`}
                className="btn btn-secondary"
              >
                Validate bundle
              </Link>
            ) : null}
          </div>
        </section>

        <section className="mt-5 grid gap-4 lg:grid-cols-3">
          <GuidanceCard
            eyebrow="object"
            title={objectLabel}
            body={
              format === "multicompo"
                ? "Use this when the converter wrote mapped domain-wise mixtures. DONJON typically reads it as CPO, then NCR extracts a MACROLIB for the geometry mixture map."
                : "Use this when the converter wrote a direct one-state macrolib. DONJON can assign the ASCII object directly to MACRO."
            }
          />
          <GuidanceCard
            eyebrow="mapping"
            title={
              format === "multicompo" ? "NCR builds MACRO" : "MACRO is direct"
            }
            body={
              format === "multicompo"
                ? "Your GEOM MIX numbers must correspond to the mixture indices you select in the NCR MIX lines."
                : "Your GEOM MIX numbers refer directly to the mixtures stored in the L_MACROLIB object."
            }
          />
          <GuidanceCard
            eyebrow="solver"
            title="Geometry stays case-specific"
            body="The generated skeleton deliberately keeps geometry and tracking minimal. Replace those blocks with the diffusion, SPN, or SN deck for the real case."
          />
        </section>

        <DeckBuilderPanel
          solveDeckFilename={solveDeckFilename}
          onSolveDeckFilenameChange={(value) => {
            setSolveDeckFilename(value);
            setDeckFilenameEdited(true);
          }}
          onResetSolveDeckFilename={() => {
            setSolveDeckFilename(donjonDeckFilename(asciiPath, format, "solve"));
            setDeckFilenameEdited(false);
          }}
          mixtureCount={mixtureCount}
          onMixtureCountChange={(value) => {
            setMixtureCount(value);
            setMixtureCountEdited(true);
          }}
          geometry={geometry}
          onGeometryChange={(value) => {
            setGeometry(value);
            if (value !== "hex" && solver === "snt") setSolver("diffusion");
          }}
          solver={solver}
          onSolverChange={setSolver}
          spnOrder={spnOrder}
          onSpnOrderChange={setSpnOrder}
          snOrder={snOrder}
          onSnOrderChange={setSnOrder}
          hexSide={hexSide}
          onHexSideChange={setHexSide}
          hexHeight={hexHeight}
          onHexHeightChange={setHexHeight}
          boundaries={boundaries}
          onBoundaryChange={(key, value) =>
            setBoundaries((current) => ({ ...current, [key]: value }))
          }
        />
        <DeckHandoffChecklist items={checklist} />

        <section className="mt-5 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <SnippetCard
            title={`${shortName} ingest smoke`}
            description="Use this tiny deck first when you only want to confirm that DONJON can read the ASCII file."
            code={dumpSnippet}
            downloadFilename={ingestDeckFilename}
            runCommand={donjonRunCommand(ingestDeckFilename)}
          />
          <SnippetCard
            title="Low-order solve skeleton"
            description="Use this as a starting point for a real DONJON deck; replace geometry, tracking, and solver details."
            code={ingestSnippet}
            downloadFilename={solveDeckFilename}
            runCommand={donjonRunCommand(solveDeckFilename)}
          />
        </section>

        <section className="mt-5 rounded-xl border border-[var(--edge)] bg-white/[0.02] p-4">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            production reminder
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            The converter does not define the core model by itself
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-[var(--fg-2)]">
            OpenMC supplies the homogenized cross sections. DONJON still needs
            the deterministic geometry, mixture assignment, tracking options,
            boundary conditions, and solver choice. For SPH workflows, generate
            factors upstream from OpenMC CE versus OpenMC MG with the same
            geometry, then deliver the corrected handoff to this DONJON deck.
          </p>
        </section>
      </div>
    </main>
  );
}

function ManifestCasePanel({
  state,
  selectedAsciiPath,
  onUseArtifact,
}: {
  state: ManifestState;
  selectedAsciiPath: string;
  onUseArtifact: (artifact: DonjonBundleArtifact) => void;
}) {
  if (state.kind === "idle") return null;
  if (state.kind === "loading") {
    return (
      <div className="mt-3 rounded-md border border-cyan-300/15 bg-cyan-300/5 px-3 py-2 text-[12px] text-cyan-100">
        Reading bundle manifest…
      </div>
    );
  }
  if (state.kind === "missing" || state.kind === "error") {
    return (
      <div className="mt-3 rounded-md border border-amber-300/25 bg-amber-300/10 px-3 py-2 text-[12px] text-amber-100">
        {state.message}
      </div>
    );
  }

  const artifact = state.artifact;
  const summaryArtifact = state.summaryArtifact;
  const mismatch = donjonBundleAsciiMismatch(artifact, summaryArtifact);
  const artifactCount = `${state.data.artifact_count} artifact${
    state.data.artifact_count === 1 ? "" : "s"
  }`;
  return (
    <div className="mt-3 rounded-md border border-current/15 bg-black/15 px-3 py-2 text-[12px]">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="font-semibold tracking-tight">Bundle manifest context</div>
        <span
          className={
            "rounded border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] " +
            (state.data.ok
              ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100"
              : "border-amber-300/25 bg-amber-300/10 text-amber-100")
          }
        >
          {state.data.decision}
        </span>
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-3">
        <ManifestStat label="manifest" value={state.data.manifest_path} />
        <ManifestStat label="artifacts" value={artifactCount} />
        <ManifestStat
          label="result"
          value={state.data.ok ? "ready to share" : "needs attention"}
        />
      </div>
      <ManifestDonjonDefaults defaults={state.data.donjon_defaults} />
      {mismatch ? (
        <div className="mt-2 rounded border border-amber-300/25 bg-amber-300/10 p-2 text-amber-100">
          <div className="text-[10px] uppercase tracking-[0.14em] text-amber-100/70">
            summary/artifact mismatch
          </div>
          <p className="mt-1 leading-5">
            The bundle contains one DONJON ASCII artifact, but the conversion
            summary points to a different output path. Use the bundled artifact
            for a self-contained package, or choose the summary output if you
            are working in the original run directory.
          </p>
          <div className="mt-1 grid gap-1 font-mono text-[11px] text-amber-100/80">
            <span className="truncate" title={mismatch.artifactPath}>
              artifact: {mismatch.artifactPath}
            </span>
            <span className="truncate" title={mismatch.summaryPath}>
              summary: {mismatch.summaryPath}
            </span>
          </div>
          {selectedAsciiPath.trim() === mismatch.summaryPath ? null : (
            <button
              type="button"
              className="btn btn-secondary mt-2 px-2 py-1 text-[11px]"
              onClick={() => summaryArtifact && onUseArtifact(summaryArtifact)}
            >
              Use summary output
            </button>
          )}
        </div>
      ) : null}
      {artifact ? (
        <div className="mt-2 rounded border border-emerald-300/15 bg-emerald-300/5 p-2">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-100/70">
                detected DONJON ASCII
              </div>
              <div className="mt-1 truncate font-mono text-[11px]" title={artifact.asciiPath}>
                {artifact.asciiPath}
              </div>
              <div className="mt-1 text-[var(--fg-2)]">
                label <span className="font-mono">{artifact.label}</span> ·{" "}
                {donjonObjectLabel(artifact.format)}
                {artifact.ok === false ? " · manifest reports artifact issues" : ""}
              </div>
            </div>
            {selectedAsciiPath.trim() === artifact.asciiPath ? null : (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onUseArtifact(artifact)}
              >
                Use this output
              </button>
            )}
          </div>
        </div>
      ) : summaryArtifact ? (
        <div className="mt-2 rounded border border-cyan-300/15 bg-cyan-300/5 p-2">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-100/70">
                output from conversion summary
              </div>
              <div
                className="mt-1 truncate font-mono text-[11px]"
                title={summaryArtifact.asciiPath}
              >
                {summaryArtifact.asciiPath}
              </div>
              <div className="mt-1 text-cyan-100/70">
                {donjonObjectLabel(summaryArtifact.format)} · not listed as a
                bundle artifact
              </div>
            </div>
            {selectedAsciiPath.trim() === summaryArtifact.asciiPath ? null : (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => onUseArtifact(summaryArtifact)}
              >
                Use summary output
              </button>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-2 text-[var(--fg-2)]">
          Manifest loaded, but no <span className="font-mono">mcompo</span> or{" "}
          <span className="font-mono">macrolib</span> artifact or conversion
          summary output was found. Keep the ASCII path above explicit.
        </p>
      )}
    </div>
  );
}

function ManifestDonjonDefaults({
  defaults,
}: {
  defaults: BundleInspection["donjon_defaults"];
}) {
  if (!defaults) return null;
  const hasSummaryContext =
    defaults.ascii_path ||
    defaults.summary_path ||
    defaults.format ||
    defaults.mixture_count != null ||
    defaults.preflight_decision ||
    defaults.ok != null ||
    defaults.preflight_ok != null ||
    defaults.production_requested != null;
  if (!hasSummaryContext) return null;
  return (
    <div className="mt-2 rounded border border-cyan-300/15 bg-cyan-300/5 p-2 text-[11px] text-cyan-100">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-100/70">
            conversion summary
          </div>
          <div className="mt-1 font-semibold tracking-tight">
            DONJON inputs inferred from convert_summary.json
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <SummaryPill tone={defaults.ok === false ? "bad" : "good"}>
            {conversionStateLabel(defaults)}
          </SummaryPill>
          <SummaryPill tone={defaults.production_requested ? "good" : "neutral"}>
            {defaults.production_requested ? "production gates" : "standard run"}
          </SummaryPill>
          <SummaryPill tone={defaults.preflight_ok === false ? "bad" : "good"}>
            {preflightStateLabel(defaults)}
          </SummaryPill>
        </div>
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-2">
        <SummaryFact
          label="ASCII output"
          value={defaults.ascii_path ?? "not recorded"}
        />
        <SummaryFact
          label="format"
          value={defaults.format ? donjonObjectLabel(defaults.format) : "not recorded"}
        />
        <SummaryFact
          label="mixtures"
          value={
            defaults.mixture_count != null
              ? `NMIX ${defaults.mixture_count}`
              : "not recorded"
          }
        />
        <SummaryFact
          label="preflight decision"
          value={defaults.preflight_decision ?? "not recorded"}
        />
      </div>
      {defaults.summary_path ? (
        <div className="mt-2 truncate text-cyan-100/70" title={defaults.summary_path}>
          source <span className="font-mono">{defaults.summary_path}</span>
        </div>
      ) : null}
    </div>
  );
}

function SummaryPill({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "good" | "bad" | "neutral";
}) {
  const toneClass =
    tone === "good"
      ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100"
      : tone === "bad"
        ? "border-rose-300/25 bg-rose-300/10 text-rose-100"
        : "border-cyan-300/20 bg-cyan-300/10 text-cyan-100";
  return (
    <span className={"rounded border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] " + toneClass}>
      {children}
    </span>
  );
}

function SummaryFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-cyan-300/10 bg-black/10 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-100/55">
        {label}
      </div>
      <div className="mt-0.5 truncate font-mono text-[11px]" title={value}>
        {value}
      </div>
    </div>
  );
}

function conversionStateLabel(defaults: BundleInspection["donjon_defaults"]) {
  if (!defaults) return "summary unknown";
  if (defaults.dry_run) return "dry-run only";
  if (defaults.converted) return "converted";
  if (defaults.ok === false) return "conversion failed";
  return "summary loaded";
}

function preflightStateLabel(defaults: BundleInspection["donjon_defaults"]) {
  if (!defaults) return "preflight unknown";
  if (defaults.preflight_ok === true) return "preflight pass";
  if (defaults.preflight_ok === false) return "preflight fail";
  return "preflight n/a";
}

function ManifestStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-current/10 bg-black/10 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-60">
        {label}
      </div>
      <div className="mt-0.5 truncate font-mono text-[11px]" title={value}>
        {value}
      </div>
    </div>
  );
}

function DeckBuilderPanel({
  solveDeckFilename,
  onSolveDeckFilenameChange,
  onResetSolveDeckFilename,
  mixtureCount,
  onMixtureCountChange,
  geometry,
  onGeometryChange,
  solver,
  onSolverChange,
  spnOrder,
  onSpnOrderChange,
  snOrder,
  onSnOrderChange,
  hexSide,
  onHexSideChange,
  hexHeight,
  onHexHeightChange,
  boundaries,
  onBoundaryChange,
}: {
  solveDeckFilename: string;
  onSolveDeckFilenameChange: (value: string) => void;
  onResetSolveDeckFilename: () => void;
  mixtureCount: number;
  onMixtureCountChange: (value: number) => void;
  geometry: DonjonDeckGeometry;
  onGeometryChange: (value: DonjonDeckGeometry) => void;
  solver: DonjonDeckSolver;
  onSolverChange: (value: DonjonDeckSolver) => void;
  spnOrder: number;
  onSpnOrderChange: (value: number) => void;
  snOrder: number;
  onSnOrderChange: (value: number) => void;
  hexSide: number;
  onHexSideChange: (value: number) => void;
  hexHeight: number;
  onHexHeightChange: (value: number) => void;
  boundaries: Pick<
    DonjonDeckOptions,
    "xMinus" | "xPlus" | "yMinus" | "yPlus" | "zMinus" | "zPlus"
  >;
  onBoundaryChange: (key: BoundaryKey, value: DonjonDeckBoundary) => void;
}) {
  const visibleBoundaries = BOUNDARY_FIELDS.filter(
    (field) => geometry === "car3d" || field.dimension === "xy",
  );

  return (
    <section className="mt-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            deck builder
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            Shape the low-order skeleton before copying it
          </h2>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            {geometry === "hex"
              ? "These controls generate the skeleton below. The HEXZ block assigns one mixture per hex position in multicompo order; set SIDE and the axial height to the real lattice."
              : "These controls generate the skeleton below. The geometry is still a one-cell smoke model; replace its mesh and mixture map with the real DONJON core deck."}
          </p>
        </div>
        <span className="rounded border border-cyan-300/20 bg-cyan-300/10 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-cyan-100">
          local template
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[1.5fr_repeat(4,minmax(0,1fr))]">
        <label className="block">
          <span className="text-[12px] font-semibold tracking-tight">
            Solve deck filename
          </span>
          <div className="mt-2 flex gap-2">
            <input
              value={solveDeckFilename}
              onChange={(event) => onSolveDeckFilenameChange(event.target.value)}
              className="min-w-0 flex-1 rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)]"
            />
            <button
              type="button"
              onClick={onResetSolveDeckFilename}
              className="btn btn-secondary px-2 py-1 text-[11px]"
            >
              Reset
            </button>
          </div>
        </label>
        <label className="block">
          <span className="text-[12px] font-semibold tracking-tight">
            Mixtures to extract
          </span>
          <input
            type="number"
            min={1}
            max={999}
            step={1}
            value={mixtureCount}
            onChange={(event) =>
              onMixtureCountChange(Number(event.target.value))
            }
            className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
          />
        </label>
        <label className="block">
          <span className="text-[12px] font-semibold tracking-tight">
            Geometry primitive
          </span>
          <select
            value={geometry}
            onChange={(event) =>
              onGeometryChange(event.target.value as DonjonDeckGeometry)
            }
            className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
          >
            <option value="car2d">CAR2D smoke</option>
            <option value="car3d">CAR3D smoke</option>
            <option value="hex">HEXZ core</option>
          </select>
        </label>
        <label className="block">
          <span className="text-[12px] font-semibold tracking-tight">
            Solver/tracking
          </span>
          <select
            value={solver}
            onChange={(event) =>
              onSolverChange(event.target.value as DonjonDeckSolver)
            }
            className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
          >
            <option value="diffusion">Diffusion</option>
            <option value="spn">SPN</option>
            <option value="snt" disabled={geometry !== "hex"}>
              SNT (hex only)
            </option>
          </select>
        </label>
        <label className="block">
          <span className="text-[12px] font-semibold tracking-tight">
            SPN order
          </span>
          <select
            value={spnOrder}
            disabled={solver !== "spn"}
            onChange={(event) => onSpnOrderChange(Number(event.target.value))}
            className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)] disabled:cursor-not-allowed disabled:opacity-45"
          >
            <option value={3}>SPN 3</option>
            <option value={5}>SPN 5</option>
          </select>
        </label>
      </div>

      {geometry === "hex" ? (
        <div className="mt-3 grid gap-3 lg:grid-cols-3">
          <label className="block">
            <span className="text-[12px] font-semibold tracking-tight">
              SN order
            </span>
            <select
              value={snOrder}
              disabled={solver !== "snt"}
              onChange={(event) => onSnOrderChange(Number(event.target.value))}
              className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)] disabled:cursor-not-allowed disabled:opacity-45"
            >
              <option value={4}>SN 4</option>
              <option value={8}>SN 8</option>
              <option value={16}>SN 16</option>
            </select>
            <span className="mt-1 block text-[11px] text-[var(--fg-3)]">
              Discrete-ordinates order for SNT; SN 8 is the validated setting.
            </span>
          </label>
          <label className="block">
            <span className="text-[12px] font-semibold tracking-tight">
              Hex side (cm)
            </span>
            <input
              type="number"
              min={0.0001}
              step={0.0001}
              value={hexSide}
              onChange={(event) => onHexSideChange(Number(event.target.value))}
              className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
            />
            <span className="mt-1 block text-[11px] text-[var(--fg-3)]">
              SIDE — the hexagon edge length in cm.
            </span>
          </label>
          <label className="block">
            <span className="text-[12px] font-semibold tracking-tight">
              Axial height (cm)
            </span>
            <input
              type="number"
              min={0.0001}
              step={0.1}
              value={hexHeight}
              onChange={(event) => onHexHeightChange(Number(event.target.value))}
              className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
            />
            <span className="mt-1 block text-[11px] text-[var(--fg-3)]">
              MESHZ upper bound for the single z-plane.
            </span>
          </label>
        </div>
      ) : null}

      {geometry === "hex" ? (
        <p className="mt-3 text-[12px] leading-5 text-[var(--fg-2)]">
          Hexagonal boundaries are fixed: Z- REFL Z+ REFL with HBC COMPLETE
          VOID — the only outer boundary validated for full-hex SNT decks.
        </p>
      ) : (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
          {visibleBoundaries.map((field) => (
            <label key={field.key} className="block">
              <span className="text-[11px] font-semibold tracking-tight text-[var(--fg-2)]">
                {field.label}
              </span>
              <select
                value={boundaries[field.key]}
                onChange={(event) =>
                  onBoundaryChange(field.key, event.target.value as DonjonDeckBoundary)
                }
                className="mt-1.5 w-full rounded-md border border-[var(--edge)] bg-black/20 px-2 py-1.5 text-[12px] text-[var(--fg-0)]"
              >
                <option value="REFL">REFL</option>
                <option value="VOID">VOID</option>
              </select>
            </label>
          ))}
        </div>
      )}
    </section>
  );
}

function DeckHandoffChecklist({ items }: { items: DonjonDeckChecklistItem[] }) {
  return (
    <section className="mt-5 rounded-xl border border-[var(--edge)] bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            handoff checklist
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            Before running the downloaded deck
          </h2>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            The generated deck is a DONJON smoke and starter skeleton. These are
            the production checks to make before treating the result as a real
            low-order calculation.
          </p>
        </div>
        <span className="rounded border border-amber-300/20 bg-amber-300/10 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-amber-100">
          review before physics
        </span>
      </div>
      <div className="mt-4 grid gap-2 lg:grid-cols-5">
        {items.map((item, index) => (
          <article
            key={item.id}
            className="rounded-lg border border-[var(--edge)] bg-black/15 p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                step {index + 1}
              </span>
              <ChecklistBadge tone={item.tone} />
            </div>
            <h3 className="mt-2 text-[13px] font-semibold tracking-tight">
              {item.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {item.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function ChecklistBadge({ tone }: { tone: DonjonDeckChecklistItem["tone"] }) {
  const label =
    tone === "ready" ? "filled" : tone === "review" ? "check" : "manual";
  const className =
    tone === "ready"
      ? "border-emerald-300/20 bg-emerald-300/10 text-emerald-100"
      : tone === "review"
        ? "border-cyan-300/20 bg-cyan-300/10 text-cyan-100"
        : "border-amber-300/20 bg-amber-300/10 text-amber-100";
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] ${className}`}
    >
      {label}
    </span>
  );
}

function GuidanceCard({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-black/15 p-4">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {eyebrow}
      </div>
      <h2 className="mt-1 text-sm font-semibold tracking-tight">{title}</h2>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
    </article>
  );
}

function SnippetCard({
  title,
  description,
  code,
  downloadFilename,
  runCommand,
}: {
  title: string;
  description: string;
  code: string;
  downloadFilename?: string;
  runCommand?: string;
}) {
  const downloadHref = `data:text/plain;charset=utf-8,${encodeURIComponent(code)}`;
  return (
    <article className="rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            {description}
          </p>
          {downloadFilename ? (
            <p className="mt-1 text-[11px] text-[var(--fg-3)]">
              Suggested file:{" "}
              <span className="font-mono text-[var(--fg-2)]">
                {downloadFilename}
              </span>
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <CopyCliButton value={code} label="Copy deck" compact />
          {downloadFilename ? (
            <a
              href={downloadHref}
              download={downloadFilename}
              className="btn btn-secondary px-2 py-1 text-[11px]"
            >
              Download .x2m
            </a>
          ) : null}
          {runCommand ? (
            <CopyCliButton
              value={runCommand}
              label="Copy run command"
              ariaLabel={`Copy DONJON run command for ${title}`}
              compact
            />
          ) : null}
        </div>
      </div>
      <pre className="mt-3 max-h-[460px] overflow-auto rounded-lg border border-[var(--edge)] bg-black/30 p-3 text-[12px] leading-5 text-[var(--fg-1)]">
        {code}
      </pre>
    </article>
  );
}
