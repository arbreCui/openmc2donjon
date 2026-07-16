"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import AdfWorkflowPanel from "@/components/AdfWorkflowPanel";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import OpenmcSphWorkflowPanel from "@/components/OpenmcSphWorkflowPanel";
import NativeSphRunner from "@/components/NativeSphRunner";
import OpenmcSphPhysicsSummaryCard from "@/components/openmc/OpenmcSphPhysicsSummaryCard";
import {
  BooleanChoice,
  EQUIVALENCE_KINDS,
  EquivalenceCommandOptions,
  EquivalenceKind,
  buildEquivalenceCli,
  defaultEquivalenceOptions,
  equivalenceKindInfo,
  parseEquivalenceKind,
} from "@/lib/equivalenceCommand";
import { isAdfEquivalenceKind } from "@/lib/adfWorkflow";
import {
  equivalenceAppliedHandoffHref,
  equivalenceConverterReferenceHref,
  equivalenceOperationHref,
  equivalenceRouteHref,
  resolveEquivalenceRoute,
} from "@/lib/equivalenceRoutes";
import {
  OPENMC_SPH_FIXED_POLICY,
  OPENMC_SPH_UPDATE_GATE,
  parseOpenmcSphDamping,
} from "@/lib/openmcSphExecution";
import { equivalenceOptionsForKindSwitch } from "@/lib/equivalenceKindSwitch";
import { isOpenmcSphEquivalenceKind } from "@/lib/openmcSphWorkflow";
import { containingDirectory, outputPathInDirectory } from "@/lib/outputBrowse";
import { useSettings } from "@/lib/settings";
import { WorkflowPageHeader } from "@/components/ui/Workflow";
import { ApiError, api, type SphExecutionResponse } from "@/lib/api";
import type { NativeSphValidationInputs } from "@/lib/nativeSphRunner";
import { colorsetDefinition, isWithdrawnColorsetWorkflow } from "@/lib/colorsetWorkflow";
import {
  colorsetProjectPaths,
  projectRootFromSearchParams,
  type ColorsetProjectPaths,
} from "@/lib/projectWorkspace";

type BrowserTarget =
  | "inputH5"
  | "outputDir"
  | "adfSource"
  | "surfaceFlux"
  | "homogeneousFaceFlux"
  | "referenceFlux"
  | "mgFlux"
  | "previousSph"
  | "sphSource"
  | "macrolib"
  | "tableOutput"
  | "table"
  | "summary";

const SPH_TABLE_OUTPUT_PLACEHOLDER = "openmc_sph.csv";

type SphExecutionState =
  | { kind: "idle" }
  | { kind: "loading"; operation: string }
  | { kind: "ok"; data: SphExecutionResponse }
  | { kind: "error"; message: string };

export default function EquivalencePage() {
  return (
    <Suspense fallback={<EquivalenceLoading />}>
      <EquivalencePageContent />
    </Suspense>
  );
}

function EquivalenceLoading() {
  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading SPH tools…
        </section>
      </div>
    </main>
  );
}

function EquivalencePageContent() {
  const searchParams = useSearchParams();
  const isIrenaColorset = isWithdrawnColorsetWorkflow(
    searchParams.get("colorset"),
    searchParams.get("contract"),
  );
  const selectedRoute = resolveEquivalenceRoute(
    searchParams.get("route"),
    searchParams.has("kind"),
    searchParams.get("contract"),
  );
  const componentId = searchParams.get("component");
  const activeColorset = colorsetDefinition(searchParams.get("colorset"));
  const projectRoot = projectRootFromSearchParams(searchParams);
  const projectPaths = useMemo(
    () => colorsetProjectPaths(isIrenaColorset ? projectRoot : "", activeColorset),
    [activeColorset, isIrenaColorset, projectRoot],
  );
  const kind = parseEquivalenceKind(searchParams.get("kind"));
  const info = equivalenceKindInfo(kind);
  const isPrimarySph =
    kind === "openmc-sph-sidecar" || kind === "apply-sph";
  const isSupportingSph =
    kind === "sph-sidecar" || kind === "augment-sph";
  const [options, setOptions] = useState<EquivalenceCommandOptions>(() =>
    projectEquivalenceOptions(defaultEquivalenceOptions(kind), kind, projectPaths),
  );
  const [outputTouched, setOutputTouched] = useState(Boolean(projectRoot && isIrenaColorset));
  const projectSummaryPath =
    searchParams.get("summary_json") ?? searchParams.get("summary") ?? "";
  const [summaryPath, setSummaryPath] = useState(projectSummaryPath);
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const [executionState, setExecutionState] = useState<SphExecutionState>({ kind: "idle" });
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const firstInputRef = useRef<HTMLInputElement | null>(null);

  // Tab switches reset per-kind fields (output name, modes, clips,
  // summary JSON, force-overwrite) to the incoming kind's defaults so
  // the CLI preview cannot keep targeting the previous tool's artifact;
  // the input path carries over, and switching from a make kind to its
  // augment sibling seeds the sidecar source from the make tab's output.
  useEffect(() => {
    setOptions((current) =>
      projectEquivalenceOptions(
        equivalenceOptionsForKindSwitch(current, kind),
        kind,
        projectPaths,
      ),
    );
    setOutputTouched(Boolean(projectRoot && isIrenaColorset));
    setBrowserTarget(null);
    setExecutionState({ kind: "idle" });
  }, [isIrenaColorset, kind, projectPaths, projectRoot]);

  const activeOptions = useMemo(
    () => ({
      ...options,
      kind,
      outputPath: outputTouched ? options.outputPath : info.outputPlaceholder,
    }),
    [info.outputPlaceholder, kind, options, outputTouched],
  );
  const cli = buildEquivalenceCli(activeOptions);
  const missingOpenmcSphInputs =
    kind === "openmc-sph-sidecar"
      ? [
          ["CE reference flux", options.referenceFlux],
          ["MG macro flux", options.mgFlux],
        ].filter(([, value]) => !value.trim()).map(([label]) => label)
      : [];
  const missingSphSource =
    (kind === "apply-sph" || kind === "augment-sph") && !options.sphSource.trim()
      ? ["SPH sidecar"]
      : [];
  const missingInputs = [
    ...(options.inputH5.trim() ? [] : ["MGXS HDF5"]),
    ...missingOpenmcSphInputs,
    ...missingSphSource,
  ];
  const damping = parseOpenmcSphDamping(options.damping);
  const dampingIssue = kind === "openmc-sph-sidecar" && !damping.ok
    ? damping.message
    : null;
  const commandReady =
    !isIrenaColorset && missingInputs.length === 0 && dampingIssue === null;
  const canUseSavedPrefix =
    settingsHydrated &&
    savedPrefix !== "" &&
    !options.inputH5.startsWith(savedPrefix);
  const nativeConverterHref = equivalenceConverterReferenceHref({
    contract: "native-sph",
    projectRoot,
    componentId,
  });
  const nativeSphValidationInputs: NativeSphValidationInputs = {
    reference_h5: searchParams.get("reference_h5") ?? "",
    reference_macrolib: searchParams.get("reference_macrolib") ?? "",
    sph_macrolib: searchParams.get("sph_macrolib") ?? "",
    verify_macrolib: searchParams.get("verify_macrolib") ?? "",
    result_listing: searchParams.get("result_listing") ?? "",
    execution_deck:
      searchParams.get("execution_deck") ?? searchParams.get("deck") ?? "",
    energy_coverage: searchParams.get("energy_coverage") ?? "",
    converter_receipt: searchParams.get("converter_receipt") ?? "",
    summary_json: searchParams.get("summary_json") ?? "",
  };

  function patch(values: Partial<EquivalenceCommandOptions>) {
    setOptions((current) => ({ ...current, ...values }));
  }

  function applyBrowserPick(path: string) {
    if (browserTarget === "summary") {
      setSummaryPath(path);
    } else if (browserTarget === "outputDir") {
      patch({
        outputPath: outputPathInDirectory(path, activeOptions.outputPath, info.outputPlaceholder),
      });
      setOutputTouched(true);
    } else if (browserTarget === "tableOutput") {
      // The SPH CSV table is an output too: Browse picks the directory
      // and the field keeps (or gains) the filename.
      patch({
        tableOutput: outputPathInDirectory(
          path,
          options.tableOutput,
          SPH_TABLE_OUTPUT_PLACEHOLDER,
        ),
      });
    } else if (browserTarget) {
      patch({ [browserTarget]: path } as Partial<EquivalenceCommandOptions>);
    }
    setBrowserTarget(null);
    firstInputRef.current?.focus();
  }

  async function runSphSidecar() {
    if (isIrenaColorset) {
      setExecutionState({
        kind: "error",
        message:
          "The historical IRENA five-colorset SPH route is withdrawn and cannot compute new factors.",
      });
      return;
    }
    const parsedDamping = parseOpenmcSphDamping(options.damping);
    if (!parsedDamping.ok) {
      setExecutionState({ kind: "error", message: parsedDamping.message });
      return;
    }
    setExecutionState({ kind: "loading", operation: "ratio" });
    try {
      const data = await api.executeSphSidecar({
        strategy: "ratio",
        input_h5: options.inputH5,
        output_path: activeOptions.outputPath,
        reference_flux: options.referenceFlux,
        mg_flux: options.mgFlux,
        previous_sph: options.previousSph || undefined,
        table_output: options.tableOutput || undefined,
        damping: parsedDamping.value,
        flux_normalization: "auto",
        sph_target: "rate",
        zero_flux_policy: "reject",
        flux_floor_rel: null,
        freeze_groups: [],
        clip_min: null,
        clip_max: null,
        summary_json: options.summaryJson.trim() || undefined,
        force: options.force,
      });
      setExecutionState({ kind: "ok", data });
    } catch (error) {
      setExecutionState({ kind: "error", message: executionError(error) });
    }
  }

  async function runApplySph() {
    if (isIrenaColorset) {
      setExecutionState({
        kind: "error",
        message:
          "The historical IRENA five-colorset SPH route is withdrawn and cannot apply factors.",
      });
      return;
    }
    setExecutionState({ kind: "loading", operation: "apply-sph" });
    try {
      const data = await api.executeApplySph({
        input_h5: options.inputH5,
        sph_source: options.sphSource,
        output_path: activeOptions.outputPath,
        input_format: options.sphApplyInputFormat,
        summary_json: options.summaryJson.trim() || undefined,
        force: options.force,
      });
      if (!data.ok || !data.output_path.trim()) {
        throw new Error("apply-sph completed without confirming an output HDF5 path.");
      }
      setExecutionState({ kind: "ok", data });
    } catch (error) {
      setExecutionState({ kind: "error", message: executionError(error) });
    }
  }

  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <WorkflowPageHeader
          step="SPH"
          eyebrow={isIrenaColorset ? `Withdrawn IRENA diagnostic · ${activeColorset.id}` : "Optional physical equivalence"}
          title={isIrenaColorset ? "Review archived five-colorset SPH evidence" : selectedRoute === "native" ? "Run native DRAGON SPH on the declared coarse model" : "Run the optional OpenMC-side CE/MG SPH loop"}
          description={isIrenaColorset ? "This legacy route preserves paths, CLI text, and prior summaries for diagnosis only. It cannot compute or apply factors and cannot advance a production handoff." : selectedRoute === "native" ? "This route consumes a production Converter reference MACROLIB and solves the SPH fixed point in DRAGON. It does not require an OpenMC MG rerun." : "This separate alternate route compares matched OpenMC CE and MG calculations. Its 2% update gate is an iteration gate, never final component or full-core acceptance."}
          input={isIrenaColorset ? "Archived CE/MG paths and SPH summaries" : selectedRoute === "native" ? "Fine reference + production Converter MACROLIB + coarse-model deck" : "Matched OpenMC CE/MG fluxes + Converter-layout HDF5"}
          output={isIrenaColorset ? "No new factors or production artifact" : selectedRoute === "native" ? "Native-SPH MACROLIB + independent acceptance summary" : "OpenMC-side update + SPH-applied HDF5"}
          actions={
            <Link
              href={isIrenaColorset ? "/donjon?mode=irena30-fullcore" : selectedRoute === "native" ? nativeConverterHref : equivalenceRouteHref({ route: "native", projectRoot, componentId })}
              className="btn btn-secondary"
            >
              {isIrenaColorset ? "Open current IRENA route" : selectedRoute === "native" ? "Build production MACROLIB" : "Back to native DRAGON SPH"}
            </Link>
          }
        />

        {!isIrenaColorset ? (
          <EquivalenceRouteChooser
            active={selectedRoute}
            projectRoot={projectRoot}
            componentId={componentId}
          />
        ) : null}

        {!isIrenaColorset && selectedRoute === "native" ? (
          <NativeSphPrimaryRoute
            converterHref={nativeConverterHref}
            projectRoot={projectRoot}
            componentId={componentId ?? ""}
            initialDeckPath={searchParams.get("deck") ?? ""}
            initialWorkingDirectory={searchParams.get("working_directory") ?? ""}
            projectDeclared={searchParams.get("native_sph_source") === "project-manifest"}
            validationInputs={nativeSphValidationInputs}
          />
        ) : null}

        {isIrenaColorset || selectedRoute === "native" ? (
          <OpenmcSphPhysicsSummaryCard
            path={summaryPath}
            onPathChange={setSummaryPath}
            onBrowse={() => setBrowserTarget("summary")}
            autoLoadPath={searchParams.get("summary_json") ?? searchParams.get("summary")}
          />
        ) : null}

        {isIrenaColorset || selectedRoute === "openmc-side" ? <section
          className="mt-5 rounded-xl border border-[var(--edge)] bg-black/10 p-3"
        >
          <h2 className="text-sm font-semibold text-[var(--fg-1)]">
            OpenMC-side CE/MG SPH operations
          </h2>
          <p className="mt-2 text-[12px] leading-5 text-[var(--fg-3)]">
            This is a separate, optional method. It requires a matched OpenMC MG
            rerun after every update and is not a prerequisite for native DRAGON SPH.
          </p>
        <EquivalenceTabs active={kind} colorsetId={isIrenaColorset ? activeColorset.id : null} componentId={componentId} projectRoot={projectRoot} />

        <section className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.045] px-4 py-3 text-[12px] leading-5 text-[var(--fg-2)]">
          {isIrenaColorset ? (
            <>
              <strong className="text-amber-100">WITHDRAWN DIAGNOSTIC ONLY.</strong>{" "}
              The archived IRENA component <strong className="text-[var(--fg-0)]">{activeColorset.id}</strong>{" "}
              may be inspected below, but the five-colorset model cannot establish
              full-core equivalence. Compute/apply actions are disabled even when an
              old bookmark requests production mode.
            </>
          ) : isPrimarySph ? (
            <>
              This optional OpenMC MG-side method computes a rate-preserving update,
              reruns the homogenized MG model, and repeats until its declared residuals
              converge. It is a cross-check or alternate project method, not a required
              step before Converter.
            </>
          ) : isSupportingSph ? (
            <>
              These supporting operations do not derive physical factors. They package or
              attach SPH data that already has an independent provenance.
            </>
          ) : (
            <>
              Select this operation only when it is required by the project&apos;s explicit
              physics contract. Converter itself does not assume a universal correction.
            </>
          )}
        </section>

        <section className="surface p-4 sm:p-5">
          <div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                {info.commandId}
              </div>
              <h2 className="mt-1 text-lg font-semibold tracking-tight">
                {info.title}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
                {info.summary}
              </p>
            </div>
          </div>

          {isOpenmcSphEquivalenceKind(kind) ? (
            <details className="mt-4 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
              <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
                See the complete physical SPH convergence loop
              </summary>
              <OpenmcSphWorkflowPanel activeCommandId={info.commandId} />
            </details>
          ) : null}
          {isAdfEquivalenceKind(kind) ? (
            <AdfWorkflowPanel activeCommandId={info.commandId} />
          ) : null}

          <div className="mt-5 grid gap-4">
            <div className="space-y-4">
              <PathField
                label="MGXS HDF5"
                value={options.inputH5}
                onChange={(value) => patch({ inputH5: value })}
                onBrowse={() => setBrowserTarget("inputH5")}
                placeholder={savedPrefix || "/path/to/mgxs_library.h5"}
                inputRef={firstInputRef}
              />

              {canUseSavedPrefix ? (
                <button
                  type="button"
                  onClick={() => patch({ inputH5: savedPrefix })}
                  className="btn-link"
                >
                  Use saved prefix: <code className="font-mono">{savedPrefix}</code>
                </button>
              ) : null}

              <OutputField
                value={activeOptions.outputPath}
                onChange={(value) => {
                  setOutputTouched(true);
                  patch({ outputPath: value });
                }}
                onBrowse={() => setBrowserTarget("outputDir")}
                placeholder={info.outputPlaceholder}
              />

              {kind === "adf-sidecar" ? (
                <AdfSidecarFields options={options} patch={patch} setBrowserTarget={setBrowserTarget} />
              ) : null}
              {kind === "augment-adf" ? (
                <AugmentAdfFields options={options} patch={patch} setBrowserTarget={setBrowserTarget} />
              ) : null}
              {kind === "openmc-sph-sidecar" ? (
                <OpenmcSphSidecarFields
                  options={options}
                  patch={patch}
                  setBrowserTarget={setBrowserTarget}
                />
              ) : null}
              {kind === "apply-sph" ? (
                <ApplySphFields
                  options={options}
                  patch={patch}
                  setBrowserTarget={setBrowserTarget}
                />
              ) : null}
              {kind === "sph-sidecar" ? (
                <SphSidecarFields options={options} patch={patch} setBrowserTarget={setBrowserTarget} />
              ) : null}
              {kind === "augment-sph" ? (
                <AugmentSphFields options={options} patch={patch} setBrowserTarget={setBrowserTarget} />
              ) : null}

              <details className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
                <summary className="cursor-pointer text-sm font-semibold tracking-tight">
                  Output receipt and overwrite policy
                </summary>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <TextField
                    label="Execution summary JSON"
                    value={options.summaryJson}
                    onChange={(value) => patch({ summaryJson: value })}
                    placeholder="summary.json"
                    mono
                    hint={kind === "openmc-sph-sidecar" || kind === "apply-sph" ? "Optional path written by the same in-app execution request; the response confirms it below." : "Optional machine-readable CLI summary path; this supporting operation is copied and run locally."}
                  />
                  <Toggle
                    label="Force overwrite"
                    description="Append --force so the CLI can replace an existing HDF5 output."
                    checked={options.force}
                    onChange={(force) => patch({ force })}
                  />
                </div>
              </details>
            </div>

            <aside className="h-fit rounded-xl border border-emerald-300/20 bg-emerald-300/[0.055] p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold tracking-tight">
                    {kind === "openmc-sph-sidecar"
                      ? "Run the CE/MG SPH calculation"
                      : kind === "apply-sph"
                        ? "Apply SPH to the cross sections"
                      : kind === "augment-sph"
                        ? "Create the SPH attachment command"
                        : "Create this command"}
                  </h3>
                  <p className="mt-1 text-[12px] text-[var(--fg-3)]">
                    {kind === "openmc-sph-sidecar" || kind === "apply-sph"
                      ? "Run this scoped operation here. The exact CLI remains available for reproducibility."
                      : "Copy this command and run the supporting operation locally."}
                  </p>
                </div>
                <CopyCliButton
                  value={cli}
                  label={
                    kind === "openmc-sph-sidecar"
                      ? commandReady
                        ? "Copy SPH command"
                        : "Fill required inputs first"
                      : "Copy command"
                  }
                  copiedLabel="Command copied"
                  variant="secondary"
                  disabled={!commandReady}
                />
              </div>
              {!commandReady ? (
                <p className="mt-3 text-[12px] text-amber-100">
                  {missingInputs.length > 0 ? `Missing: ${missingInputs.join(", ")}.` : null}
                  {missingInputs.length > 0 && dampingIssue ? " " : null}
                  {dampingIssue ? `Invalid damping: ${dampingIssue}` : null}
                </p>
              ) : null}
              {kind === "openmc-sph-sidecar" ? (
                <div className="mt-3 rounded-lg border border-emerald-300/20 bg-black/10 p-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-200">
                    Run in this app
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={!commandReady || executionState.kind === "loading"}
                      onClick={() => void runSphSidecar()}
                    >
                      {executionState.kind === "loading" && executionState.operation === "ratio"
                        ? "Computing SPH…"
                        : "Compute physical SPH update"}
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] leading-4 text-[var(--fg-3)]">
                    No fitted k-effective scalar is permitted. Factors come only from the paired CE/MG flux fields and the rate-preserving SPH update; both flux files must include uncertainty datasets.
                  </p>
                </div>
              ) : kind === "apply-sph" ? (
                <div className="mt-3 rounded-lg border border-emerald-300/20 bg-black/10 p-3">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!commandReady || executionState.kind === "loading"}
                    onClick={() => void runApplySph()}
                  >
                    {executionState.kind === "loading" ? "Applying SPH…" : "Run apply-sph"}
                  </button>
                </div>
              ) : null}
              {executionState.kind === "ok" ? (
                <div className={
                  "mt-3 rounded-md border px-3 py-2 text-[12px] " +
                  (executionState.data.operation === "sph-sidecar" && executionState.data.converged === false
                    ? "border-amber-300/25 bg-amber-300/[0.06] text-amber-100"
                    : "border-emerald-300/20 bg-emerald-300/[0.06] text-emerald-100")
                }>
                  Wrote {executionState.data.output_path} · {executionState.data.mixtures} mixtures · {executionState.data.energy_groups} groups · SPH {executionState.data.sph_min.toFixed(6)}…{executionState.data.sph_max.toFixed(6)}
                  {executionState.data.max_update_residual != null
                    ? ` · update residual ${(executionState.data.max_update_residual * 100).toFixed(2)}%`
                    : ""}
                  {executionState.data.operation === "sph-sidecar" && executionState.data.converged === false
                    ? " · 2% UPDATE GATE NOT PASSED — rerun OpenMC MG and compute the next update"
                    : executionState.data.operation === "sph-sidecar"
                      ? " · 2% UPDATE GATE PASSED — final physics acceptance is still separate"
                    : ""}
                  {executionState.data.summary_path
                    ? ` · summary ${executionState.data.summary_path}`
                    : ""}
                </div>
              ) : executionState.kind === "error" ? (
                <div className="mt-3 rounded-md border border-rose-300/20 bg-rose-300/[0.06] px-3 py-2 text-[12px] text-rose-100">
                  {executionState.message}
                </div>
              ) : null}
              {executionState.kind === "ok" &&
              executionState.data.operation === "sph-sidecar" &&
              executionState.data.converged === false ? (
                <div className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/[0.05] p-3">
                  <p className="text-[11px] leading-5 text-amber-100/85">
                    Before the next update, apply this sidecar to the OpenMC MG
                    colorset, rerun that MG model, and replace the MG flux field
                    above with the new statepoint export. Reusing the old MG flux
                    is not an iteration.
                  </p>
                  <button
                    type="button"
                    className="btn btn-secondary mt-2"
                    onClick={() => {
                      patch({
                        previousSph: executionState.data.output_path,
                        outputPath: nextSphIterationPath(executionState.data.output_path),
                      });
                      setOutputTouched(true);
                      setExecutionState({ kind: "idle" });
                    }}
                  >
                    Set up the next SPH update
                  </button>
                </div>
              ) : null}
              <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
                <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
                  Review exact CLI and physics caution
                </summary>
                <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
                  {cli}
                </pre>
                <div className="mt-3 rounded-md border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-[12px] leading-relaxed text-amber-100">
                  SPH factors are physics inputs. This builder prevents flag mistakes; acceptance still depends on the CE/MG comparison.
                </div>
              </details>
              {kind === "openmc-sph-sidecar" &&
              executionState.kind === "ok" &&
              executionState.data.operation === "sph-sidecar" &&
              executionState.data.converged === true ? (
                <Link
                  href={equivalenceOperationHref({
                    kind: "apply-sph",
                    projectRoot,
                    componentId,
                    colorsetId: isIrenaColorset ? activeColorset.id : null,
                  })}
                  className="mt-3 inline-flex text-[12px] font-semibold text-[var(--accent-2)] hover:underline"
                >
                  After convergence and independent validation: apply SPH →
                </Link>
              ) : null}
              {kind === "apply-sph" &&
              executionState.kind === "ok" &&
              executionState.data.operation === "apply-sph" &&
              executionState.data.output_path.trim() ? (
                <Link
                  href={equivalenceAppliedHandoffHref({
                    inputH5: executionState.data.output_path,
                    projectRoot,
                    componentId,
                  })}
                  className="mt-3 inline-flex text-[12px] font-semibold text-[var(--accent-2)] hover:underline"
                >
                  Output confirmed — continue with this HDF5 in Converter →
                </Link>
              ) : null}
            </aside>
          </div>
        </section>
        </section> : null}

        <FileBrowserModal
          open={browserTarget != null}
          initialPath={browserInitialPath(browserTarget, activeOptions, savedPrefix, summaryPath)}
          extensions={browserExtensions(browserTarget)}
          fileTypeLabel={isOutputTarget(browserTarget) ? "output directory" : browserTarget === "summary" ? "SPH physics summary" : "input file"}
          chipLabel={isOutputTarget(browserTarget) ? "DIR" : browserChip(browserTarget)}
          recentScope={`equivalence-${browserTarget ?? "file"}`}
          selectMode={isOutputTarget(browserTarget) ? "directory" : "file"}
          onClose={() => setBrowserTarget(null)}
          onSelect={applyBrowserPick}
        />
      </div>
    </main>
  );
}

function EquivalenceRouteChooser({
  active,
  projectRoot,
  componentId,
}: {
  active: "native" | "openmc-side";
  projectRoot: string;
  componentId: string | null;
}) {
  const routes = [
    {
      id: "native" as const,
      eyebrow: "DRAGON coarse-model solve",
      title: "Native DRAGON SPH",
      body: "Converter reference MACROLIB → DRAGON SPH fixed point → DONJON verification. No OpenMC MG rerun is required.",
      badge: "Primary route",
    },
    {
      id: "openmc-side" as const,
      eyebrow: "Matched CE/MG alternate method",
      title: "OpenMC-side CE/MG SPH",
      body: "Compare matched OpenMC CE and MG fluxes, apply the update, and rerun MG until the 2% update gate passes.",
      badge: "Optional route",
    },
  ];
  return (
    <nav className="mb-5 grid gap-3 md:grid-cols-2" aria-label="SPH physical route">
      {routes.map((route) => (
        <Link
          key={route.id}
          href={equivalenceRouteHref({
            route: route.id,
            projectRoot,
            componentId,
          })}
          aria-current={active === route.id ? "page" : undefined}
          className={
            "rounded-xl border p-4 transition " +
            (active === route.id
              ? "border-emerald-300/40 bg-emerald-300/[0.09]"
              : "border-[var(--edge)] bg-white/[0.02] hover:border-[var(--edge-bright)]")
          }
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">
              {route.eyebrow}
            </span>
            <span className="rounded-full border border-[var(--edge)] px-2 py-1 text-[9px] text-[var(--fg-2)]">
              {route.badge}
            </span>
          </div>
          <h2 className="mt-2 text-base font-bold text-[var(--fg-0)]">{route.title}</h2>
          <p className="mt-2 text-[11px] leading-5 text-[var(--fg-3)]">{route.body}</p>
        </Link>
      ))}
    </nav>
  );
}

function NativeSphPrimaryRoute({
  converterHref,
  projectRoot,
  componentId,
  initialDeckPath,
  initialWorkingDirectory,
  projectDeclared,
  validationInputs,
}: {
  converterHref: string;
  projectRoot: string;
  componentId: string;
  initialDeckPath: string;
  initialWorkingDirectory: string;
  projectDeclared: boolean;
  validationInputs: NativeSphValidationInputs;
}) {
  const stages = [
    {
      number: "1",
      title: "OpenMC fine reference",
      body: "Run the actual fine geometry and preserve energy coverage, volume-integrated flux, reaction rates, and keff uncertainty. The model may be one assembly, a colorset, or another declared domain set.",
    },
    {
      number: "2",
      title: "Converter reference",
      body: "Collapse only the domains declared by this model, preserve rates and flux integrals, then write the uncorrected reference MACROLIB. Converter remains the formal handoff boundary.",
    },
    {
      number: "3",
      title: "DRAGON native SPH",
      body: "Solve SPH: on the user's coarse geometry with SN or SPN. No ADF, clipping, frozen groups, flux floors, or fitted global eigenvalue coefficient is allowed.",
    },
    {
      number: "4",
      title: "DONJON verification",
      body: "Verify convergence, rate balance, energy coverage, and keff against the OpenMC statistical uncertainty. Component closure and full-core acceptance remain distinct decisions.",
    },
  ] as const;
  return (
    <section className="rounded-xl border border-emerald-300/25 bg-emerald-300/[0.055] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.15em] text-emerald-200">
            Primary physical route
          </div>
          <h2 className="mt-1 text-lg font-bold tracking-tight">
            Converter first; native SPH on the real coarse model
          </h2>
        </div>
        <span className="rounded-full border border-emerald-200/25 px-2 py-1 font-mono text-[9px] uppercase text-emerald-100">
          OpenMC MG optional
        </span>
      </div>
      <div className="mt-4 grid gap-2 lg:grid-cols-4">
        {stages.map((stage) => (
          <article key={stage.number} className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
            <div className="flex items-center gap-2">
              <span className="step-dot">{stage.number}</span>
              <h3 className="text-[12px] font-bold text-[var(--fg-0)]">{stage.title}</h3>
            </div>
            <p className="mt-2 text-[10px] leading-4 text-[var(--fg-3)]">{stage.body}</p>
          </article>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href={converterHref} className="btn btn-primary">
          Build Converter reference
        </Link>
        <Link href="/projects" className="btn btn-secondary">
          Coordinate in Project (optional)
        </Link>
      </div>
      <p className="mt-3 text-[11px] leading-5 text-[var(--fg-3)]">
        The native <span className="font-mono">SPH:</span> deck belongs to the
        user-declared coarse geometry (or the project manifest when one is in
        use). A generic DONJON eigenvalue smoke deck cannot replace that
        fixed-point solve.
      </p>
      <NativeSphRunner
        projectRoot={projectRoot}
        componentId={componentId}
        initialDeckPath={initialDeckPath}
        initialWorkingDirectory={initialWorkingDirectory}
        projectDeclared={projectDeclared}
        validationInputs={validationInputs}
      />
    </section>
  );
}

function projectEquivalenceOptions(
  options: EquivalenceCommandOptions,
  kind: EquivalenceKind,
  paths: ColorsetProjectPaths,
): EquivalenceCommandOptions {
  if (!paths.directory) return options;
  if (kind === "openmc-sph-sidecar") {
    return {
      ...options,
      inputH5: paths.mgxs,
      outputPath: paths.sphSidecar,
      referenceFlux: `${paths.ceFlux}::openmc_volume_flux`,
      mgFlux: `${paths.mgFlux}::openmc_mg_flux`,
      tableOutput: paths.sphSidecar.replace(/\.h5$/i, ".csv"),
    };
  }
  if (kind === "apply-sph") {
    return {
      ...options,
      inputH5: paths.mgxs,
      outputPath: paths.sphApplied,
      sphSource: paths.sphSidecar,
    };
  }
  return { ...options, inputH5: paths.mgxs };
}

function EquivalenceTabs({
  active,
  colorsetId,
  componentId,
  projectRoot,
}: {
  active: EquivalenceKind;
  colorsetId: string | null;
  componentId: string | null;
  projectRoot: string;
}) {
  const mainKinds = EQUIVALENCE_KINDS.filter(
    (item) => item.kind === "openmc-sph-sidecar" || item.kind === "apply-sph",
  );
  const supportingKinds = EQUIVALENCE_KINDS.filter(
    (item) => item.kind === "sph-sidecar" || item.kind === "augment-sph",
  );
  return (
    <details className="mb-5 rounded-xl border border-[var(--edge)] bg-black/10 p-3">
      <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
        Switch SPH operation · current: {equivalenceKindInfo(active).label}
      </summary>
      <nav className="mt-3 grid gap-2 md:grid-cols-2" aria-label="SPH tool">
        {mainKinds.map((item, index) => (
          <Link
            key={item.kind}
            href={equivalenceOperationHref({
              kind: item.kind,
              projectRoot,
              componentId,
              colorsetId,
            })}
            className={equivalenceTabClass(active === item.kind)}
            aria-current={active === item.kind ? "page" : undefined}
          >
            <div className="flex items-center gap-2">
              <span className="step-dot h-6 w-6 text-[9px]">{index + 1}</span>
              <span className="text-sm font-semibold tracking-tight">{item.label}</span>
            </div>
            <div className="mt-2 font-mono text-[10px] text-[var(--fg-3)]">
              {item.commandId}
            </div>
          </Link>
        ))}
      </nav>

      <details className="mt-3 rounded-xl border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-3)]">
          Supporting SPH record tools
        </summary>
        <nav className="mt-3 grid gap-2 md:grid-cols-2" aria-label="Supporting SPH tool">
          {supportingKinds.map((item) => (
            <Link
              key={item.kind}
              href={equivalenceOperationHref({
                kind: item.kind,
                projectRoot,
                componentId,
                colorsetId,
              })}
              className={equivalenceTabClass(active === item.kind)}
              aria-current={active === item.kind ? "page" : undefined}
            >
              <div className="text-sm font-semibold tracking-tight">{item.label}</div>
              <div className="mt-1 font-mono text-[10px] text-[var(--fg-3)]">
                {item.commandId}
              </div>
            </Link>
          ))}
        </nav>
      </details>
    </details>
  );
}

function equivalenceTabClass(active: boolean): string {
  return (
    "rounded-xl border px-3 py-3 transition " +
    (active
      ? "border-emerald-300/35 bg-emerald-300/[0.09] text-emerald-100 shadow-[0_8px_24px_rgba(47,201,133,0.07)]"
      : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)] hover:border-[var(--edge-bright)] hover:text-[var(--fg-0)]")
  );
}

function AdfSidecarFields({
  options,
  patch,
  setBrowserTarget,
}: FieldGroupProps) {
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold tracking-tight">ADF sidecar options</h3>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <SelectField
          label="Mode"
          value={options.adfMode}
          onChange={(value) => patch({ adfMode: value as "unity" | "flux-ratio" })}
          options={[
            ["unity", "unity"],
            ["flux-ratio", "flux-ratio"],
          ]}
          hint="Unity is for plumbing; flux-ratio uses face-flux inputs."
        />
        <TextField
          label="Faces"
          value={options.faces}
          onChange={(value) => patch({ faces: value })}
          placeholder="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"
          mono
          hint="Comma-separated face names expected by the sidecar."
        />
        {options.adfMode === "unity" ? (
          <TextField
            label="Unity value"
            value={options.adfValue}
            onChange={(value) => patch({ adfValue: value })}
            placeholder="1.0"
            mono
            hint="Constant ADF value for every face/group/bin."
          />
        ) : (
          <>
            <PathField
              label="Heterogeneous face flux"
              value={options.surfaceFlux}
              onChange={(value) => patch({ surfaceFlux: value })}
              onBrowse={() => setBrowserTarget("surfaceFlux")}
              placeholder="face_flux.h5"
            />
            <PathField
              label="Homogeneous face flux"
              value={options.homogeneousFaceFlux}
              onChange={(value) => patch({ homogeneousFaceFlux: value })}
              onBrowse={() => setBrowserTarget("homogeneousFaceFlux")}
              placeholder="homogeneous_face_flux.h5"
            />
            <TextField
              label="Invalid fill"
              value={options.invalidFill}
              onChange={(value) => patch({ invalidFill: value })}
              placeholder="1.0"
              mono
              hint="Optional positive fill value for invalid ADF bins."
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                label="Clip min"
                value={options.clipMin}
                onChange={(value) => patch({ clipMin: value })}
                placeholder="0.2"
                mono
                hint="Optional lower clamp."
              />
              <TextField
                label="Clip max"
                value={options.clipMax}
                onChange={(value) => patch({ clipMax: value })}
                placeholder="5.0"
                mono
                hint="Optional upper clamp."
              />
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function AugmentAdfFields({
  options,
  patch,
  setBrowserTarget,
}: FieldGroupProps) {
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold tracking-tight">ADF augmentation options</h3>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <PathField
          label="ADF sidecar"
          value={options.adfSource}
          onChange={(value) => patch({ adfSource: value })}
          onBrowse={() => setBrowserTarget("adfSource")}
          placeholder="adf_sidecar.h5"
        />
        <TextField
          label="Expected faces"
          value={options.faces}
          onChange={(value) => patch({ faces: value })}
          placeholder="FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX"
          mono
          hint="Optional consistency check against the sidecar face names."
        />
      </div>
    </section>
  );
}

function SphSidecarFields({
  options,
  patch,
  setBrowserTarget,
}: FieldGroupProps) {
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold tracking-tight">SPH sidecar options</h3>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <SelectField
          label="Mode"
          value={options.sphMode}
          onChange={(value) => patch({ sphMode: value as "unity" | "macrolib" | "table" })}
          options={[
            ["unity", "unity"],
            ["macrolib", "macrolib NSPH"],
            ["table", "CSV table"],
          ]}
          hint="Choose where NSPH factors come from."
        />
        {options.sphMode === "unity" ? (
          <TextField
            label="Unity value"
            value={options.sphValue}
            onChange={(value) => patch({ sphValue: value })}
            placeholder="1.0"
            mono
            hint="Constant SPH factor for every mixture/group."
          />
        ) : null}
        {options.sphMode === "macrolib" ? (
          <PathField
            label="MACROLIB ASCII"
            value={options.macrolib}
            onChange={(value) => patch({ macrolib: value })}
            onBrowse={() => setBrowserTarget("macrolib")}
            placeholder="donjon.macrolib.txt"
          />
        ) : null}
        {options.sphMode === "table" ? (
          <PathField
            label="SPH CSV table"
            value={options.table}
            onChange={(value) => patch({ table: value })}
            onBrowse={() => setBrowserTarget("table")}
            placeholder="sph.csv"
          />
        ) : null}
      </div>
    </section>
  );
}

function OpenmcSphSidecarFields({
  options,
  patch,
  setBrowserTarget,
}: FieldGroupProps) {
  const damping = parseOpenmcSphDamping(options.damping);
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold tracking-tight">OpenMC CE/MG SPH options</h3>
      <p className="mt-1 text-[12px] leading-relaxed text-[var(--fg-3)]">
        Use fluxes from the same OpenMC geometry and output regions: CE is the reference;
        MG is the macro calculation being corrected.
      </p>
      <div className="mt-3 rounded-md border border-emerald-300/20 bg-emerald-300/[0.055] px-3 py-2 text-[12px] leading-5 text-emerald-100">
        Physics-preserving production rules are active: rate target, power
        normalization, zero-bin rejection, uncertainty gates, and no frozen
        groups, flux floors, clipping, or k-effective fitting.
        No k-effective fitting or global empirical multiplier is allowed. For rate
        SPH, the fixed point enforces Σ′φMG = ΣφCE with Σ′ = Σ/NSPH. Re-run the MG
        model with each updated sidecar and repeat until the raw update residual is
        within the declared convergence tolerance before handing factors to Converter.
      </div>
      <div className="mt-3 rounded-md border border-amber-300/25 bg-amber-300/[0.06] px-3 py-2 text-[12px] leading-5 text-amber-100">
        <strong>Iteration gate: raw update residual ≤ {(OPENMC_SPH_UPDATE_GATE * 100).toFixed(0)}%.</strong>{" "}
        Passing this gate only permits the next handoff step. It does not establish
        component closure, full-core equivalence, or final physics acceptance.
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <PathField
          label="OpenMC CE reference flux"
          value={options.referenceFlux}
          onChange={(value) => patch({ referenceFlux: value })}
          onBrowse={() => setBrowserTarget("referenceFlux")}
          placeholder="openmc_ce_flux.h5::openmc_volume_flux"
        />
        <PathField
          label="OpenMC MG macro flux"
          value={options.mgFlux}
          onChange={(value) => patch({ mgFlux: value })}
          onBrowse={() => setBrowserTarget("mgFlux")}
          placeholder="openmc_mg_flux.h5::openmc_mg_flux"
        />
      </div>
      <div className="mt-4 rounded-md border border-[var(--edge)] bg-black/10 p-3">
        <h4 className="text-[12px] font-semibold tracking-tight text-[var(--fg-2)]">
          Fixed physical policy (read-only)
        </h4>
        <dl className="mt-3 grid gap-2 sm:grid-cols-2">
          {OPENMC_SPH_FIXED_POLICY.map(([label, value]) => (
            <div key={label} className="rounded-md border border-[var(--edge)] bg-white/[0.015] px-3 py-2">
              <dt className="text-[10px] uppercase tracking-wide text-[var(--fg-3)]">{label}</dt>
              <dd className="mt-1 text-[11px] font-semibold text-[var(--fg-1)]">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-3">
        <PathField
          label="SPH CSV table"
          value={options.tableOutput}
          onChange={(value) => patch({ tableOutput: value })}
          onBrowse={() => setBrowserTarget("tableOutput")}
          placeholder={SPH_TABLE_OUTPUT_PLACEHOLDER}
          browseLabel="Browse dir…"
        />
        </div>
      </div>
      <details className="mt-4 rounded-md border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer text-[12px] font-semibold tracking-tight">
          Convergence iteration (required for production)
        </summary>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <PathField
            label="Previous SPH"
            value={options.previousSph}
            onChange={(value) => patch({ previousSph: value })}
            onBrowse={() => setBrowserTarget("previousSph")}
            placeholder="previous_sph.csv or previous_sph.h5"
          />
          <TextField
            label="Damping"
            value={options.damping}
            onChange={(value) => patch({ damping: value })}
            placeholder="1.0"
            mono
            hint="Required finite value in 0..1. Invalid input blocks execution; it never falls back silently."
          />
          {damping.ok ? null : (
            <p className="text-[11px] text-rose-200">
              {damping.message}
            </p>
          )}
        </div>
      </details>
    </section>
  );
}

function AugmentSphFields({
  options,
  patch,
  setBrowserTarget,
}: FieldGroupProps) {
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold tracking-tight">SPH augmentation options</h3>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <PathField
          label="SPH sidecar"
          value={options.sphSource}
          onChange={(value) => patch({ sphSource: value })}
          onBrowse={() => setBrowserTarget("sphSource")}
          placeholder="sph_sidecar.h5"
        />
        <SelectField
          label="SPH already applied"
          value={options.sphApplied}
          onChange={(value) => patch({ sphApplied: value as BooleanChoice })}
          options={[
            ["", "not specified"],
            ["false", "false"],
            ["true", "true"],
          ]}
          hint="Usually false: the converter records factors but does not apply them."
        />
      </div>
    </section>
  );
}

function ApplySphFields({
  options,
  patch,
  setBrowserTarget,
}: FieldGroupProps) {
  return (
    <section className="rounded-lg border border-emerald-300/20 bg-emerald-300/[0.035] p-4">
      <h3 className="text-sm font-semibold tracking-tight">Apply converged physical SPH factors</h3>
      <p className="mt-1 text-[12px] leading-relaxed text-[var(--fg-3)]">
        The main DONJON handoff uses converter-layout HDF5. This command divides
        macroscopic cross sections by NSPH and records applied-SPH provenance.
      </p>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <PathField
          label="Converged SPH sidecar"
          value={options.sphSource}
          onChange={(value) => patch({ sphSource: value })}
          onBrowse={() => setBrowserTarget("sphSource")}
          placeholder="openmc_sph.h5"
        />
        <SelectField
          label="Input HDF5 layout"
          value={options.sphApplyInputFormat}
          onChange={(value) =>
            patch({
              sphApplyInputFormat: value as "converter" | "openmc-mgxs",
            })
          }
          options={[
            ["converter", "converter handoff (main route)"],
            ["openmc-mgxs", "OpenMC native MGXS (MG rerun only)"],
          ]}
          hint="Keep converter for the HDF5 passed to Converter. Use openmc-mgxs only when preparing another OpenMC MG iteration."
        />
      </div>
    </section>
  );
}

interface FieldGroupProps {
  options: EquivalenceCommandOptions;
  patch: (values: Partial<EquivalenceCommandOptions>) => void;
  setBrowserTarget: (target: BrowserTarget) => void;
}

function PathField({
  label,
  value,
  onChange,
  onBrowse,
  placeholder,
  inputRef,
  browseLabel = "Browse…",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
  placeholder: string;
  inputRef?: React.Ref<HTMLInputElement>;
  browseLabel?: string;
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </span>
      <div className="mt-1 grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
          spellCheck={false}
          autoComplete="off"
        />
        <button type="button" onClick={onBrowse} className="btn btn-secondary">
          {browseLabel}
        </button>
      </div>
    </label>
  );
}

function OutputField({
  value,
  onChange,
  onBrowse,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
  placeholder: string;
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        Output HDF5
      </span>
      <div className="mt-1 grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
          spellCheck={false}
          autoComplete="off"
        />
        <button type="button" onClick={onBrowse} className="btn btn-secondary">
          Browse dir…
        </button>
      </div>
      <span className="mt-1 block text-[12px] text-[var(--fg-3)]">
        Choose a directory with Browse, then edit the filename if needed.
      </span>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  mono = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  hint: string;
  mono?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </span>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={
          "mt-1 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none " +
          (mono ? "font-mono" : "")
        }
        spellCheck={false}
        autoComplete="off"
      />
      <span className="mt-1 block text-[12px] text-[var(--fg-3)]">{hint}</span>
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly (readonly [string, string])[];
  hint: string;
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-md border border-[var(--edge)] bg-[var(--bg-1)] px-3 py-2 text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
      >
        {options.map(([optionValue, label]) => (
          <option key={optionValue} value={optionValue}>
            {label}
          </option>
        ))}
      </select>
      <span className="mt-1 block text-[12px] text-[var(--fg-3)]">{hint}</span>
    </label>
  );
}

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2 rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 text-sm text-[var(--fg-1)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 accent-emerald-500"
      />
      <span className="min-w-0">
        <span className="block text-[var(--fg-0)]">{label}</span>
        <span className="mt-0.5 block text-[12px] leading-snug text-[var(--fg-3)]">
          {description}
        </span>
      </span>
    </label>
  );
}

/** Output-path targets browse for a directory rather than an existing file. */
function isOutputTarget(target: BrowserTarget | null): boolean {
  return target === "outputDir" || target === "tableOutput";
}

function browserInitialPath(
  target: BrowserTarget | null,
  options: EquivalenceCommandOptions,
  savedPrefix: string,
  summaryPath: string,
): string {
  const value = browserTargetValue(target, options, summaryPath);
  return containingDirectory(value || savedPrefix || "~");
}

function browserTargetValue(
  target: BrowserTarget | null,
  options: EquivalenceCommandOptions,
  summaryPath: string,
): string {
  if (target == null) return "";
  const values: Record<BrowserTarget, string> = {
    inputH5: options.inputH5,
    outputDir: options.outputPath,
    adfSource: options.adfSource,
    surfaceFlux: options.surfaceFlux,
    homogeneousFaceFlux: options.homogeneousFaceFlux,
    referenceFlux: options.referenceFlux,
    mgFlux: options.mgFlux,
    previousSph: options.previousSph,
    sphSource: options.sphSource,
    macrolib: options.macrolib,
    tableOutput: options.tableOutput,
    table: options.table,
    summary: summaryPath,
  };
  return values[target];
}

function browserExtensions(target: BrowserTarget | null): readonly string[] {
  if (isOutputTarget(target)) return [];
  if (target === "table") return ["csv"];
  if (target === "previousSph") return ["h5", "hdf5", "csv"];
  if (target === "macrolib") return ["txt", "mco"];
  if (target === "summary") return ["json"];
  return ["h5", "hdf5"];
}

function browserChip(target: BrowserTarget | null): string {
  if (target === "table") return "CSV";
  if (target === "macrolib") return "TXT";
  if (target === "summary") return "JSON";
  return "H5";
}

function nextSphIterationPath(path: string): string {
  const trimmed = path.trim() || "openmc_sph.h5";
  const numbered = trimmed.match(/^(.*?)(?:[_-]iter)(\d+)(\.h(?:df)?5)$/i);
  if (numbered) {
    const next = String(Number(numbered[2]) + 1).padStart(numbered[2].length, "0");
    return `${numbered[1]}_iter${next}${numbered[3]}`;
  }
  return trimmed.replace(/(\.h(?:df)?5)$/i, "_iter02$1");
}

function executionError(error: unknown): string {
  if (error instanceof ApiError) return error.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return "Execution failed";
}
