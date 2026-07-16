"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import EvidenceLadder from "@/components/EvidenceLadder";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import { ApiError, api, type BundleInspection, type ExecutionJob, type ProjectStatus } from "@/lib/api";
import { containingDirectory } from "@/lib/outputBrowse";
import { useSettings } from "@/lib/settings";
import { donjonEvidenceLadder } from "@/lib/evidenceLadder";
import {
  deckNumberParam,
  donjonBundleAsciiMismatch,
  donjonDeckChecklist,
  donjonDeckOptionsFromSearchParams,
  donjonDeckFilename,
  donjonDefaultsArtifact,
  donjonGuideFacts,
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  findDonjonBundleArtifact,
  donjonObjectLabel,
  donjonRunCommand,
  donjonShortName,
  donjonWebRunPlan,
  inferDonjonFormat,
  IRENA30_COLORSET_CPO_COMPONENTS,
  IRENA30_LEGACY_DECK_STATUS,
  irena30CpoPreviewIssue,
  irena30ColorsetFullCoreSnippet,
  isWithdrawnIrenaDonjonMode,
  placeholderAsciiPath,
  type DonjonBundleArtifact,
  type DonjonDeckChecklistItem,
  type DonjonDeckGeometry,
  type DonjonDeckOptions,
  type DonjonDeckSolver,
  type DonjonGuideFormat,
  type Irena30ColorsetCpoPaths,
  type Irena30CoreSolver,
} from "@/lib/donjonGuide";
import { FormStep, WorkflowPageHeader } from "@/components/ui/Workflow";
import { colorsetDefinition } from "@/lib/colorsetWorkflow";
import {
  colorsetProjectPaths,
  projectComponentConvertHref,
  projectConsumerHref,
  projectNativeSphEntryHrefs,
  projectPath,
  projectRootFromSearchParams,
} from "@/lib/projectWorkspace";

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

type DonjonRunState =
  | { kind: "idle" }
  | { kind: "starting"; label: string }
  | { kind: "job"; label: string; data: ExecutionJob }
  | { kind: "error"; message: string };

type CpoPathKey = keyof Irena30ColorsetCpoPaths;
type BrowserTarget = CpoPathKey | "single" | null;

const EMPTY_COLORSET_CPO_PATHS: Irena30ColorsetCpoPaths = {
  int: "",
  ext: "",
  csd: "",
  dsdf: "",
  pnl: "",
};

function projectCpoPaths(projectRoot: string): Irena30ColorsetCpoPaths {
  if (!projectRoot) return EMPTY_COLORSET_CPO_PATHS;
  return {
    int: colorsetProjectPaths(projectRoot, colorsetDefinition("int_ext")).cpo,
    ext: colorsetProjectPaths(projectRoot, colorsetDefinition("ext_int")).cpo,
    csd: colorsetProjectPaths(projectRoot, colorsetDefinition("csd_int")).cpo,
    dsdf: colorsetProjectPaths(projectRoot, colorsetDefinition("dsdf_int")).cpo,
    pnl: colorsetProjectPaths(projectRoot, colorsetDefinition("pnl_ext")).cpo,
  };
}

export default function DonjonPage() {
  return (
    <Suspense fallback={<DonjonLoading />}>
      <DonjonPageContent />
    </Suspense>
  );
}

function DonjonLoading() {
  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading DONJON guide…
        </section>
      </div>
    </main>
  );
}

function DonjonPageContent() {
  const searchParams = useSearchParams();
  const projectRoot = projectRootFromSearchParams(searchParams);
  const componentId = searchParams.get("component");
  const queryReceipt = searchParams.get("receipt") ?? "";
  const queryPhysicsSummary = searchParams.get("physics_summary") ?? "";
  const mode = searchParams.get("mode");
  const strictIrenaMode = mode === "irena30-fullcore";
  const irenaMode = isWithdrawnIrenaDonjonMode(mode);
  const queryAscii = searchParams.get("ascii") ?? "";
  const queryFormat = searchParams.get("format");
  const queryManifest = searchParams.get("manifest") ?? "";
  const queryDeckFilename = searchParams.get("deck") ?? "";
  const queryMixtureCount = searchParams.get("nmix");
  const initialDeckOptions = useMemo(
    () => donjonDeckOptionsFromSearchParams(searchParams),
    [searchParams],
  );
  const initialFormat = inferDonjonFormat(queryAscii, queryFormat);
  const [asciiPath, setAsciiPath] = useState(queryAscii);
  const [asciiEdited, setAsciiEdited] = useState(Boolean(queryAscii.trim()));
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget>(null);
  const [settings] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const [format, setFormat] = useState<DonjonGuideFormat>(initialFormat);
  const [manifestPath, setManifestPath] = useState(queryManifest);
  const [manifestState, setManifestState] = useState<ManifestState>({
    kind: "idle",
  });
  const [runState, setRunState] = useState<DonjonRunState>({ kind: "idle" });
  const [colorsetCpoPaths, setColorsetCpoPaths] =
    useState<Irena30ColorsetCpoPaths>(() => projectCpoPaths(projectRoot));
  const [projectStatus, setProjectStatus] = useState<ProjectStatus | null>(null);
  const [selectedProjectComponentId, setSelectedProjectComponentId] = useState(
    componentId ?? "",
  );
  const [coreSolver, setCoreSolver] = useState<Irena30CoreSolver>(
    initialDeckOptions.solver === "spn" ? "spn" : "snt",
  );
  // Numeric fields keep the raw text the user typed; ``deckNumberParam``
  // + ``normalizeDonjonDeckOptions`` turn it into the effective value in
  // ONE place, so the checklist and the generated deck always agree with
  // the field (an emptied field shows the placeholder default, not 0).
  const [mixtureCountText, setMixtureCountText] = useState(
    String(initialDeckOptions.mixtureCount),
  );
  const [mixtureCountEdited, setMixtureCountEdited] = useState(
    queryMixtureCount !== null,
  );
  const [geometry, setGeometry] = useState<DonjonDeckGeometry>(
    initialDeckOptions.geometry,
  );
  const [solver, setSolver] = useState<DonjonDeckSolver>(initialDeckOptions.solver);
  const [spnOrder, setSpnOrder] = useState(initialDeckOptions.spnOrder);
  const [snOrder, setSnOrder] = useState(initialDeckOptions.snOrder);
  const [hexSideText, setHexSideText] = useState(String(initialDeckOptions.hexSide));
  const [hexHeightText, setHexHeightText] = useState(
    String(initialDeckOptions.hexHeight),
  );
  // Boundary conditions are no longer editable on the page: the smoke
  // cell ships the fixed validated default. Deep-link parameters
  // (xm/xp/ym/yp/zm/zp) are still honored so shared guide URLs keep
  // reproducing the same deck.
  const boundaries = useMemo(
    () => ({
      xMinus: initialDeckOptions.xMinus,
      xPlus: initialDeckOptions.xPlus,
      yMinus: initialDeckOptions.yMinus,
      yPlus: initialDeckOptions.yPlus,
      zMinus: initialDeckOptions.zMinus,
      zPlus: initialDeckOptions.zPlus,
    }),
    [initialDeckOptions],
  );
  // The solve deck filename is auto-derived from the ASCII path; a
  // ``deck=`` deep-link parameter (e.g. from the convert page) still
  // overrides it so shared links keep their filename.
  const solveDeckFilename = useMemo(
    () =>
      queryDeckFilename.trim() ||
      donjonDeckFilename(asciiPath, format, "solve"),
    [asciiPath, format, queryDeckFilename],
  );

  const deckOptions = useMemo<Partial<DonjonDeckOptions>>(
    () => ({
      mixtureCount: deckNumberParam(mixtureCountText),
      geometry,
      solver,
      spnOrder,
      snOrder,
      hexSide: deckNumberParam(hexSideText),
      hexHeight: deckNumberParam(hexHeightText),
      ...boundaries,
    }),
    [
      boundaries,
      geometry,
      hexHeightText,
      hexSideText,
      mixtureCountText,
      snOrder,
      solver,
      spnOrder,
    ],
  );

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
  // "Copy page link" must yield a full URL, not a relative path;
  // ``window`` is only readable after mount (this page is also
  // server-rendered), so pick the origin up in an effect.
  const [origin, setOrigin] = useState("");
  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);
  useEffect(() => {
    if (!projectRoot) {
      setProjectStatus(null);
      return;
    }
    let cancelled = false;
    api
      .projectStatus(projectRoot)
      .then((data) => {
        if (cancelled) return;
        setProjectStatus(data);
        const selected =
          data.components.find((item) => item.id === selectedProjectComponentId) ??
          data.components.find((item) => item.output.state === "accepted") ??
          data.components[0];
        if (selected) {
          setSelectedProjectComponentId(selected.id);
          if (!asciiEdited) {
            setAsciiPath(selected.paths.output);
            setFormat(selected.format);
          }
        }
      })
      .catch(() => {
        if (!cancelled) setProjectStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [asciiEdited, projectRoot, runState, selectedProjectComponentId]);

  const selectedProjectComponent = projectStatus?.components.find(
    (item) => item.id === selectedProjectComponentId,
  ) ?? null;
  const selectedReceipt = queryReceipt || selectedProjectComponent?.paths.receipt || "";
  const selectedPhysicsSummary =
    queryPhysicsSummary || selectedProjectComponent?.paths.physics_summary || "";

  function selectProjectComponent(id: string) {
    setSelectedProjectComponentId(id);
    const selected = projectStatus?.components.find((item) => item.id === id);
    if (!selected) return;
    setAsciiPath(selected.paths.output);
    setFormat(selected.format);
    setAsciiEdited(true);
    setRunState({ kind: "idle" });
  }
  const checklist = useMemo(
    () => donjonDeckChecklist(asciiPath, format, deckOptions),
    [asciiPath, deckOptions, format],
  );
  const colorsetCoreDeck = useMemo(
    () => irena30ColorsetFullCoreSnippet(colorsetCpoPaths, coreSolver),
    [colorsetCpoPaths, coreSolver],
  );
  const browseSeed =
    browserTarget === "single"
      ? asciiPath
      : browserTarget
        ? colorsetCpoPaths[browserTarget]
        : "";

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
    setMixtureCountText(String(nextMixtureCount));
  }, [manifestState, mixtureCountEdited]);

  useEffect(() => {
    if (runState.kind !== "job") return;
    if (runState.data.status !== "queued" && runState.data.status !== "running") return;
    const timer = window.setTimeout(() => {
      api
        .executionJob(runState.data.job_id)
        .then((data) => setRunState({ kind: "job", label: runState.label, data }))
        .catch((error) =>
          setRunState({
            kind: "error",
            message:
              error instanceof ApiError
                ? error.detail ?? error.message
                : error instanceof Error
                  ? error.message
                  : "Could not poll DONJON job",
          }),
        );
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [runState]);

  async function startDonjonRun(
    label: string,
    purpose: "ingest" | "solve",
    deckFilename: string,
    expectKEffective: boolean,
  ) {
    setRunState({ kind: "starting", label });
    try {
      const run = donjonWebRunPlan({
        asciiPath,
        format,
        purpose,
        deckOptions,
      });
      const data = await api.executeDonjon({
        deck_text: run.deckText,
        deck_filename: deckFilename,
        input_files: run.inputFiles,
        artifact_directory: projectRoot ? projectPath(projectRoot, "core") : undefined,
        project_root: projectRoot || undefined,
        component_id: projectRoot && selectedProjectComponentId
          ? selectedProjectComponentId
          : undefined,
        timeout_seconds: 1800,
        expect_k_effective: expectKEffective,
      });
      setRunState({ kind: "job", label, data });
    } catch (error) {
      setRunState({
        kind: "error",
        message:
          error instanceof ApiError
            ? error.detail ?? error.message
            : error instanceof Error
              ? error.message
              : "DONJON could not start",
      });
    }
  }

  function applyManifestArtifact(artifact: DonjonBundleArtifact) {
    setAsciiPath(artifact.asciiPath);
    setFormat(artifact.format);
    setAsciiEdited(true);
  }

  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <WorkflowPageHeader
          step="Consumer"
          eyebrow="DONJON consumption"
          title={strictIrenaMode ? "IRENA-30 strict full-core acceptance" : irenaMode ? "IRENA-30 legacy five-CPO deck (withdrawn)" : "Connect the checked handoff to your DONJON model"}
          description={strictIrenaMode ? "The current physical candidate preserves all 91 fine-reference positions and uses either 91 independent coarse domains or 21 exact D3 orbits pooled during OpenMC transport. It remains on HOLD until native SPH, leakage, keff, and 91-position power gates all pass." : irenaMode ? "Historical deck preview only. Reusing five center-domain CPOs over 91 positions does not establish a position-resolved full-core equivalence result, so this route cannot be executed from the product." : "Choose a Converter object or a native-SPH-corrected MACROLIB, then adapt the ingest and solve skeleton to the geometry, mixture map, SN/SPN method, and boundary conditions of your own model."}
          input={strictIrenaMode ? "91-position OpenMC reference + Converter object + exact coarse-domain declaration" : irenaMode ? "Historical INT, EXT, CSD, DSDF, and PNL CPO paths" : "One or more project-defined Converter or native-SPH outputs"}
          output={strictIrenaMode ? "HOLD until full-core physical acceptance passes" : irenaMode ? `${IRENA30_LEGACY_DECK_STATUS} .x2m preview` : "User-defined DRAGON/DONJON result"}
          actions={
            <Link
              href={strictIrenaMode ? (projectRoot ? `/projects?project=${encodeURIComponent(projectRoot)}` : "/projects") : irenaMode ? "/donjon?mode=irena30-fullcore" : (projectRoot ? `/convert?project=${encodeURIComponent(projectRoot)}` : "/convert")}
              className="btn btn-secondary"
            >
              {strictIrenaMode ? "Open project" : irenaMode ? "Open current IRENA route" : "Back to Converter"}
            </Link>
          }
        />

        {strictIrenaMode ? (
          <IrenaStrictFullCorePanel
            projectStatus={projectStatus}
            projectRoot={projectRoot}
          />
        ) : irenaMode ? <IrenaColorsetCorePanel
          paths={colorsetCpoPaths}
          onPathChange={(key, value) =>
            setColorsetCpoPaths((current) => ({ ...current, [key]: value }))
          }
          onBrowse={setBrowserTarget}
          solver={coreSolver}
          onSolverChange={setCoreSolver}
          deck={colorsetCoreDeck}
        /> : <GenericConsumerPanel
          projectStatus={projectStatus}
          projectRoot={projectRoot}
          selectedComponentId={selectedProjectComponentId}
          onSelectComponent={selectProjectComponent}
        />}

        <details className="mt-6 rounded-xl border border-[var(--edge)] bg-black/10 p-3" open={!irenaMode && !strictIrenaMode}>
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
            {irenaMode || strictIrenaMode ? "Generic tools: single-object ingest and deck builder" : "Single-object ingest and generic deck builder"}
          </summary>
          <div className="mt-4">
        <FormStep
          number="A"
          title={irenaMode || strictIrenaMode ? "Generic: inspect one ASCII object" : "Select one checked handoff object"}
          description={strictIrenaMode ? "This optional smoke-test is not the strict IRENA full-core solver or acceptance validator." : irenaMode ? "Use this separate diagnostic path to smoke-test one CPO or MACROLIB. It is independent of the withdrawn IRENA deck preview above." : "Smoke-test one Converter or native-SPH output and use the generated skeleton as the starting point for your own consumer model."}
          className="surface"
        >
          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="block">
              <span className="text-sm font-semibold tracking-tight">
                DONJON ASCII path
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
            <button
              type="button"
              onClick={() => setBrowserTarget("single")}
              className="btn btn-secondary"
            >
              Browse ASCII
            </button>
          </div>
          <div className="mt-3 rounded-md border border-emerald-300/20 bg-emerald-300/[0.06] px-3 py-2 text-[12px] text-emerald-100">
            Current preset · {donjonObjectLabel(format)} · NMIX {mixtureCountText || "—"} · {geometry === "hex" ? "HEXZ" : geometry.toUpperCase()} · {solver === "snt" ? "SN" : solver === "spn" ? "SPN" : "DIFFUSION"}
          </div>
          {selectedProjectComponent ? (
            <div className="mt-3 rounded-md border border-cyan-300/20 bg-cyan-300/[0.05] px-3 py-2 text-[11px] leading-5 text-cyan-100">
              Bound to Project component <strong>{selectedProjectComponent.label}</strong>
              {` (${selectedProjectComponent.id})`} · output {selectedProjectComponent.output.state}
              <code className="mt-1 block break-all text-[10px] text-cyan-100/70">
                Converter receipt: {selectedReceipt || "not declared"}
              </code>
              {selectedPhysicsSummary ? (
                <code className="mt-1 block break-all text-[10px] text-cyan-100/70">
                  SPH physics summary: {selectedPhysicsSummary}
                </code>
              ) : null}
            </div>
          ) : null}
          <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
            <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
              Advanced input format, bundle, and share link
            </summary>
            <label className="mt-3 block">
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
              <CopyCliButton value={`${origin}${selfHref}`} label="Copy page link" />
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
          </details>
        </FormStep>

        <FileBrowserModal
          open={browserTarget !== null}
          initialPath={containingDirectory(browseSeed.trim() || savedPrefix || "~")}
          extensions={["txt", "mcompo", "macrolib"]}
          fileTypeLabel="DONJON ASCII"
          chipLabel="ASCII"
          recentScope="donjon-ascii"
          onClose={() => setBrowserTarget(null)}
          onSelect={(picked) => {
            if (browserTarget === "single") {
              setAsciiPath(picked);
              setAsciiEdited(true);
            } else if (browserTarget) {
              setColorsetCpoPaths((current) => ({
                ...current,
                [browserTarget]: picked,
              }));
            }
            setBrowserTarget(null);
          }}
        />

        <details className="mt-5 rounded-xl border border-[var(--edge)] bg-white/[0.02] p-4">
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
            What DONJON receives from this object
          </summary>
          <dl className="grid gap-2">
            {donjonGuideFacts(format).map((fact) => (
              <div
                key={fact.id}
                className="flex flex-col gap-0.5 sm:flex-row sm:gap-3"
              >
                <dt className="w-20 shrink-0 pt-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                  {fact.label}
                </dt>
                <dd className="text-[12px] leading-5 text-[var(--fg-2)]">
                  {fact.body}
                </dd>
              </div>
            ))}
          </dl>
        </details>

        <details className="mt-5 rounded-xl border border-[var(--edge)] bg-black/10 p-3">
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
            Advanced generic geometry and solver settings
          </summary>
        <DeckBuilderPanel
          mixtureCount={mixtureCountText}
          onMixtureCountChange={(value) => {
            setMixtureCountText(value);
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
          hexSide={hexSideText}
          onHexSideChange={setHexSideText}
          hexHeight={hexHeightText}
          onHexHeightChange={setHexHeightText}
          boundaries={boundaries}
        />
        </details>
        <details className="mt-5 rounded-xl border border-[var(--edge)] bg-black/10 p-3">
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
            Review the generic single-object checks
          </summary>
          <DeckChecklist items={checklist} />
        </details>

        <details className="mt-5 rounded-xl border border-[var(--edge)] bg-black/10 p-3">
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
            Optional: review or download the generated .x2m decks
          </summary>
          <div className="mt-3 grid gap-4">
          <SnippetCard
            title={`${shortName} ingest smoke`}
            description="This tiny deck is what the in-app ingest smoke runs to confirm that DONJON can read the ASCII object."
            code={dumpSnippet}
            downloadFilename={ingestDeckFilename}
            runCommand={donjonRunCommand(ingestDeckFilename)}
            ready={asciiPath.trim().length > 0}
          />
          <details className="rounded-xl border border-[var(--edge)] bg-black/10 p-3">
            <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
              After ingest succeeds: open the low-order solve skeleton
            </summary>
          <SnippetCard
            title="Low-order solve skeleton"
            description="Use this as a starting point for a real DONJON deck; replace geometry, tracking, and solver details."
            code={ingestSnippet}
            downloadFilename={solveDeckFilename}
            runCommand={donjonRunCommand(solveDeckFilename)}
          />
          </details>
          </div>
        </details>

        <section className="mt-5 rounded-xl border border-[var(--edge)] bg-black/10 p-4">
          <div className="flex items-start gap-3">
            <span className="step-dot">A</span>
            <div>
              <h2 className="text-base font-bold tracking-tight">Run single-object diagnostics</h2>
              <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
                {irenaMode
                  ? "The ingest smoke proves only that one object can be read. It neither validates nor replaces the withdrawn IRENA five-CPO deck preview above."
                  : "The ingest smoke proves that one object can be read. The generated solve is a starting diagnostic; replace its geometry, mixtures, solver, and boundary conditions with the consumer declared by your project."}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!asciiPath.trim() || runState.kind === "starting" || (runState.kind === "job" && (runState.data.status === "queued" || runState.data.status === "running"))}
              onClick={() => void startDonjonRun("Ingest smoke", "ingest", ingestDeckFilename, false)}
            >
              Run ingest smoke
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!asciiPath.trim() || runState.kind === "starting" || (runState.kind === "job" && (runState.data.status === "queued" || runState.data.status === "running"))}
              onClick={() => void startDonjonRun("Generic solve diagnostic", "solve", solveDeckFilename, true)}
            >
              {runState.kind === "starting"
                ? "Starting DONJON…"
                : runState.kind === "job" && (runState.data.status === "queued" || runState.data.status === "running")
                  ? "DONJON running…"
                  : "Run generic solve diagnostic"}
            </button>
          </div>
          <p className="mt-3 text-[11px] leading-5 text-[var(--fg-3)]">
            The backend uses the DONJON installation configured when the service starts; a web request cannot replace that trusted runtime.
          </p>
        </section>
        {!irenaMode ? (
          <DonjonRunStatus
            state={runState}
            projectRoot={projectRoot}
            component={selectedProjectComponent}
            asciiPath={asciiPath}
            format={format}
            runSummary={selectedPhysicsSummary || selectedReceipt}
          />
        ) : null}
          </div>
        </details>
      </div>
    </main>
  );
}

function GenericConsumerPanel({
  projectStatus,
  projectRoot,
  selectedComponentId,
  onSelectComponent,
}: {
  projectStatus: ProjectStatus | null;
  projectRoot: string;
  selectedComponentId: string;
  onSelectComponent: (id: string) => void;
}) {
  const required = projectStatus?.required_components ?? 0;
  const selected = projectStatus?.components.find(
    (item) => item.id === selectedComponentId,
  );
  return (
    <section className="surface p-5">
      <p className="page-kicker">Project-defined consumer</p>
      <h2 className="mt-1 text-lg font-bold">
        {projectStatus?.configured ? projectStatus.consumer.label : "No fixed core model is assumed"}
      </h2>
      <p className="mt-2 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
        {projectStatus?.configured
          ? `This project declares ${required} required component${required === 1 ? "" : "s"}. ${projectStatus.accepted_outputs} Converter handoff contract${projectStatus.accepted_outputs === 1 ? " has" : "s have"} passed. This is not a physics verdict; the consumer geometry and mixture map remain the responsibility of ${projectStatus.consumer.label}.`
          : "Open a project manifest to track a component set, or use the generic ingest builder below for a standalone Converter or native-SPH output. Converter does not invent a component count, core layout, or solver order."}
      </p>
      {projectStatus?.configured && projectStatus.components.length ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">
              Diagnostic component output
            </span>
            <select
              value={selectedComponentId}
              onChange={(event) => onSelectComponent(event.target.value)}
              className="mt-2 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
            >
              {projectStatus.components.map((component) => (
                <option key={component.id} value={component.id}>
                  {component.label} · {component.format.toUpperCase()} · {component.output.state}
                </option>
              ))}
            </select>
          </label>
          <div className="rounded-lg border border-[var(--edge)] bg-black/10 p-3 text-[11px] leading-5 text-[var(--fg-2)]">
            <strong className="text-[var(--fg-0)]">
              {selected?.label ?? "Select a component"}
            </strong>
            {selected ? (
              <>
                <code className="mt-1 block break-all text-[10px] text-[var(--fg-3)]">
                  {selected.paths.output}
                </code>
                <span className="mt-1 block">
                  input {selected.handoff.state} · output {selected.output.state}
                </span>
                <code className="mt-1 block break-all text-[10px] text-[var(--fg-3)]">
                  Converter receipt: {selected.paths.receipt || "not declared"}
                </code>
                {selected.paths.physics_summary ? (
                  <code className="mt-1 block break-all text-[10px] text-[var(--fg-3)]">
                    SPH physics summary: {selected.paths.physics_summary}
                  </code>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
      ) : null}
      <p className="mt-4 rounded-lg border border-amber-300/20 bg-amber-300/[0.05] p-3 text-[11px] leading-5 text-amber-100">
        The tools below ingest exactly one selected object. They are component diagnostics,
        not a multi-component or full-core calculation. A real aggregate solve must come from
        the consumer geometry, mapping, and deck declared by this project manifest.
      </p>
      {projectStatus?.consumer.runs.length ? (
        <div className="mt-4 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.04] p-3">
          <div className="text-[10px] font-bold uppercase tracking-[0.13em] text-cyan-100">
            Manifest-declared consumer decks
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            {projectStatus.consumer.runs.map((run) => (
              <div key={run.id} className="rounded border border-cyan-300/10 bg-black/10 p-2 text-[11px]">
                <strong>{run.label}</strong> · {run.state}
                <code className="mt-1 block break-all text-[10px] text-cyan-100/65">
                  {run.deck_path ?? "deck path not declared"}
                </code>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10px] leading-4 text-cyan-100/70">
            These project-owned decks are authoritative. The generic builder below does not
            replace or silently synthesize them.
          </p>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href={projectRoot ? `/convert?project=${encodeURIComponent(projectRoot)}` : "/convert"} className="btn btn-primary">
          Open Converter
        </Link>
        {projectStatus?.configured && projectStatus.consumer.href && projectStatus.consumer.href !== "/donjon" ? (
          <Link href={projectConsumerHref(projectRoot, projectStatus.consumer, selected)} className="btn btn-secondary">Open declared consumer entry</Link>
        ) : null}
      </div>
    </section>
  );
}

function IrenaStrictFullCorePanel({
  projectStatus,
  projectRoot,
}: {
  projectStatus: ProjectStatus | null;
  projectRoot: string;
}) {
  const projectHref = projectRoot
    ? `/projects?project=${encodeURIComponent(projectRoot)}`
    : "/projects";
  const nativeLinks = projectNativeSphEntryHrefs(
    projectRoot,
    projectStatus?.components ?? [],
  );
  const converterHref = nativeLinks.converterHref ?? projectHref;
  const equivalenceHref = nativeLinks.equivalenceHref;
  const evidenceHref = projectRoot
    ? `/inspect?mode=acceptance&project=${encodeURIComponent(projectRoot)}`
    : "/inspect?mode=acceptance";
  const accepted = projectStatus?.accepted_outputs ?? 0;
  const required = projectStatus?.required_components ?? 1;

  return (
    <section className="surface border-cyan-300/25 bg-cyan-300/[0.035] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="page-kicker">Current physical candidate</p>
          <h2 className="mt-1 text-xl font-bold tracking-tight">
            Preserve the 91-position reference; declare the coarse domains
          </h2>
          <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
            This is one full-core handoff, not five reused material labels. The
            domain strategy is chosen before tallies are accumulated and is
            recorded in the Converter/native-SPH evidence.
          </p>
        </div>
        <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.13em] text-amber-100">
          HOLD · no accepted IRENA result
        </span>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <article className="rounded-xl border border-[var(--edge)] bg-black/10 p-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-cyan-200">
            Strategy A · 91 domains
          </div>
          <h3 className="mt-2 text-sm font-bold">Independent coarse positions</h3>
          <p className="mt-2 text-[11px] leading-5 text-[var(--fg-3)]">
            Each physical position owns its OpenMC-integrated rates, flux, and
            Converter mixture. This is the direct baseline.
          </p>
        </article>
        <article className="rounded-xl border border-[var(--edge)] bg-black/10 p-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-cyan-200">
            Strategy B · 21 domains
          </div>
          <h3 className="mt-2 text-sm font-bold">Exact D3 transport-time orbits</h3>
          <p className="mt-2 text-[11px] leading-5 text-[var(--fg-3)]">
            Symmetry-equivalent positions share a tally domain while OpenMC is
            transporting particles. Cross sections are never averaged between
            positions after transport.
          </p>
        </article>
      </div>

      <div className="mt-4 rounded-xl border border-[var(--edge)] bg-black/10 p-4">
        <div className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">
          Acceptance is always position resolved
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <FullCoreGate label="Native SPH" detail="all one-speed and final solves proved" />
          <FullCoreGate label="Finite balance" detail="keff and physical leakage" />
          <FullCoreGate label="91-position power" detail="RMS and maximum errors" />
          <FullCoreGate label="Exact evidence" detail="hash-linked Converter artifacts" />
        </div>
        <p className="mt-3 text-[11px] leading-5 text-amber-100/85">
          No ADF, empirical eigenvalue multiplier, clipping, frozen group,
          flux floor, zero-bin fill, or post-hoc orbit averaging is accepted.
        </p>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] text-[var(--fg-3)]">
          Project handoffs: {accepted}/{required}. A complete handoff count is
          still not a full-core physics verdict.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link href={projectHref} className="btn btn-secondary">Project</Link>
          <Link href={converterHref} className="btn btn-primary">
            {nativeLinks.converterHref ? "Converter reference" : "Open project first"}
          </Link>
          <Link href={equivalenceHref} className="btn btn-secondary">Native SPH</Link>
          <Link href={evidenceHref} className="btn btn-secondary">Review evidence</Link>
        </div>
      </div>
    </section>
  );
}

function FullCoreGate({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="rounded-lg border border-cyan-300/15 bg-cyan-300/[0.04] p-3">
      <div className="text-[11px] font-bold text-cyan-100">{label}</div>
      <div className="mt-1 text-[10px] leading-4 text-[var(--fg-3)]">{detail}</div>
    </div>
  );
}

function IrenaColorsetCorePanel({
  paths,
  onPathChange,
  onBrowse,
  solver,
  onSolverChange,
  deck,
}: {
  paths: Irena30ColorsetCpoPaths;
  onPathChange: (key: CpoPathKey, value: string) => void;
  onBrowse: (key: CpoPathKey) => void;
  solver: Irena30CoreSolver;
  onSolverChange: (solver: Irena30CoreSolver) => void;
  deck: string;
}) {
  const [verification, setVerification] = useState<
    | { kind: "idle" }
    | { kind: "loading" }
    | { kind: "ready" }
    | { kind: "error"; message: string }
  >({ kind: "idle" });
  const missing = IRENA30_COLORSET_CPO_COMPONENTS.filter(
    (component) => !paths[component.id].trim(),
  );
  const longPaths = IRENA30_COLORSET_CPO_COMPONENTS.filter(
    (component) => paths[component.id].trim().length > 72,
  );
  const duplicatePaths =
    new Set(
      IRENA30_COLORSET_CPO_COMPONENTS.map((component) =>
        paths[component.id].trim(),
      ).filter(Boolean),
    ).size !== IRENA30_COLORSET_CPO_COMPONENTS.length;
  const pathsComplete =
    missing.length === 0 && longPaths.length === 0 && !duplicatePaths;

  useEffect(() => {
    setVerification({ kind: "idle" });
  }, [paths]);

  async function verifyCpoFiles() {
    setVerification({ kind: "loading" });
    try {
      const previews = await Promise.all(
        IRENA30_COLORSET_CPO_COMPONENTS.map(async (component) => ({
          component,
          preview: await api.textPreview(paths[component.id], 8192, 100),
        })),
      );
      const issues = previews
        .map(({ component, preview }) =>
          irena30CpoPreviewIssue(component.id, preview.text),
        )
        .filter((issue): issue is string => issue !== null);
      if (issues.length > 0) {
        setVerification({
          kind: "error",
          message: issues.join("; "),
        });
        return;
      }
      setVerification({ kind: "ready" });
    } catch (error) {
      setVerification({
        kind: "error",
        message:
          error instanceof ApiError
            ? error.detail ?? error.message
            : error instanceof Error
              ? error.message
              : "Could not inspect the five historical CPO headers.",
      });
    }
  }

  return (
    <section
      className="surface border-amber-300/25 bg-amber-300/[0.035] p-5"
      data-testid="irena-colorset-core-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="page-kicker">Withdrawn historical diagnostic</p>
          <h2 className="mt-1 text-xl font-bold tracking-tight">
            Five center-domain CPOs → five reused labels → 91 positions
          </h2>
          <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
            This archived mapping takes <span className="font-mono">FROM 1</span>{" "}
            from each <span className="font-mono">L_MULTICOMPO</span> and reuses only
            five labels across the whole map. It does not retain the 91-position or
            21-orbit transport-time domain evidence required by the current IRENA route.
          </p>
        </div>
        <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.13em] text-amber-100">
          {IRENA30_LEGACY_DECK_STATUS}
        </span>
      </div>

      <div className="mt-5 grid gap-3">
        {IRENA30_COLORSET_CPO_COMPONENTS.map((component) => (
          <div
            key={component.id}
            className="grid gap-3 rounded-xl border border-[var(--edge)] bg-black/10 p-3 md:grid-cols-[150px_minmax(0,1fr)_auto] md:items-end"
          >
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">
                MIX {component.mixture}
              </div>
              <div className="mt-1 text-sm font-bold">{component.label}</div>
              <div className="mt-0.5 text-[11px] text-[var(--fg-2)]">
                {component.colorset} colorset
              </div>
            </div>
            <label className="block">
              <span className="sr-only">{component.label} CPO path</span>
              <input
                value={paths[component.id]}
                onChange={(event) => onPathChange(component.id, event.target.value)}
                placeholder={`/short/cpo/${component.id}.mcompo.txt`}
                className="w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-[12px] text-[var(--fg-0)]"
              />
            </label>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => onBrowse(component.id)}
            >
              Browse
            </button>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
        <label className="block rounded-xl border border-[var(--edge)] bg-black/10 p-3">
          <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--fg-3)]">
            Historical deck solver
          </span>
          <select
            value={solver}
            onChange={(event) => onSolverChange(event.target.value as Irena30CoreSolver)}
            className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
          >
            <option value="snt">SN</option>
            <option value="spn">SPN</option>
          </select>
        </label>
        <div className="rounded-xl border border-[var(--edge)] bg-black/10 p-3 text-[12px] leading-5 text-[var(--fg-2)]">
          <div className="font-bold text-[var(--fg-1)]">Archived fixed map</div>
          <div className="mt-1">
            HEXZ 91 · NMIX 5 · ARI control positions use CSD · radial VOID · axial
            reflective · SIDE 10.1036 cm · height 10.0 cm.
          </div>
          <div className="mt-1 text-[11px] text-[var(--fg-3)]">
            SN/SPN changes only the archived deck variant shown below. Neither
            variant is an IRENA full-core equivalence result.
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!pathsComplete || verification.kind === "loading"}
          onClick={() => void verifyCpoFiles()}
        >
          {verification.kind === "loading"
            ? "Checking five historical CPO headers…"
            : verification.kind === "ready"
              ? "✓ Five CPO headers readable"
              : "Check five historical CPO headers"}
        </button>
        <span className="text-[11px] text-[var(--fg-3)]">
          This checks file signature and colorset identity only; it is not a model gate.
        </span>
      </div>

      {longPaths.length > 0 ? (
        <div className="mt-3 rounded-md border border-rose-300/25 bg-rose-300/[0.07] px-3 py-2 text-[12px] text-rose-100">
          Shorten the {longPaths.map((component) => component.label).join(", ")}{" "}
          path below 73 characters; SEQ_ASCII paths are limited by DONJON.
        </div>
      ) : missing.length > 0 ? (
        <div className="mt-3 rounded-md border border-amber-300/25 bg-amber-300/[0.07] px-3 py-2 text-[12px] text-amber-100">
          Waiting for {missing.map((component) => component.label).join(", ")} CPO.
          Paths are optional for viewing the placeholder deck and required only
          for checking the historical CPO headers.
        </div>
      ) : duplicatePaths ? (
        <div className="mt-3 rounded-md border border-rose-300/25 bg-rose-300/[0.07] px-3 py-2 text-[12px] text-rose-100">
          Each component must use its own colorset CPO path; duplicate inputs are
          not allowed.
        </div>
      ) : verification.kind === "error" ? (
        <div className="mt-3 rounded-md border border-rose-300/25 bg-rose-300/[0.07] px-3 py-2 text-[12px] text-rose-100">
          {verification.message}
        </div>
      ) : verification.kind === "ready" ? (
        <div className="mt-3 rounded-md border border-amber-300/25 bg-amber-300/[0.07] px-3 py-2 text-[12px] text-amber-100">
          Five historical CPO headers are readable. This supports deck inspection
          only and does not qualify the 91-position reuse map.
        </div>
      ) : (
        <div className="mt-3 rounded-md border border-amber-300/25 bg-amber-300/[0.07] px-3 py-2 text-[12px] text-amber-100">
          All five paths are entered. Check their L_MULTICOMPO signatures if you
          need to reproduce the historical deck; execution remains unavailable.
        </div>
      )}

      <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
          Review withdrawn five-CPO .x2m deck
        </summary>
        <div className="mt-3 flex flex-wrap gap-2">
          <CopyCliButton value={deck} label="Copy withdrawn deck text" />
        </div>
        <pre className="mt-3 max-h-96 overflow-auto whitespace-pre rounded-lg border border-[var(--edge)] bg-black/25 p-3 font-mono text-[11px] leading-5 text-[var(--fg-2)]">
          {deck}
        </pre>
      </details>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-secondary"
          disabled
        >
          91-position execution withdrawn
        </button>
        <span className="text-[11px] text-[var(--fg-3)]">
          The UI intentionally provides no run action. The text is retained only
          to inspect how the historical map was assembled.
        </span>
      </div>
    </section>
  );
}

function DonjonRunStatus({
  state,
  projectRoot,
  component,
  asciiPath,
  format,
  runSummary,
}: {
  state: DonjonRunState;
  projectRoot: string;
  component: ProjectStatus["components"][number] | null;
  asciiPath: string;
  format: DonjonGuideFormat;
  runSummary: string;
}) {
  if (state.kind === "idle") return null;
  if (state.kind === "starting") {
    return (
      <div className="mt-3 rounded-md border border-cyan-300/20 bg-cyan-300/[0.06] px-3 py-3 text-[12px] text-cyan-100">
        Starting {state.label}…
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="mt-3 rounded-md border border-rose-300/25 bg-rose-300/[0.07] px-3 py-3 text-[12px] text-rose-100">
        {state.message}
      </div>
    );
  }
  return (
    <div
      className={`mt-3 rounded-md border px-3 py-3 text-[12px] ${state.data.status === "completed" ? "border-emerald-300/25 bg-emerald-300/[0.07] text-emerald-100" : state.data.status === "failed" ? "border-rose-300/25 bg-rose-300/[0.07] text-rose-100" : "border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-100"}`}
    >
      <div className="font-semibold">
        {state.label} · {state.data.status}
      </div>
      <div className="mt-1">{state.data.message}</div>
      <EvidenceLadder
        stages={donjonEvidenceLadder(state.label, state.data)}
        title="DONJON job evidence scope"
        compact
      />
      {state.data.k_effective != null ? (
        <div className="mt-2 text-lg font-bold">
          computed k-effective = {state.data.k_effective.toFixed(6)}
          <span className="ml-2 text-[10px] font-normal uppercase tracking-[0.1em] text-[var(--fg-3)]">
            not an acceptance verdict
          </span>
        </div>
      ) : null}
      {state.data.result_path ? (
        <div className="mt-2 break-all font-mono text-[11px]">
          {state.data.result_path}
        </div>
      ) : null}
      {state.data.status === "completed" ? (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-current/15 pt-3">
          {projectRoot ? (
            <Link
              href={`/projects?project=${encodeURIComponent(projectRoot)}${component ? `&component=${encodeURIComponent(component.id)}` : ""}`}
              className="btn btn-secondary"
            >
              Return to Project
            </Link>
          ) : null}
          {projectRoot && component && state.data.result_path ? (
            <Link
              href={`/projects?project=${encodeURIComponent(projectRoot)}&component=${encodeURIComponent(component.id)}&add_evidence=${encodeURIComponent(state.data.result_path)}&evidence_label=${encodeURIComponent(`${state.label} result`)}`}
              className="btn btn-primary"
            >
              Add result to project evidence
            </Link>
          ) : null}
          {component ? (
            <Link href={projectComponentConvertHref(projectRoot, component)} className="btn btn-secondary">
              Reopen Converter
            </Link>
          ) : null}
          <Link
            href={`/builder?${new URLSearchParams({
              command: "bundle",
              output_dir: projectRoot && component
                ? projectPath(projectRoot, "bundles", component.id)
                : `${asciiPath}.bundle`,
              mgxs: component?.paths.input ?? "",
              ...(format === "macrolib" ? { macrolib: asciiPath } : { mcompo: asciiPath }),
              ...(runSummary ? { run_summary: runSummary } : {}),
            }).toString()}`}
            className="btn btn-secondary"
          >
            Bundle this diagnostic
          </Link>
        </div>
      ) : null}
      {state.data.log_tail ? (
        <details className="mt-2">
          <summary className="cursor-pointer font-semibold">Result log</summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-black/25 p-2 text-[11px]">
            {state.data.log_tail}
          </pre>
        </details>
      ) : null}
    </div>
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
  // Compare the summary output against ALL bundled ASCII artifacts: a
  // bundle can carry both a MULTICOMPO and a MACROLIB, and pointing at
  // either one is not a mismatch.
  const mismatch = donjonBundleAsciiMismatch(state.data.artifacts, summaryArtifact);
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
            The conversion summary points to an output path that is not one of
            the bundle&apos;s DONJON ASCII artifacts. Use a bundled artifact
            for a self-contained package, or choose the summary output if you
            are working in the original run directory.
          </p>
          <div className="mt-1 grid gap-1 font-mono text-[11px] text-amber-100/80">
            {mismatch.artifactPaths.map((artifactPath) => (
              <span key={artifactPath} className="truncate" title={artifactPath}>
                artifact: {artifactPath}
              </span>
            ))}
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
      <div>
        <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-100/70">
          conversion summary
        </div>
        <div className="mt-1 font-semibold tracking-tight">
          DONJON inputs inferred from convert_summary.json
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
}: {
  mixtureCount: string;
  onMixtureCountChange: (value: string) => void;
  geometry: DonjonDeckGeometry;
  onGeometryChange: (value: DonjonDeckGeometry) => void;
  solver: DonjonDeckSolver;
  onSolverChange: (value: DonjonDeckSolver) => void;
  spnOrder: number;
  onSpnOrderChange: (value: number) => void;
  snOrder: number;
  onSnOrderChange: (value: number) => void;
  hexSide: string;
  onHexSideChange: (value: string) => void;
  hexHeight: string;
  onHexHeightChange: (value: string) => void;
  boundaries: Pick<
    DonjonDeckOptions,
    "xMinus" | "xPlus" | "yMinus" | "yPlus" | "zMinus" | "zPlus"
  >;
}) {
  const boundaryLine =
    `X- ${boundaries.xMinus} X+ ${boundaries.xPlus} ` +
    `Y- ${boundaries.yMinus} Y+ ${boundaries.yPlus}` +
    (geometry === "car3d"
      ? ` Z- ${boundaries.zMinus} Z+ ${boundaries.zPlus}`
      : "");

  return (
    <section className="mt-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="step-dot">2</span>
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              generic deck builder
            </div>
            <h2 className="mt-1 text-base font-semibold tracking-tight">
              Build a diagnostic skeleton
            </h2>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              {geometry === "hex"
                ? "This generic HEXZ block creates one position for every mixture in one ASCII object. It is useful for diagnostics, but it cannot supply evidence for the withdrawn IRENA five-CPO map."
                : "These controls generate a one-object starter skeleton for diagnostics. They do not establish a model-specific full-core result."}
            </p>
          </div>
        </div>
        <span className="rounded border border-cyan-300/20 bg-cyan-300/10 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-cyan-100">
          local template
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-4">
        <label className="block">
          <span className="text-[12px] font-semibold tracking-tight">
            Mixtures in this one object
          </span>
          <input
            type="number"
            min={1}
            max={999}
            step={1}
            value={mixtureCount}
            placeholder="1"
            onChange={(event) => onMixtureCountChange(event.target.value)}
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
              SN (hex only)
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
              Select the discrete-ordinates order used by the generated SN deck.
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
              placeholder="1.0"
              onChange={(event) => onHexSideChange(event.target.value)}
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
              placeholder="10.0"
              onChange={(event) => onHexHeightChange(event.target.value)}
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
          Hexagonal boundary conditions are fixed by the skeleton — see the
          outer-boundary card in the deck checklist below.
        </p>
      ) : (
        <p className="mt-3 text-[12px] leading-5 text-[var(--fg-2)]">
          Boundary conditions are fixed for the smoke cell:{" "}
          <span className="font-mono">{boundaryLine}</span> — replace them
          together with the GEOM block for the real case.
        </p>
      )}
    </section>
  );
}

function DeckChecklist({ items }: { items: DonjonDeckChecklistItem[] }) {
  return (
    <section className="mt-5 rounded-xl border border-[var(--edge)] bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="step-dot">3</span>
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              deck checklist
            </div>
            <h2 className="mt-1 text-base font-semibold tracking-tight">
              Review the full-core contract
            </h2>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              Confirm the mixture order, geometry, boundary conditions, tracking, and solver before treating the result as a production calculation.
            </p>
          </div>
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

function SnippetCard({
  title,
  description,
  code,
  downloadFilename,
  runCommand,
  recommended = false,
  ready = true,
}: {
  title: string;
  description: string;
  code: string;
  downloadFilename?: string;
  runCommand?: string;
  recommended?: boolean;
  ready?: boolean;
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
          {downloadFilename ? (
            ready ? (
              <a
                href={downloadHref}
                download={downloadFilename}
                className={`btn btn-${recommended ? "primary" : "secondary"} px-2 py-1 text-[11px]`}
              >
                {recommended ? "Download ingest deck" : "Download .x2m"}
              </a>
            ) : (
              <button type="button" className="btn btn-primary px-2 py-1 text-[11px]" disabled>
                Enter ASCII path first
              </button>
            )
          ) : null}
          {runCommand && ready ? (
            <CopyCliButton
              value={runCommand}
              label="Copy run command"
              ariaLabel={`Copy DONJON run command for ${title}`}
              compact
            />
          ) : null}
        </div>
      </div>
      <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
          Review or copy deck text
        </summary>
        <div className="mt-3 flex justify-end">
          <CopyCliButton value={code} label="Copy deck text" compact />
        </div>
        <pre className="mt-3 max-h-[460px] overflow-auto rounded-lg border border-[var(--edge)] bg-black/30 p-3 text-[12px] leading-5 text-[var(--fg-1)]">
          {code}
        </pre>
      </details>
    </article>
  );
}
