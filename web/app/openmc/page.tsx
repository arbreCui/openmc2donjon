"use client";

import { FormEvent, Suspense, useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  ConvertFormat,
  OpenmcEquivalenceMode,
  OpenmcWorkflowPlan,
  OpenmcExportExecutionResponse,
  api,
} from "@/lib/api";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import OpenmcArtifactList from "@/components/openmc/OpenmcArtifactList";
import OpenmcCommandList from "@/components/openmc/OpenmcCommandList";
import OpenmcProductionPathPanel from "@/components/openmc/OpenmcProductionPathPanel";
import OpenmcSphPhysicsSummaryCard from "@/components/openmc/OpenmcSphPhysicsSummaryCard";
import OpenmcProvenanceCard from "@/components/OpenmcProvenanceCard";
import OpenmcWorkflowSummary from "@/components/openmc/OpenmcWorkflowSummary";
import { FormStep, WorkflowPageHeader } from "@/components/ui/Workflow";
import { useSettings } from "@/lib/settings";
import {
  OPENMC_SPH_SIDECAR_FORM_HREF,
  isFailedOpenmcSphSidecarCheck,
  openmcDirectConvertHref,
  openmcSphPrerequisiteCommands,
  openmcSphSidecarCheckFailed,
} from "@/lib/openmcWorkflowWalkthrough";
import {
  LIVE_OPENMC_SPH_DEMO,
  MOCK_OPENMC_SPH_DEMO,
  type OpenmcSphDemoPreset,
  openmcSphPlannerPrefill,
} from "@/lib/openmcSphDemo";
import {
  parseConvertFormat,
  parseOpenmcEquivalence,
  queryFlag,
} from "@/lib/workflowQuery";
import {
  colorsetDefinition,
  isWithdrawnColorsetWorkflow,
} from "@/lib/colorsetWorkflow";
import {
  colorsetProjectPaths,
  projectPath,
  projectRootFromSearchParams,
  type ProjectComponentRouteContext,
} from "@/lib/projectWorkspace";

type PlanState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: OpenmcWorkflowPlan }
  | { kind: "error"; message: string; status?: number };

type BackendMode = "checking" | "mock" | "live" | "unavailable";

type ExportExecutionState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: OpenmcExportExecutionResponse }
  | { kind: "error"; message: string };

type BrowserTarget =
  | "recipe"
  | "statepoint"
  | "run-dir"
  | "hdf5"
  | "output"
  | "adf"
  | "sph"
  | "summary";

interface BrowserConfig {
  initialPath: string;
  extensions: readonly string[];
  fileTypeLabel: string;
  chipLabel: string;
  recentScope: string;
  selectMode?: "file" | "directory";
}

const FALLBACK_RUN_DIR = "/path/to/openmc2donjon-run";
const RECIPE_TEMPLATE_PATH = "examples/openmc_recipe_template/export_recipe.py";

export default function OpenmcPage() {
  return (
    <Suspense fallback={<OpenmcLoading />}>
      <OpenmcPageContent />
    </Suspense>
  );
}

function OpenmcLoading() {
  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading OpenMC prep…
        </section>
      </div>
    </main>
  );
}

function OpenmcPageContent() {
  const searchParams = useSearchParams();
  const isIrenaColorset = isWithdrawnColorsetWorkflow(
    searchParams.get("colorset"),
    searchParams.get("contract"),
  );
  const activeColorset = colorsetDefinition(searchParams.get("colorset"));
  const projectRoot = projectRootFromSearchParams(searchParams);
  const componentId = searchParams.get("component");
  const contract = searchParams.get("contract");
  const projectContext: ProjectComponentRouteContext = {
    projectRoot,
    componentId,
    contract,
  };
  const projectPaths = isIrenaColorset ? colorsetProjectPaths(projectRoot, activeColorset) : null;
  const initialEquivalence = parseOpenmcEquivalence(searchParams.get("equivalence"));
  const [equivalence, setEquivalence] = useState<OpenmcEquivalenceMode>(initialEquivalence);
  const [format, setFormat] = useState<ConvertFormat>(
    searchParams.get("format") == null && initialEquivalence === "sph"
      ? "multicompo"
      : parseConvertFormat(searchParams.get("format")),
  );
  const [recipePath, setRecipePath] = useState(
    projectRoot && projectPaths ? projectPath(projectPaths.directory, "export_recipe.py") : "",
  );
  const [statepointPath, setStatepointPath] = useState(
    projectRoot && projectPaths ? projectPath(projectPaths.directory, "ce_statepoint.h5") : "",
  );
  const [runDir, setRunDir] = useState(projectPaths?.directory ?? "");
  const [outputPath, setOutputPath] = useState(searchParams.get("output") ?? "");
  const [keepHdf5Path, setKeepHdf5Path] = useState(
    searchParams.get("input") ?? projectPaths?.mgxs ?? "",
  );
  const [adfSource, setAdfSource] = useState("");
  const [sphSource, setSphSource] = useState("");
  const [physicsSummaryPath, setPhysicsSummaryPath] = useState(
    searchParams.get("summary") ?? "",
  );
  const [loadStatepoint, setLoadStatepoint] = useState(true);
  const [check, setCheck] = useState(true);
  const [production, setProduction] = useState(
    isIrenaColorset ? false : queryFlag(searchParams, "production", true),
  );
  const [requireKnownMesh, setRequireKnownMesh] = useState(
    isIrenaColorset
      ? false
      : queryFlag(searchParams, "require_known_mesh", false),
  );
  const [strictDryRun, setStrictDryRun] = useState(false);
  const [hFactorText, setHFactorText] = useState("");
  const [state, setState] = useState<PlanState>({ kind: "idle" });
  const [submittedPlanKey, setSubmittedPlanKey] = useState<string | null>(null);
  const [backendMode, setBackendMode] = useState<BackendMode>("checking");
  const [exportState, setExportState] = useState<ExportExecutionState>({ kind: "idle" });
  const [overwriteExport, setOverwriteExport] = useState(false);
  const [liveDemoAvailable, setLiveDemoAvailable] = useState(false);
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const planButtonRef = useRef<HTMLButtonElement | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const runDirPlaceholder = savedPrefix || FALLBACK_RUN_DIR;
  const derivedOutput = useMemo(
    () => defaultAsciiPath(runDir || savedPrefix, format),
    [runDir, savedPrefix, format],
  );
  const derivedHdf5 = useMemo(
    () => defaultHdf5Path(runDir || savedPrefix),
    [runDir, savedPrefix],
  );
  const directConverterHref = openmcDirectConvertHref(
    keepHdf5Path || (runDir.trim() ? derivedHdf5 : ""),
    outputPath || (runDir.trim() ? derivedOutput : ""),
    format,
    production,
    projectContext,
  );
  const planInputKey = JSON.stringify({
    equivalence,
    format,
    recipePath: recipePath.trim(),
    statepointPath: statepointPath.trim(),
    loadStatepoint,
    runDir: runDir.trim(),
    outputPath: outputPath.trim() || derivedOutput,
    keepHdf5Path: keepHdf5Path.trim() || derivedHdf5,
    check,
    production,
    requireKnownMesh,
    strictDryRun,
    hFactorText: hFactorText.trim(),
    adfSource: adfSource.trim(),
    sphSource: sphSource.trim(),
  });
  const planMatchesInputs = submittedPlanKey === planInputKey;
  const activePlanState: PlanState = planMatchesInputs
    ? state
    : state.kind === "loading"
      ? state
      : { kind: "idle" };
  const missingPlanInputs = [
    recipePath.trim() ? null : "recipe",
    (production || loadStatepoint) && !statepointPath.trim() ? "CE statepoint" : null,
    runDir.trim() ? null : "run folder",
    production && hFactorText.trim() ? "remove the H-factor fallback" : null,
  ].filter((item): item is string => item != null);
  const planReady = !isIrenaColorset && missingPlanInputs.length === 0;
  const browserConfig = browserTarget
    ? openmcBrowserConfig(browserTarget, {
        recipePath,
        statepointPath,
        runDir,
        keepHdf5Path,
        outputPath,
        derivedOutput,
        adfSource,
        sphSource,
        physicsSummaryPath,
        savedPrefix,
        format,
      })
    : null;
  const sphDemoPreset =
    backendMode === "mock"
      ? MOCK_OPENMC_SPH_DEMO
      : backendMode === "live" && liveDemoAvailable
        ? LIVE_OPENMC_SPH_DEMO
        : null;
  const sphDemoMode =
    sphDemoPreset == null ? null : backendMode === "mock" ? "mock" : "live";

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((health) => {
        if (cancelled) return;
        setBackendMode(health.mock_mode ? "mock" : "live");
        if (health.mock_mode) return;
        // The live demo card prefills absolute paths from a specific
        // production run; only offer it when those artifacts exist on the
        // backend host.
        Promise.all([
          api.fileStatus(LIVE_OPENMC_SPH_DEMO.physicsSummary),
          api.fileStatus(LIVE_OPENMC_SPH_DEMO.augmentedH5),
        ])
          .then((statuses) => {
            if (cancelled) return;
            setLiveDemoAvailable(
              statuses.every(
                (status) => status.exists && status.kind === "file",
              ),
            );
          })
          .catch(() => {
            if (!cancelled) setLiveDemoAvailable(false);
          });
      })
      .catch(() => {
        if (!cancelled) setBackendMode("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Re-sync form state from query params on same-route navigations
    // (e.g. the "Open SPH summary" entry-point link); useState initializers
    // only run on mount. Only params present in the URL override state.
    const equivalenceParam = searchParams.get("equivalence");
    if (equivalenceParam != null) {
      setEquivalence(parseOpenmcEquivalence(equivalenceParam));
    }
    const formatParam = searchParams.get("format");
    if (formatParam != null) {
      setFormat(parseConvertFormat(formatParam));
    } else if (parseOpenmcEquivalence(equivalenceParam) === "sph") {
      setFormat("multicompo");
    }
    const summaryParam = searchParams.get("summary");
    if (summaryParam != null) setPhysicsSummaryPath(summaryParam);
    const inputParam = searchParams.get("input");
    if (inputParam != null) setKeepHdf5Path(inputParam);
    const outputParam = searchParams.get("output");
    if (outputParam != null) setOutputPath(outputParam);
    if (isIrenaColorset) {
      setProduction(false);
      setRequireKnownMesh(false);
    } else if (searchParams.get("production") != null) {
      setProduction(queryFlag(searchParams, "production", false));
    }
    if (!isIrenaColorset && searchParams.get("require_known_mesh") != null) {
      setRequireKnownMesh(queryFlag(searchParams, "require_known_mesh", false));
    }
  }, [isIrenaColorset, searchParams]);

  async function plan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmittedPlanKey(planInputKey);
    setExportState({ kind: "idle" });
    if (isIrenaColorset) {
      setState({
        kind: "error",
        message:
          "The historical IRENA five-colorset workflow is withdrawn and cannot create an OpenMC production plan.",
      });
      return;
    }
    const hFactorDefault = parseOptionalNumber(hFactorText);
    if (hFactorDefault === "invalid") {
      setState({
        kind: "error",
        message: "H-factor default must be a finite number.",
      });
      return;
    }
    if (production && (!loadStatepoint || !statepointPath.trim())) {
      setState({
        kind: "error",
        message:
          "A formal production export requires a real CE statepoint. Recipe-only mode is a non-production command scaffold.",
      });
      return;
    }
    if (production && hFactorDefault != null) {
      setState({
        kind: "error",
        message:
          "Production forbids an H-factor fallback. Export physical group-wise H-FACTOR / kappa-fission data instead.",
      });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await api.openmcWorkflowPlan({
        workflow: "two-step",
        plan_scope: "export",
        recipe_path: recipePath,
        statepoint_path: statepointPath,
        load_statepoint: loadStatepoint,
        format,
        output_path: outputPath || derivedOutput,
        run_dir: runDir,
        keep_hdf5_path: keepHdf5Path || derivedHdf5,
        check,
        production,
        strict_dry_run: strictDryRun,
        h_factor_default: hFactorDefault,
        require_known_energy_mesh: requireKnownMesh,
        warn_unknown_energy_mesh: true,
        equivalence,
        adf_source: adfSource,
        sph_source: sphSource,
        build_flux_ratio_adf: equivalence === "flux-ratio-adf",
      });
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  async function runExport() {
    if (isIrenaColorset) {
      setExportState({
        kind: "error",
        message:
          "The historical IRENA five-colorset workflow is diagnostic only; export execution is disabled.",
      });
      return;
    }
    if (!planMatchesInputs || state.kind !== "ok" || !state.data.ok) {
      setExportState({
        kind: "error",
        message: "The form changed after planning. Create a fresh plan before writing the HDF5.",
      });
      return;
    }
    setExportState({ kind: "loading" });
    try {
      const data = await api.executeOpenmcExport({
        recipe_path: recipePath,
        statepoint_path: statepointPath,
        load_statepoint: loadStatepoint,
        output_path: keepHdf5Path || derivedHdf5,
        overwrite: overwriteExport,
      });
      setExportState({ kind: "ok", data });
    } catch (error) {
      setExportState({
        kind: "error",
        message:
          error instanceof ApiError
            ? error.detail ?? error.message
            : error instanceof Error
              ? error.message
              : "OpenMC export failed",
      });
    }
  }

  function applyBrowserPick(picked: string) {
    switch (browserTarget) {
      case "recipe":
        setRecipePath(picked);
        break;
      case "statepoint":
        setStatepointPath(picked);
        break;
      case "run-dir":
        setRunDir(picked);
        break;
      case "hdf5":
        setKeepHdf5Path(picked);
        break;
      case "output":
        setOutputPath(picked);
        break;
      case "adf":
        setAdfSource(picked);
        break;
      case "sph":
        setSphSource(picked);
        break;
      case "summary":
        setPhysicsSummaryPath(picked);
        break;
      default:
        break;
    }
    setBrowserTarget(null);
    planButtonRef.current?.focus();
  }

  function updateLoadStatepoint(value: boolean) {
    setLoadStatepoint(value);
    if (!value) {
      setProduction(false);
      setRequireKnownMesh(false);
    }
  }

  function updateProduction(value: boolean) {
    setProduction(value);
    if (value) {
      setLoadStatepoint(true);
      setHFactorText("");
    }
  }

  function applyOpenmcSphDemo(preset: OpenmcSphDemoPreset) {
    const prefill = openmcSphPlannerPrefill(preset);
    setEquivalence(prefill.equivalence);
    setFormat(prefill.format);
    setProduction(prefill.production);
    setCheck(prefill.check);
    setRunDir(prefill.runDir);
    setKeepHdf5Path(prefill.keepHdf5Path);
    setOutputPath(prefill.outputPath);
    setSphSource(prefill.sphSource);
    setPhysicsSummaryPath(preset.physicsSummary);
    setRecipePath(prefill.recipePath);
    setStatepointPath(prefill.statepointPath);
    setLoadStatepoint(prefill.loadStatepoint);
    setAdfSource("");
  }

  function reviewOpenmcSphDemo(preset: OpenmcSphDemoPreset) {
    applyOpenmcSphDemo(preset);
    window.setTimeout(() => {
      document.getElementById("openmc-sph-summary")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 0);
  }

  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <WorkflowPageHeader
          step="Handoff"
          eyebrow={isIrenaColorset ? `Withdrawn IRENA diagnostic · ${activeColorset.id}` : "OpenMC source"}
          title={isIrenaColorset ? "Review one archived fine/coarse colorset pair" : "Prepare an OpenMC MGXS handoff"}
          description={isIrenaColorset ? `The old seven-domain ${activeColorset.target}/${activeColorset.neighbors} setup is retained only to inspect historical paths and summaries. It cannot create a production OpenMC plan.` : "Prepare one HDF5 for the assembly, component, domain set, or larger model you actually need. The recipe owns its energy structure and domains; Converter does not impose a geometry or domain count."}
          input={isIrenaColorset ? "Archived seven-assembly recipe and evidence paths" : production ? "Validated export recipe + CE statepoint" : "Export recipe; statepoint optional only for a non-production scaffold"}
          output={isIrenaColorset ? "No production artifact; diagnostic review only" : "Model-defined MGXS HDF5"}
          actions={
            <Link
              href={isIrenaColorset ? "/donjon?mode=irena30-fullcore" : directConverterHref}
              className="btn btn-secondary"
            >
              {isIrenaColorset ? "Open current IRENA route" : "Already have an HDF5"}
            </Link>
          }
        />

        <section className={`mb-5 rounded-xl border p-4 ${isIrenaColorset ? "border-amber-300/25 bg-amber-300/[0.055]" : "border-emerald-300/20 bg-emerald-300/[0.055]"}`}>
          <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--accent)]">
            {isIrenaColorset ? "WITHDRAWN DIAGNOSTIC ONLY" : "Generic handoff path"}
          </div>
          <p className="mt-2 text-sm font-semibold text-[var(--fg-0)]">
            {isIrenaColorset ? `${activeColorset.id} cannot enter a production chain.` : "Export one handoff for the model and domains you actually need."}
          </p>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
            {isIrenaColorset ? "The five-colorset experiment is not a full-core equivalence model. Any production=1 value in an old bookmark is ignored, planning and export are disabled, and no Converter action is generated from this page." : "A standalone user can stop with one assembly or component HDF5. A project may coordinate one handoff or many; physical SPH is used only when that model requires it."}
          </p>
        </section>

        {!isIrenaColorset ? (
          <section className="mb-5 grid gap-3 lg:grid-cols-2">
            <article className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.04] p-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-cyan-200">
                What this page starts from
              </div>
              <h2 className="mt-2 text-sm font-semibold">OpenMC has already produced a statepoint</h2>
              <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
                Supply the statepoint and a recipe that declares groups, domains,
                tallies, and export metadata. The backend then writes the MGXS
                handoff; it does not rerun transport.
              </p>
            </article>
            <article className="rounded-xl border border-amber-300/20 bg-amber-300/[0.04] p-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-amber-200">
                Only have a CE model or XML files?
              </div>
              <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
                Run the OpenMC transport model first. Then adapt the repository
                recipe template to bind that model&apos;s domains and tallies; a raw
                statepoint, summary.h5, or arbitrary MGXS library is not silently
                treated as a Converter-ready handoff.
              </p>
              <button
                type="button"
                onClick={() => setRecipePath(RECIPE_TEMPLATE_PATH)}
                className="btn-link mt-2"
              >
                Fill repository recipe template
              </button>
            </article>
          </section>
        ) : null}

        <form
          id="openmc-planner-form"
          className="surface space-y-3 p-4 sm:p-5"
          onSubmit={plan}
        >
          <section className="rounded-lg border border-[var(--edge)] bg-black/10 p-3 text-[12px] leading-5 text-[var(--fg-2)]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-[var(--fg-1)]">OpenMC prepares the HDF5 handoff</span>
              <span className="rounded border border-[var(--edge)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--fg-3)]">
                backend: {backendMode}
              </span>
            </div>
            <p className="mt-1">
              This page does not write DONJON ASCII. After export, Converter validates the handoff and lets you choose L_MULTICOMPO or L_MACROLIB and the ASCII or PyGan writer.
            </p>
          </section>

          <FormStep
            number="1"
            title="Select the OpenMC source"
            description={isIrenaColorset ? `The IRENA recipe defines seven assembly domains: center ${activeColorset.target} first and six ${activeColorset.neighbors} neighbors.` : "The recipe defines the domains and tallies required by your model. Converter preserves their declared order but does not prescribe the count."}
          >
            <div className="grid gap-3 lg:grid-cols-2">
              <TextField
                label="Recipe Python"
                value={recipePath}
                onChange={setRecipePath}
                onBrowse={() => setBrowserTarget("recipe")}
                placeholder={
                  settingsHydrated && savedPrefix
                    ? `${savedPrefix.replace(/\/?$/, "/")}export_recipe.py`
                    : "/path/to/export_recipe.py"
                }
              />
              <div className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
                <fieldset>
                  <legend className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                    Source mode
                  </legend>
                  <div className="mt-2 grid grid-cols-2 overflow-hidden rounded-md border border-[var(--edge)]">
                    <button
                      type="button"
                      onClick={() => updateLoadStatepoint(true)}
                      aria-pressed={loadStatepoint}
                      className={sourceModeClass(loadStatepoint)}
                    >
                      Recipe + statepoint
                    </button>
                    <button
                      type="button"
                      onClick={() => updateLoadStatepoint(false)}
                      aria-pressed={!loadStatepoint}
                      className={sourceModeClass(!loadStatepoint)}
                    >
                      Recipe scaffold only
                    </button>
                  </div>
                </fieldset>
                {loadStatepoint ? (
                  <div className="mt-3">
                    <TextField
                      label="CE statepoint HDF5"
                      value={statepointPath}
                      onChange={setStatepointPath}
                      onBrowse={() => setBrowserTarget("statepoint")}
                      placeholder="/path/to/statepoint.h5"
                    />
                  </div>
                ) : (
                  <p className="mt-3 text-[11px] leading-5 text-[var(--fg-3)]">
                    Non-production only. This can prepare a command scaffold or
                    call a recipe that explicitly owns already-loaded MGXS data;
                    it cannot claim a reproducible CE transport reference.
                  </p>
                )}
              </div>
            </div>
          </FormStep>

          <FormStep
            number="2"
            title="Choose the run folder"
            description="All generated artifacts use predictable names inside this folder."
          >
            <div className="grid gap-3">
              <TextField
                label="Run directory"
                value={runDir}
                onChange={setRunDir}
                onBrowse={() => setBrowserTarget("run-dir")}
                placeholder={runDirPlaceholder}
              />
            </div>
            <div className="mt-3 grid gap-2 text-[12px] text-[var(--fg-2)] sm:grid-cols-2">
              <div className="rounded-md border border-[var(--edge)] bg-black/10 px-3 py-2">
                HDF5 <span className="ml-2 font-mono text-[var(--fg-1)]">{keepHdf5Path || derivedHdf5}</span>
              </div>
              <div className="rounded-md border border-[var(--edge)] bg-black/10 px-3 py-2">
                Next: open this HDF5 in Converter and choose the downstream object there.
              </div>
            </div>
            <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
              <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
                Override artifact filenames
              </summary>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <TextField
                  label="Intermediate HDF5"
                  value={keepHdf5Path}
                  onChange={setKeepHdf5Path}
                  onBrowse={() => setBrowserTarget("hdf5")}
                  placeholder={derivedHdf5}
                />
              </div>
            </details>
          </FormStep>

          <section className="rounded-lg border border-cyan-300/20 bg-cyan-300/[0.045] px-3 py-3 text-[12px] leading-5 text-[var(--fg-2)]">
            {isIrenaColorset ? <>Historical artifact names remain visible for diagnosis. There is no production SPH or Converter continuation from this withdrawn route.</> : <>This step stops at an MGXS HDF5. Continue directly to <Link href={directConverterHref} className="font-semibold text-[var(--accent-2)] hover:underline">Converter</Link>, or run the equivalence method required by your project.</>}
          </section>

          <details className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
            <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
              Advanced production checks
            </summary>
            <div className="mt-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <Toggle
                label="Preflight (--check)"
                checked={check}
              onChange={setCheck}
            />
              <Toggle
                label="Production checks (--production)"
                checked={production}
                onChange={updateProduction}
                disabled={isIrenaColorset}
              />
            </div>
            <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
              <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
                Advanced checks and fallback values
              </summary>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <Toggle
                  label="Known mesh required"
                  checked={requireKnownMesh}
                  onChange={setRequireKnownMesh}
                  disabled={isIrenaColorset}
                />
                <Toggle
                  label="Strict dry run"
                  checked={strictDryRun}
                  onChange={setStrictDryRun}
                />
              </div>
              <div className="mt-3">
                <TextField
                  label="H-factor default"
                  value={hFactorText}
                  onChange={setHFactorText}
                  placeholder="optional; prefer group-wise kappa-fission in HDF5"
                  disabled={production}
                />
                <p className="mt-1 text-[11px] leading-5 text-[var(--fg-3)]">
                  {production
                    ? "Disabled: production requires physical group-wise H-FACTOR / kappa-fission data in the HDF5."
                    : "Diagnostic plumbing only; it is never accepted as production physics."}
                </p>
              </div>
            </details>
            </div>
          </details>

          <div className="flex flex-col gap-3 rounded-xl border border-emerald-300/20 bg-emerald-300/[0.055] p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <span className="step-dot">3</span>
              <div>
              <div className="text-sm font-bold">Create the OpenMC plan</div>
              <div className="mt-1 text-[12px] text-[var(--fg-2)]">
                {planReady
                  ? "Ready: generate the export command and artifact map. Nothing runs yet."
                  : isIrenaColorset
                    ? "Disabled: this five-colorset route is withdrawn diagnostic only."
                    : `Missing: ${missingPlanInputs.join(", ")}.`}
              </div>
              </div>
            </div>
            <button
              ref={planButtonRef}
              type="submit"
              className="btn btn-primary shrink-0"
              disabled={!planReady || state.kind === "loading"}
            >
              {state.kind === "loading"
                ? "Creating plan…"
                : isIrenaColorset
                  ? "Production planning withdrawn"
                : planReady
                  ? "Create OpenMC plan"
                  : "Fill required inputs first"}
            </button>
          </div>
        </form>

        {browserConfig ? (
          <FileBrowserModal
            open={browserTarget != null}
            initialPath={browserConfig.initialPath}
            extensions={browserConfig.extensions}
            fileTypeLabel={browserConfig.fileTypeLabel}
            chipLabel={browserConfig.chipLabel}
            recentScope={browserConfig.recentScope}
            selectMode={browserConfig.selectMode}
            onClose={() => setBrowserTarget(null)}
            onSelect={applyBrowserPick}
          />
        ) : null}

        <section className="mt-6">
          <PlanReport state={activePlanState} exportState={exportState} />
        </section>

        {activePlanState.kind === "ok" && activePlanState.data.ok ? (
          <section className="mt-5 rounded-xl border border-emerald-300/20 bg-emerald-300/[0.045] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-emerald-300">
                  Execute step 01
                </div>
                <h2 className="mt-1 text-base font-semibold">Run the planned OpenMC export</h2>
                <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
                  This invokes the named recipe exporter in the backend and writes only the MGXS HDF5. It does not run an arbitrary shell command.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary shrink-0"
                onClick={() => void runExport()}
                disabled={exportState.kind === "loading"}
              >
                {exportState.kind === "loading" ? "Exporting…" : "Run OpenMC export"}
              </button>
            </div>
            <label className="mt-3 flex items-center gap-2 text-[12px] text-[var(--fg-2)]">
              <input
                type="checkbox"
                checked={overwriteExport}
                onChange={(event) => setOverwriteExport(event.target.checked)}
                className="accent-emerald-500"
              />
              Replace the output HDF5 if it already exists
            </label>
            {exportState.kind === "ok" ? (
              <div className="mt-3 space-y-3">
                <div
                  className={`rounded-md border bg-black/10 px-3 py-2 text-[12px] ${
                    exportState.data.mock_mode
                      ? "border-amber-300/20 text-amber-100"
                      : "border-emerald-300/20 text-emerald-100"
                  }`}
                >
                  {exportState.data.mock_mode ? (
                    <>
                      Simulation only — OpenMC was not executed and no HDF5 was
                      written. The values below are interface placeholders, not
                      scientific evidence.
                    </>
                  ) : (
                    <>
                      Exported {exportState.data.mixtures} mixtures ·{" "}
                      {exportState.data.energy_groups} groups · P
                      {exportState.data.legendre_order} · std_dev{" "}
                      {exportState.data.std_dev_datasets}/
                      {exportState.data.std_dev_expected} ·{" "}
                      <code>{exportState.data.output_path}</code>
                    </>
                  )}
                </div>
                <OpenmcProvenanceCard
                  provenance={exportState.data.openmc_provenance}
                />
              </div>
            ) : exportState.kind === "error" ? (
              <div className="mt-3 rounded-md border border-rose-300/20 bg-rose-300/[0.06] px-3 py-2 text-[12px] text-rose-100">
                {exportState.message}
              </div>
            ) : null}
          </section>
        ) : null}

        {activePlanState.kind === "ok" ? (
          <OpenmcProductionPathPanel
            state={activePlanState}
            exportState={exportState}
            equivalence={equivalence}
            format={format}
            production={production}
            recipePath={recipePath}
            statepointPath={statepointPath}
            loadStatepoint={loadStatepoint}
            runDir={runDir}
            projectContext={projectContext}
            demo={
              sphDemoPreset && sphDemoMode
                ? {
                    preset: sphDemoPreset,
                    mode: sphDemoMode,
                    onFill: () => applyOpenmcSphDemo(sphDemoPreset),
                    onReview: () => reviewOpenmcSphDemo(sphDemoPreset),
                  }
                : null
            }
          />
        ) : null}

        {equivalence === "sph" ? (
          <details
            id="openmc-sph-summary"
            className="surface mt-6 p-4"
          >
            <summary className="cursor-pointer text-sm font-bold tracking-tight">
              Review an existing SPH physics summary
            </summary>
            <div className="mt-4">
              <OpenmcSphPhysicsSummaryCard
                path={physicsSummaryPath}
                onPathChange={setPhysicsSummaryPath}
                onBrowse={() => setBrowserTarget("summary")}
                autoLoadPath={searchParams.get("summary")}
              />
            </div>
          </details>
        ) : null}
      </div>
    </main>
  );
}

function PlanReport({
  state,
  exportState,
}: {
  state: PlanState;
  exportState: ExportExecutionState;
}) {
  if (state.kind === "idle") {
    return null;
  }
  if (state.kind === "loading") {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
        Building workflow plan…
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section className="glass rounded-xl border-rose-500/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Request failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </section>
    );
  }
  const plan = state.data;
  const sphPrerequisites = openmcSphSidecarCheckFailed(plan)
    ? openmcSphPrerequisiteCommands()
    : [];
  return (
    <div className="space-y-4">
      <section className="glass rounded-xl p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <div
              className={`text-sm font-semibold ${
                plan.ok ? "text-emerald-300" : "text-rose-300"
              }`}
            >
              {plan.ok ? "PLAN READY" : "NEEDS INPUT"}
            </div>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">
              {plan.workflow_label}
            </h2>
          </div>
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {plan.equivalence}
          </span>
        </div>
      </section>

      <OpenmcWorkflowSummary plan={plan} />

      <OpenmcCommandList
        commands={plan.commands}
        primaryCommandText={plan.primary_command_text}
        prerequisites={sphPrerequisites}
      />

      <section className="grid gap-4 lg:grid-cols-2">
        <Cards
          title="Readiness"
          items={plan.checks.map((check) => ({
            key: check.name,
            label: check.name,
            detail: check.message,
            tone: check.status,
            href: isFailedOpenmcSphSidecarCheck(check)
              ? OPENMC_SPH_SIDECAR_FORM_HREF
              : undefined,
            hrefLabel: "Build the SPH sidecar",
          }))}
        />
        <OpenmcArtifactList
          artifacts={plan.artifacts}
          writtenHdf5Path={
            exportState.kind === "ok" && !exportState.data.mock_mode
              ? exportState.data.output_path
              : null
          }
        />
      </section>

      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">Next actions</h2>
        <ul className="mt-2 space-y-1 text-sm text-[var(--fg-1)]">
          {plan.next_actions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Cards({
  title,
  items,
}: {
  title: string;
  items: {
    key: string;
    label: string;
    detail: string;
    tone: string;
    href?: string;
    hrefLabel?: string;
  }[];
}) {
  return (
    <section className="glass rounded-xl p-5">
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div
            key={item.key}
            className="rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium">{item.label}</div>
              <span
                className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${toneClass(
                  item.tone,
                )}`}
              >
                {item.tone}
              </span>
            </div>
            <div className="mt-1 break-all font-mono text-[12px] text-[var(--fg-2)]">
              {item.detail}
            </div>
            {item.href && item.hrefLabel ? (
              <Link
                href={item.href}
                className="mt-1 inline-flex text-[12px] font-medium text-[var(--accent-2)] hover:underline"
              >
                {item.hrefLabel}
              </Link>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  disabled = false,
  onBrowse,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  disabled?: boolean;
  onBrowse?: () => void;
}) {
  const inputId = useId();
  return (
    <div className="block">
      <label
        htmlFor={inputId}
        className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]"
      >
        {label}
      </label>
      <span className="mt-1 flex gap-2">
        <input
          id={inputId}
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className="w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          spellCheck={false}
          autoComplete="off"
        />
        {onBrowse ? (
          <button
            type="button"
            onClick={onBrowse}
            disabled={disabled}
            className="btn btn-secondary shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Browse…
          </button>
        ) : null}
      </span>
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 text-sm text-[var(--fg-1)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
        className="accent-emerald-500"
      />
      <span>{label}</span>
    </label>
  );
}

function toneClass(tone: string): string {
  if (tone === "pass") return "border-emerald-400/30 text-emerald-300";
  if (tone === "warn") return "border-amber-400/30 text-amber-300";
  if (tone === "fail") return "border-rose-400/30 text-rose-300";
  return "border-[var(--edge-bright)] text-[var(--fg-2)]";
}

function sourceModeClass(active: boolean): string {
  return (
    "control-segment px-3 py-2 text-[11px] font-semibold transition " +
    (active
      ? "bg-emerald-300/10 text-emerald-100"
      : "bg-black/10 text-[var(--fg-3)] hover:bg-white/[0.04] hover:text-[var(--fg-1)]")
  );
}

function defaultAsciiPath(base: string, format: ConvertFormat): string {
  const stem = base.trim().replace(/\/$/, "");
  const name = format === "macrolib" ? "out.macrolib.txt" : "out.mcompo.txt";
  return stem ? `${stem}/${name}` : name;
}

function defaultHdf5Path(base: string): string {
  const stem = base.trim().replace(/\/$/, "");
  return stem ? `${stem}/mgxs_library.h5` : "mgxs_library.h5";
}

function openmcBrowserConfig(
  target: BrowserTarget,
  values: {
    recipePath: string;
    statepointPath: string;
    runDir: string;
    keepHdf5Path: string;
    outputPath: string;
    derivedOutput: string;
    adfSource: string;
    sphSource: string;
    physicsSummaryPath: string;
    savedPrefix: string;
    format: ConvertFormat;
  },
): BrowserConfig {
  const baseDir = values.runDir || values.savedPrefix;
  if (target === "recipe") {
    return {
      initialPath: pickBrowserStart(values.recipePath || values.savedPrefix),
      extensions: ["py"],
      fileTypeLabel: "Python recipe",
      chipLabel: "PY",
      recentScope: "openmc-recipe",
    };
  }
  if (target === "statepoint") {
    return {
      initialPath: pickBrowserStart(values.statepointPath || values.savedPrefix),
      extensions: ["h5", "hdf5"],
      fileTypeLabel: "statepoint HDF5",
      chipLabel: "H5",
      recentScope: "openmc-statepoint",
    };
  }
  if (target === "run-dir") {
    return {
      initialPath: values.runDir || values.savedPrefix || "~",
      extensions: [],
      fileTypeLabel: "run",
      chipLabel: "DIR",
      recentScope: "openmc-run-dir",
      selectMode: "directory",
    };
  }
  if (target === "hdf5") {
    return {
      initialPath: pickBrowserStart(values.keepHdf5Path || baseDir),
      extensions: ["h5", "hdf5"],
      fileTypeLabel: "MGXS HDF5",
      chipLabel: "H5",
      recentScope: "openmc-hdf5",
    };
  }
  if (target === "output") {
    const outputSeed = values.outputPath || (baseDir ? values.derivedOutput : "");
    return {
      initialPath: pickBrowserStart(outputSeed),
      extensions:
        values.format === "macrolib" ? ["macrolib.txt"] : ["mcompo.txt"],
      fileTypeLabel: "DONJON ASCII",
      chipLabel: "TXT",
      recentScope: `openmc-output-${values.format}`,
    };
  }
  if (target === "adf") {
    return {
      initialPath: pickBrowserStart(values.adfSource || values.savedPrefix),
      extensions: ["h5", "hdf5"],
      fileTypeLabel: "ADF sidecar",
      chipLabel: "H5",
      recentScope: "openmc-adf",
    };
  }
  if (target === "sph") {
    return {
      initialPath: pickBrowserStart(values.sphSource || values.savedPrefix),
      extensions: ["h5", "hdf5"],
      fileTypeLabel: "SPH sidecar",
      chipLabel: "H5",
      recentScope: "openmc-sph",
    };
  }
  return {
    initialPath: pickBrowserStart(
      values.physicsSummaryPath || values.runDir || values.savedPrefix,
    ),
    extensions: ["json"],
    fileTypeLabel: "OpenMC SPH physics summary",
    chipLabel: "JSON",
    recentScope: "openmc-sph-summary",
  };
}

function pickBrowserStart(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) return "~";
  const lastSlash = trimmed.lastIndexOf("/");
  if (lastSlash >= 0 && lastSlash < trimmed.length - 1) {
    const tail = trimmed.slice(lastSlash + 1);
    if (tail.includes(".")) return trimmed.slice(0, lastSlash + 1);
  }
  return trimmed;
}

function parseOptionalNumber(value: string): number | null | "invalid" {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : "invalid";
}

function toErrorState(err: unknown): Extract<PlanState, { kind: "error" }> {
  if (err instanceof ApiError) {
    return {
      kind: "error",
      status: err.status,
      message: err.detail ?? err.message,
    };
  }
  if (err instanceof Error) return { kind: "error", message: err.message };
  return { kind: "error", message: "Unknown error." };
}
