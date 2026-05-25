"use client";

import Link from "next/link";
import {
  FormEvent,
  type RefObject,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";
import ConvertReport, {
  ConvertRunState,
} from "@/components/convert/ConvertReport";
import ConvertShowcase from "@/components/convert/ConvertShowcase";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import MixturePicker from "@/components/convert/MixturePicker";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  api,
} from "@/lib/api";
import type { ConvertFormat } from "@/lib/api";
import {
  buildConvertCliPreview,
  convertAdvancedPayload,
} from "@/lib/convertCommand";
import {
  C5G7_PRODUCTION_DEMO,
  PRODUCTION_MINICASE_ARTIFACTS,
  PRODUCTION_MINICASE_COMMAND,
  PRODUCTION_MINICASE_DEMO,
  convertDemoBundleHref,
  convertDemoPreviewHref,
  convertDemoRequest,
  convertDemoWalkthrough,
  isProductionMinicasePath,
  productionMinicaseAvailability,
  type ConvertDemoArtifactRole,
  type ProductionMinicaseAvailabilityTone,
} from "@/lib/convertDemo";
import { convertIntentCopy } from "@/lib/convertIntent";
import type { ConvertIntentCopy } from "@/lib/convertIntent";
import {
  convertModeReference,
  type ConvertModeReferenceItem,
} from "@/lib/convertModeReference";
import {
  defaultConvertOutputPath,
  outputPathInDirectory,
  pickConvertBrowserStart,
} from "@/lib/convertPaths";
import {
  convertBundleBuilderHrefFromPaths,
  convertWorkflowStageSummary,
  convertWalkthroughStatuses,
  type ConvertWorkflowStageStatus,
  type ConvertWalkthroughRun,
  type ConvertWalkthroughStatus,
} from "@/lib/convertWalkthrough";
import { convertShowcaseDefaultOpen } from "@/lib/convertShowcase";
import {
  fileStatusLabel,
  fileStatusTone,
  type FileStatusState,
} from "@/lib/fileStatus";
import { useSettings } from "@/lib/settings";
import { parseConvertFormat, queryFlag } from "@/lib/workflowQuery";

const FALLBACK_INPUT = "/path/to/mgxs_library.h5";
type BrowserTarget = "input" | "output-directory";
type ArtifactStatusMap = Record<string, FileStatusState>;

export default function ConvertPage() {
  return (
    <Suspense fallback={<ConvertLoading />}>
      <ConvertPageContent />
    </Suspense>
  );
}

function ConvertLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading converter…
        </section>
      </div>
    </main>
  );
}

function ConvertPageContent() {
  const searchParams = useSearchParams();
  const intent = convertIntentCopy(searchParams.get("intent"));
  const queryInput = searchParams.get("input");
  const queryOutput = searchParams.get("output");
  const queryFormat = parseConvertFormat(searchParams.get("format"));
  const queryCheck = queryFlag(searchParams, "check", true);
  const queryProduction = queryFlag(searchParams, "production", false);
  const queryRequireKnownMesh = queryFlag(
    searchParams,
    "require_known_mesh",
    false,
  );
  const queryComment = searchParams.get("comment");
  const queryHasPrefill =
    queryInput !== null ||
    queryOutput !== null ||
    searchParams.get("format") !== null ||
    searchParams.get("check") !== null ||
    searchParams.get("production") !== null ||
    searchParams.get("require_known_mesh") !== null ||
    queryComment !== null;
  const [inputPath, setInputPath] = useState(queryInput ?? "");
  const [outputPath, setOutputPath] = useState(queryOutput ?? "");
  const [format, setFormat] = useState<ConvertFormat>(queryFormat);
  const [check, setCheck] = useState(queryCheck);
  const [production, setProduction] = useState(queryProduction);
  const [requireKnownMesh, setRequireKnownMesh] = useState(queryRequireKnownMesh);
  const [overwrite, setOverwrite] = useState(false);
  const [rootName, setRootName] = useState("CPO");
  const [comment, setComment] = useState(queryComment ?? "");
  const [burnup, setBurnup] = useState("");
  const [hFactorDefault, setHFactorDefault] = useState("");
  const [mixturesText, setMixturesText] = useState("");
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const [outputTouched, setOutputTouched] = useState(queryOutput !== null);
  const [state, setState] = useState<ConvertRunState>({ kind: "idle" });
  const [mockMode, setMockMode] = useState(false);
  const convertButtonRef = useRef<HTMLButtonElement | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const inputPlaceholder = savedPrefix || FALLBACK_INPUT;
  const derivedOutput = useMemo(
    () => defaultConvertOutputPath(inputPath, format),
    [inputPath, format],
  );
  const displayedOutput = outputTouched ? outputPath : derivedOutput;
  const canUseSavedPrefix =
    settingsHydrated &&
    savedPrefix !== "" &&
    !inputPath.startsWith(savedPrefix);
  const cliPreview = buildConvertCliPreview({
    inputPath,
    outputPath: displayedOutput,
    format,
    check,
    production,
    warnUnknownEnergyMesh: true,
    requireKnownEnergyMesh: requireKnownMesh,
    rootName,
    comment,
    burnup,
    hFactorDefault,
    mixturesText,
  });
  const showMinicaseMissingHint =
    !mockMode &&
    state.kind === "error" &&
    state.status === 404 &&
    (isProductionMinicasePath(inputPath) ||
      isProductionMinicasePath(displayedOutput));
  const preflightInput = state.kind === "ok" ? state.data.preflight?.inputs[0] ?? null : null;
  const c5g7DemoDryRunPassed = isC5g7DemoDryRunPassed(state);
  const c5g7DemoConverted = isC5g7DemoConverted(state);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((health) => {
        if (!cancelled) setMockMode(health.mock_mode);
      })
      .catch(() => {
        if (!cancelled) setMockMode(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!queryHasPrefill) return;
    setFormat(queryFormat);
    setCheck(queryCheck);
    setProduction(queryProduction);
    setRequireKnownMesh(queryRequireKnownMesh);
    if (queryInput !== null) {
      setInputPath(queryInput);
    }
    if (queryOutput !== null) {
      setOutputPath(queryOutput);
      setOutputTouched(true);
    } else if (queryInput !== null) {
      setOutputPath(defaultConvertOutputPath(queryInput, queryFormat));
      setOutputTouched(false);
    }
    if (queryComment !== null) {
      setComment(queryComment);
    }
    setState({ kind: "idle" });
  }, [
    queryCheck,
    queryComment,
    queryFormat,
    queryHasPrefill,
    queryInput,
    queryOutput,
    queryProduction,
    queryRequireKnownMesh,
  ]);

  function updateInput(value: string) {
    setInputPath(value);
    if (!outputTouched) setOutputPath(defaultConvertOutputPath(value, format));
  }

  function updateFormat(value: ConvertFormat) {
    setFormat(value);
    if (!outputTouched) setOutputPath(defaultConvertOutputPath(inputPath, value));
  }

  function applyC5g7Demo() {
    applyDemoPreset(C5G7_PRODUCTION_DEMO, "C5G7 mock production demo");
    setState({ kind: "idle" });
  }

  function applyProductionMinicaseDemo() {
    applyDemoPreset(PRODUCTION_MINICASE_DEMO, "production minicase web repeat");
    setState({ kind: "idle" });
  }

  function applyDemoPreset(
    preset: typeof C5G7_PRODUCTION_DEMO,
    demoComment: string,
  ) {
    updateInput(preset.inputPath);
    setOutputPath(preset.outputPath);
    setOutputTouched(true);
    setFormat(preset.format);
    setCheck(preset.check);
    setProduction(preset.production);
    setRequireKnownMesh(preset.requireKnownMesh);
    setOverwrite(false);
    setRootName("CPO");
    setComment(demoComment);
    setBurnup("");
    setHFactorDefault("");
    setMixturesText("");
  }

  async function runC5g7DemoDryRun() {
    const demoComment = "C5G7 mock production demo";
    applyDemoPreset(C5G7_PRODUCTION_DEMO, demoComment);
    setState({ kind: "loading", mode: "dry-run" });
    try {
      const data = await api.convert(
        convertDemoRequest(C5G7_PRODUCTION_DEMO, {
          dryRun: true,
          comment: demoComment,
        }),
      );
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  async function runC5g7DemoConvert() {
    const demoComment = "C5G7 mock production demo";
    applyDemoPreset(C5G7_PRODUCTION_DEMO, demoComment);
    setState({ kind: "loading", mode: "convert" });
    try {
      const data = await api.convert(
        convertDemoRequest(C5G7_PRODUCTION_DEMO, {
          dryRun: false,
          comment: demoComment,
        }),
      );
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  function applyBrowserPick(picked: string) {
    if (browserTarget === "input") {
      updateInput(picked);
    } else if (browserTarget === "output-directory") {
      setOutputTouched(true);
      setOutputPath(
        outputPathInDirectory({
          directory: picked,
          currentOutput: displayedOutput,
          inputPath,
          format,
        }),
      );
    }
    setBrowserTarget(null);
    convertButtonRef.current?.focus();
  }

  function submitDryRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run("dry-run");
  }

  async function run(mode: "dry-run" | "convert") {
    const trimmedInput = inputPath.trim();
    const trimmedOutput = displayedOutput.trim();
    if (!trimmedInput) {
      setState({ kind: "error", message: "Enter an input HDF5 path first." });
      return;
    }
    if (!trimmedOutput) {
      setState({ kind: "error", message: "Enter an output path first." });
      return;
    }
    const numberError =
      optionalNumberError("Burnup", burnup) ??
      optionalNumberError("H-FACTOR default", hFactorDefault);
    if (numberError) {
      setState({ kind: "error", message: numberError });
      return;
    }
    setState({ kind: "loading", mode });
    try {
      const data = await api.convert({
        input_path: trimmedInput,
        output_path: trimmedOutput,
        format,
        dry_run: mode === "dry-run",
        overwrite,
        check,
        production,
        warn_unknown_energy_mesh: true,
        require_known_energy_mesh: requireKnownMesh,
        ...convertAdvancedPayload({
          rootName,
          comment,
          burnup,
          hFactorDefault,
          mixturesText,
        }),
      });
      setState({ kind: "ok", data });
    } catch (err) {
      setState(toErrorState(err));
    }
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="grad-text">Convert MGXS handoff</span>
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-2)]">
            Direct OpenMC HDF5 → DRAGON/DONJON ASCII conversion.
          </p>
        </header>

        <ConvertIntentBanner intent={intent} />
        {mockMode ? (
          <MockDemoCard
            onApply={applyC5g7Demo}
            onDryRun={() => void runC5g7DemoDryRun()}
            onConvert={() => void runC5g7DemoConvert()}
            dryRunLoading={state.kind === "loading" && state.mode === "dry-run"}
            convertLoading={state.kind === "loading" && state.mode === "convert"}
            canConvert={c5g7DemoDryRunPassed}
            converted={c5g7DemoConverted}
          />
        ) : (
          <LiveMinicaseCard onApply={applyProductionMinicaseDemo} />
        )}
        <ConvertPrimer
          state={state}
          inputPath={inputPath}
          outputPath={displayedOutput}
          format={format}
        />
        <ConvertShowcase
          format={format}
          check={check}
          production={production}
          requireKnownMesh={requireKnownMesh}
          outputPath={displayedOutput}
          input={preflightInput}
          defaultOpen={convertShowcaseDefaultOpen(state.kind)}
        />

        <form
          className="glass rounded-xl p-4 space-y-4"
          onSubmit={submitDryRun}
        >
          <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                Input HDF5
              </span>
              <input
                type="text"
                placeholder={inputPlaceholder}
                value={inputPath}
                onChange={(event) => updateInput(event.target.value)}
                className="mt-1 w-full min-w-0 px-3 py-2 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
                spellCheck={false}
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              onClick={() => setBrowserTarget("input")}
              className="btn btn-secondary self-end"
            >
              Browse…
            </button>
          </div>

          {canUseSavedPrefix ? (
            <button
              type="button"
              onClick={() => updateInput(savedPrefix)}
              className="text-[12px] text-[var(--accent-2)] hover:underline"
            >
              Use saved prefix:{" "}
              <code className="font-mono">{savedPrefix}</code>
            </button>
          ) : null}

          <div className="grid gap-3 lg:grid-cols-[220px_1fr_auto]">
            <fieldset>
              <legend className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                Output object
              </legend>
              <div className="mt-1 grid grid-cols-2 rounded-md border border-[var(--edge)] overflow-hidden">
                <button
                  type="button"
                  onClick={() => updateFormat("multicompo")}
                  className={segmentClass(format === "multicompo")}
                >
                  MULTICOMPO
                </button>
                <button
                  type="button"
                  onClick={() => updateFormat("macrolib")}
                  className={segmentClass(format === "macrolib")}
                >
                  MACROLIB
                </button>
              </div>
            </fieldset>

            <label className="block">
              <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                Output ASCII
              </span>
              <input
                type="text"
                value={displayedOutput}
                onChange={(event) => {
                  setOutputTouched(true);
                  setOutputPath(event.target.value);
                }}
                className="mt-1 w-full min-w-0 px-3 py-2 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-sm focus:outline-none focus:border-[var(--accent)]"
                spellCheck={false}
                autoComplete="off"
              />
              <span className="mt-1 block text-[12px] text-[var(--fg-3)]">
                Choose a directory with Browse, then edit the filename if needed.
              </span>
            </label>
            <button
              type="button"
              onClick={() => setBrowserTarget("output-directory")}
              className="btn btn-secondary self-end"
            >
              Browse dir…
            </button>
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Toggle
              label="Validate first"
              description="Check the HDF5 contract and quick physics consistency before writing."
              checked={check}
              onChange={setCheck}
            />
            <Toggle
              label="Production checks"
              description="Use the stricter acceptance preset for production handoffs."
              checked={production}
              onChange={setProduction}
            />
            <Toggle
              label="Known mesh required"
              description="Fail unless the energy grid matches a known standard mesh."
              checked={requireKnownMesh}
              onChange={setRequireKnownMesh}
            />
            <Toggle
              label="Overwrite output"
              description="Allow Convert to replace an existing ASCII file."
              checked={overwrite}
              onChange={setOverwrite}
            />
          </div>

          <ConvertModeReferenceStrip format={format} />

          <DirectConvertActionPanel
            state={state}
            inputPath={inputPath}
            outputPath={displayedOutput}
            check={check}
            production={production}
            format={format}
            onConvert={() => void run("convert")}
            convertButtonRef={convertButtonRef}
          />

          <details className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
            <summary className="cursor-pointer text-sm font-semibold tracking-tight text-[var(--fg-0)]">
              Advanced converter options
            </summary>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <Field
                label="LCM root name"
                value={rootName}
                onChange={setRootName}
                placeholder="CPO"
                mono
                disabled={format === "macrolib"}
                hint={
                  format === "macrolib"
                    ? "MACROLIB output does not use a MULTICOMPO root directory."
                    : "Top-level MULTICOMPO directory name."
                }
              />
              <Field
                label="Burnup value"
                value={burnup}
                onChange={setBurnup}
                placeholder="0.0"
                mono
                hint="Optional single-point BURN axis metadata."
              />
              <Field
                label="H-FACTOR default"
                value={hFactorDefault}
                onChange={setHFactorDefault}
                placeholder="200.0"
                mono
                hint="Only for plumbing/demo cases when the HDF5 lacks H-FACTOR."
              />
              <Field
                label="COMMENT block"
                value={comment}
                onChange={setComment}
                placeholder="OpenMC direct homogenization"
                hint="Optional comment written into MULTICOMPO output."
              />
              <label className="block lg:col-span-2">
                <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                  Mixture filter
                </div>
                <div className="mt-1 space-y-3">
                  <MixturePicker
                    inputPath={inputPath}
                    value={mixturesText}
                    onChange={setMixturesText}
                  />
                  <textarea
                    value={mixturesText}
                    onChange={(event) => setMixturesText(event.target.value)}
                    placeholder="ASM_Y01_X01, ASM_Y01_X02"
                    className="min-h-20 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
                    spellCheck={false}
                  />
                </div>
                <span className="mt-1 block text-[12px] text-[var(--fg-3)]">
                  Optional comma/newline list. Empty means write every mixture.
                </span>
              </label>
            </div>
          </details>

          <section className="rounded-lg border border-[var(--edge)] bg-black/15 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold tracking-tight">
                  CLI preview
                </div>
                <div className="mt-1 text-[12px] text-[var(--fg-3)]">
                  The web endpoint calls the Python converter directly; this is
                  the equivalent terminal command.
                </div>
              </div>
              <CopyCliButton value={cliPreview} />
            </div>
            <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
              {cliPreview}
            </pre>
          </section>

        </form>

        <FileBrowserModal
          open={browserTarget != null}
          initialPath={
            browserTarget === "output-directory"
              ? pickConvertBrowserStart(displayedOutput || savedPrefix)
              : pickConvertBrowserStart(inputPath.trim() || savedPrefix)
          }
          extensions={browserTarget === "output-directory" ? [] : ["h5", "hdf5"]}
          fileTypeLabel={
            browserTarget === "output-directory" ? "output directory" : "HDF5"
          }
          chipLabel={browserTarget === "output-directory" ? "DIR" : "H5"}
          recentScope={
            browserTarget === "output-directory" ? "convert-output-dir" : "hdf5"
          }
          selectMode={browserTarget === "output-directory" ? "directory" : "file"}
          onClose={() => setBrowserTarget(null)}
          onSelect={applyBrowserPick}
        />

        <section className="mt-6">
          <ConvertReport
            state={state}
            onConvert={() => void run("convert")}
            draftInputPath={inputPath}
            draftOutputPath={displayedOutput}
            format={format}
          />
          {showMinicaseMissingHint ? (
            <ProductionMinicaseMissingHint onApply={applyProductionMinicaseDemo} />
          ) : null}
        </section>
      </div>
    </main>
  );
}

function ConvertIntentBanner({ intent }: { intent: ConvertIntentCopy }) {
  return (
    <section className={"mb-5 rounded-xl border p-4 " + intentBannerClass(intent.tone)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            {intent.eyebrow}
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {intent.title}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {intent.body}
          </p>
        </div>
        {intent.commandHref && intent.commandLabel ? (
          <Link href={intent.commandHref} className="btn btn-secondary shrink-0">
            {intent.commandLabel}
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function DirectConvertActionPanel({
  state,
  inputPath,
  outputPath,
  check,
  production,
  format,
  onConvert,
  convertButtonRef,
}: {
  state: ConvertRunState;
  inputPath: string;
  outputPath: string;
  check: boolean;
  production: boolean;
  format: ConvertFormat;
  onConvert: () => void;
  convertButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  const hasInput = inputPath.trim().length > 0;
  const hasOutput = outputPath.trim().length > 0;
  const canRun = hasInput && hasOutput && state.kind !== "loading";
  const dryRunLoading = state.kind === "loading" && state.mode === "dry-run";
  const convertLoading = state.kind === "loading" && state.mode === "convert";
  const converted = state.kind === "ok" && state.data.converted && state.data.output_exists;
  const validated =
    state.kind === "ok" && state.data.preflight != null && state.data.preflight_ok;
  const validationFailed =
    (state.kind === "ok" && state.data.preflight != null && !state.data.preflight_ok) ||
    state.kind === "error";
  const object = format === "macrolib" ? "MACROLIB" : "MULTICOMPO";
  const checkMode = production ? "production" : check ? "standard" : "minimal";
  return (
    <section className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.035] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Direct convert action
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            Validate, then write the DONJON ASCII handoff
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Dry run is the safe no-write pass. Convert writes the selected{" "}
            {object} text file at the output path.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {object} · {checkMode} checks
        </span>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-3">
        <ActionStep
          step="01"
          title="Select paths"
          body="Choose the MGXS HDF5 and the target ASCII filename."
          status={hasInput && hasOutput ? "ready" : "needed"}
        />
        <ActionStep
          step="02"
          title="Dry run"
          body="Run validation without creating or replacing the output file."
          status={validationFailed ? "failed" : validated ? "done" : "recommended"}
        />
        <ActionStep
          step="03"
          title="Convert"
          body={`Write the ${object} artifact for downstream DONJON use.`}
          status={converted ? "done" : canRun ? "ready" : "waiting"}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          className="btn btn-secondary"
          disabled={!canRun}
        >
          {dryRunLoading ? "Checking…" : "Dry run"}
        </button>
        <button
          ref={convertButtonRef}
          type="button"
          onClick={onConvert}
          className="btn btn-primary"
          disabled={!canRun}
        >
          {convertLoading ? "Converting…" : "Convert"}
        </button>
        <p className="text-[12px] leading-5 text-[var(--fg-3)]">
          You can convert directly, but a dry run gives a readable no-write
          record first.
        </p>
      </div>
    </section>
  );
}

function ConvertModeReferenceStrip({ format }: { format: ConvertFormat }) {
  const items = convertModeReference(format);
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            What each action means
          </h2>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            The converter is deliberately linear: check without writing, write
            the ASCII file, then review and package it.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          user flow
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        {items.map((item) => (
          <ConvertModeCard key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}

function ConvertModeCard({ item }: { item: ConvertModeReferenceItem }) {
  return (
    <article
      className={
        "rounded-md border px-3 py-2 " +
        convertModeReferenceClass(item.emphasis)
      }
    >
      <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
        {item.label}
      </span>
      <h3 className="mt-2 text-[12px] font-semibold tracking-tight">
        {item.title}
      </h3>
      <p className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
        {item.body}
      </p>
    </article>
  );
}

function convertModeReferenceClass(
  emphasis: ConvertModeReferenceItem["emphasis"],
): string {
  if (emphasis === "safe") {
    return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-100";
  }
  if (emphasis === "write") {
    return "border-emerald-300/20 bg-emerald-300/[0.045] text-emerald-100";
  }
  return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
}

function ActionStep({
  step,
  title,
  body,
  status,
}: {
  step: string;
  title: string;
  body: string;
  status: "needed" | "recommended" | "ready" | "waiting" | "done" | "failed";
}) {
  return (
    <article className={"rounded-lg border px-3 py-2 " + actionStepClass(status)}>
      <div className="flex items-center justify-between gap-3">
        <span className="rounded border border-current/25 px-1.5 py-0.5 font-mono text-[10px]">
          {step}
        </span>
        <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
          {status}
        </span>
      </div>
      <h3 className="mt-2 text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
    </article>
  );
}

function actionStepClass(status: "needed" | "recommended" | "ready" | "waiting" | "done" | "failed"): string {
  if (status === "done") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (status === "failed") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  if (status === "ready") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "recommended") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}

function MockDemoCard({
  onApply,
  onDryRun,
  onConvert,
  dryRunLoading,
  convertLoading,
  canConvert,
  converted,
}: {
  onApply: () => void;
  onDryRun: () => void;
  onConvert: () => void;
  dryRunLoading: boolean;
  convertLoading: boolean;
  canConvert: boolean;
  converted: boolean;
}) {
  const steps = convertDemoWalkthrough(C5G7_PRODUCTION_DEMO);
  return (
    <section className="mb-5 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.05] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-200/80">
            Mock backend walkthrough
          </div>
          <h2 className="mt-1 text-sm font-semibold tracking-tight text-cyan-100">
            {C5G7_PRODUCTION_DEMO.label}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-[var(--fg-2)]">
            {C5G7_PRODUCTION_DEMO.description}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={onApply} className="btn btn-secondary">
            Fill demo
          </button>
          <button
            type="button"
            onClick={onDryRun}
            className="btn btn-primary"
            disabled={dryRunLoading}
          >
            {dryRunLoading ? "Checking…" : "Run demo dry-run"}
          </button>
          {canConvert || converted || convertLoading ? (
            <button
              type="button"
              onClick={onConvert}
              className="btn btn-primary"
              disabled={!canConvert || converted || convertLoading}
            >
              {convertLoading
                ? "Converting…"
                : converted
                  ? "Demo output ready"
                  : "Convert demo output"}
            </button>
          ) : null}
        </div>
      </div>
      {canConvert || converted ? (
        <div
          className={
            "mt-3 rounded-md border px-3 py-2 text-sm " +
            (converted
              ? "border-emerald-300/20 bg-emerald-300/[0.055] text-emerald-100"
              : "border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-100")
          }
        >
          <span className="font-semibold">
            {converted ? "Demo conversion complete." : "Dry run passed."}
          </span>
          <span className="ml-2 text-[var(--fg-1)]">
            {converted
              ? "The mock MULTICOMPO artifact is ready for preview and bundling below."
              : "Run Convert demo output to create the mock MULTICOMPO ASCII handoff."}
          </span>
        </div>
      ) : null}
      {converted ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href={convertDemoPreviewHref(C5G7_PRODUCTION_DEMO)}
            className="btn btn-primary"
          >
            Preview output
          </a>
          <Link
            href={convertDemoBundleHref(C5G7_PRODUCTION_DEMO)}
            className="btn btn-secondary"
          >
            Bundle demo
          </Link>
        </div>
      ) : null}
      <div className="mt-4 grid gap-3 lg:grid-cols-4">
        {steps.map((step) => (
          <div key={step.id} className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded border border-cyan-200/25 bg-cyan-200/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-cyan-100">
                {step.label}
              </span>
              <h3 className="text-[12px] font-semibold tracking-tight text-cyan-50">
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
                Open
              </Link>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function LiveMinicaseCard({ onApply }: { onApply: () => void }) {
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

function ProductionMinicaseMissingHint({ onApply }: { onApply: () => void }) {
  return (
    <section className="mt-4 rounded-xl border border-amber-300/25 bg-amber-300/[0.06] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-amber-200">
            Production minicase artifacts were not found.
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Run the smoke command from the repository root first; it writes the
            managed MGXS path used by the live walkthrough. The repeat ASCII
            and bundle paths are created later by the web convert and bundle
            steps.
          </p>
        </div>
        <button type="button" onClick={onApply} className="btn btn-secondary">
          Refill paths
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CopyCliButton
          value={PRODUCTION_MINICASE_COMMAND}
          compact
          label="Copy smoke command"
          copiedLabel="Copied"
        />
        <code className="rounded border border-[var(--edge)] bg-black/20 px-2 py-1 font-mono text-[12px] text-[var(--fg-1)]">
          {PRODUCTION_MINICASE_COMMAND}
        </code>
      </div>
    </section>
  );
}

function ConvertPrimer({
  state,
  inputPath,
  outputPath,
  format,
}: {
  state: ConvertRunState;
  inputPath: string;
  outputPath: string;
  format: ConvertFormat;
}) {
  const trimmedInput = inputPath.trim();
  const trimmedOutput = outputPath.trim();
  const run = convertWalkthroughRunFromState(state);
  const statuses = convertWalkthroughStatuses({
    hasInput: trimmedInput.length > 0,
    hasOutput: trimmedOutput.length > 0,
    run,
  });
  const stageSummary = convertWorkflowStageSummary({
    hasInput: trimmedInput.length > 0,
    hasOutput: trimmedOutput.length > 0,
    run,
  });
  const object = format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
  const inspectHref = trimmedInput
    ? `/inspect?path=${encodeURIComponent(trimmedInput)}`
    : undefined;
  const bundleHref =
    convertBundleBuilderHrefFromPaths({
      inputPath: trimmedInput,
      outputPath: trimmedOutput,
      format,
    }) ?? undefined;
  const items = [
    {
      id: "source",
      label: "01",
      eyebrow: "Source",
      title: "OpenMC MGXS HDF5",
      body:
        "Start from the homogenized OpenMC handoff. Inspect it when you need mixture, mesh, ADF, or SPH evidence.",
      href: inspectHref,
      hrefLabel: "Inspect source",
      status: statuses.source,
    },
    {
      id: "dry-run",
      label: "02",
      eyebrow: "No-write check",
      title: "No-write production check",
      body:
        "Run the converter in dry-run mode first. It checks the contract and production physics without creating output.",
      href: undefined,
      hrefLabel: undefined,
      status: statuses["dry-run"],
    },
    {
      id: "convert",
      label: "03",
      eyebrow: "Convert ASCII",
      title: `Write ${object}`,
      body:
        "Convert writes the DONJON-facing ASCII handoff at the selected output path.",
      href: undefined,
      hrefLabel: undefined,
      status: statuses.convert,
    },
    {
      id: "bundle",
      label: "04",
      eyebrow: "Bundle handoff",
      title: "Package delivery evidence",
      body:
        "Collect the MGXS input, ASCII output, summaries, and logs into a manifest-backed handoff.",
      href: bundleHref,
      hrefLabel: "Open bundle builder",
      status: statuses.bundle,
    },
  ] as const;
  return (
    <section className="mb-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Direct converter production path
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            This page turns an existing OpenMC MGXS handoff into a DONJON-facing
            ASCII library. Dry run is the readable no-write checkpoint, Convert
            creates the file, and Bundle packages the delivery record.
          </p>
        </div>
        <Link href="/commands/direct-convert" className="btn btn-secondary">
          Command notes
        </Link>
      </div>
      <div
        className={
          "mt-4 rounded-lg border px-3 py-3 " +
          stageSummaryClass(stageSummary.tone)
        }
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
              Current stage
            </div>
            <h3 className="mt-1 text-sm font-semibold tracking-tight">
              {stageSummary.title}
            </h3>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-1)]">
              {stageSummary.body}
            </p>
          </div>
          <ol className="flex min-w-0 flex-wrap items-center gap-1.5">
            {stageSummary.stages.map((stage, index) => (
              <li key={stage.id} className="flex items-center gap-1.5">
                {index > 0 ? (
                  <span className="text-[var(--fg-3)]" aria-hidden="true">
                    →
                  </span>
                ) : null}
                <span
                  className={
                    "rounded-full border px-2 py-1 text-[11px] font-medium " +
                    stagePillClass(stage.status)
                  }
                >
                  {stage.label}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => (
          <article
            key={item.id}
            className={
              "rounded-lg border px-3 py-2 " +
              walkthroughStatusClass(item.status)
            }
          >
            <div className="flex items-center justify-between gap-2">
              <span className="rounded border border-current/25 px-1.5 py-0.5 font-mono text-[10px]">
                {item.label}
              </span>
              <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
                {item.status}
              </span>
            </div>
            <div className="mt-2 text-[10px] uppercase tracking-[0.14em] opacity-70">
              {item.eyebrow}
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight">
              {item.title}
            </h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
              {item.body}
            </p>
            {item.href && item.hrefLabel ? (
              <Link
                href={item.href}
                className="mt-3 inline-flex text-[12px] font-medium text-[var(--accent-2)] hover:underline"
              >
                {item.hrefLabel}
              </Link>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function stageSummaryClass(
  tone: "ready" | "current" | "running" | "blocked",
): string {
  if (tone === "ready") {
    return "border-emerald-300/20 bg-emerald-300/[0.045] text-emerald-100";
  }
  if (tone === "running") {
    return "border-cyan-300/25 bg-cyan-300/[0.07] text-cyan-100";
  }
  if (tone === "blocked") {
    return "border-rose-300/25 bg-rose-300/[0.055] text-rose-100";
  }
  return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
}

function stagePillClass(status: ConvertWorkflowStageStatus): string {
  if (status === "complete") {
    return "border-emerald-300/25 bg-emerald-300/[0.08] text-emerald-100";
  }
  if (status === "running") {
    return "border-cyan-300/25 bg-cyan-300/[0.12] text-cyan-100";
  }
  if (status === "current") {
    return "border-amber-300/30 bg-amber-300/[0.12] text-amber-100";
  }
  if (status === "blocked") {
    return "border-rose-300/25 bg-rose-300/[0.08] text-rose-100";
  }
  return "border-[var(--edge)] bg-black/10 text-[var(--fg-2)]";
}

function convertWalkthroughRunFromState(state: ConvertRunState): ConvertWalkthroughRun {
  if (state.kind === "loading") {
    return { kind: "loading", mode: state.mode };
  }
  if (state.kind === "ok") {
    return {
      kind: "ok",
      ok: state.data.ok,
      dryRun: state.data.dry_run,
      converted: state.data.converted,
      outputExists: state.data.output_exists,
      preflightOk: state.data.preflight_ok,
    };
  }
  return { kind: state.kind };
}

function walkthroughStatusClass(status: ConvertWalkthroughStatus): string {
  if (status === "done" || status === "passed") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (status === "ready") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "recommended" || status === "planned") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
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

function Field({
  label,
  value,
  onChange,
  placeholder,
  hint,
  mono = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  hint: string;
  mono?: boolean;
  disabled?: boolean;
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
        disabled={disabled}
        className={
          "mt-1 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none disabled:cursor-not-allowed disabled:text-[var(--fg-3)] " +
          (mono ? "font-mono" : "")
        }
        spellCheck={false}
        autoComplete="off"
      />
      <span className="mt-1 block text-[12px] text-[var(--fg-3)]">{hint}</span>
    </label>
  );
}

function segmentClass(active: boolean): string {
  return (
    "px-3 py-2 text-[12px] font-semibold uppercase tracking-wider transition " +
    (active
      ? "bg-emerald-400/15 text-emerald-200"
      : "bg-white/[0.02] text-[var(--fg-2)] hover:text-[var(--fg-0)]")
  );
}

function intentBannerClass(tone: ConvertIntentCopy["tone"]): string {
  if (tone === "accent") return "border-cyan-300/25 bg-cyan-300/[0.05]";
  if (tone === "production") {
    return "border-emerald-300/25 bg-emerald-300/[0.05]";
  }
  if (tone === "sph") return "border-amber-300/25 bg-amber-300/[0.05]";
  return "border-[var(--edge)] bg-white/[0.02]";
}

function optionalNumberError(label: string, value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (Number.isFinite(Number(trimmed))) return null;
  return `${label} must be a number.`;
}

function isC5g7DemoDryRunPassed(state: ConvertRunState): boolean {
  return (
    state.kind === "ok" &&
    state.data.ok &&
    state.data.dry_run &&
    !state.data.converted &&
    state.data.input_path === C5G7_PRODUCTION_DEMO.inputPath &&
    state.data.output_path === C5G7_PRODUCTION_DEMO.outputPath
  );
}

function isC5g7DemoConverted(state: ConvertRunState): boolean {
  return (
    state.kind === "ok" &&
    state.data.ok &&
    state.data.converted &&
    state.data.output_exists &&
    state.data.input_path === C5G7_PRODUCTION_DEMO.inputPath &&
    state.data.output_path === C5G7_PRODUCTION_DEMO.outputPath
  );
}

function toErrorState(
  err: unknown,
): Extract<ConvertRunState, { kind: "error" }> {
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
