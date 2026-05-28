"use client";

import {
  FormEvent,
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
import BackendModeCard from "@/components/convert/BackendModeCard";
import ConvertIntentBanner from "@/components/convert/ConvertIntentBanner";
import ConvertModeReferenceStrip from "@/components/convert/ConvertModeReferenceStrip";
import ConvertPrimer from "@/components/convert/ConvertPrimer";
import ConvertShowcase from "@/components/convert/ConvertShowcase";
import DirectConvertActionPanel from "@/components/convert/DirectConvertActionPanel";
import LiveMinicaseCard from "@/components/convert/LiveMinicaseCard";
import MockDemoCard from "@/components/convert/MockDemoCard";
import ProductionMinicaseMissingHint from "@/components/convert/ProductionMinicaseMissingHint";
import WriterBackendSelector from "@/components/convert/WriterBackendSelector";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import MixturePicker from "@/components/convert/MixturePicker";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  api,
} from "@/lib/api";
import type {
  ConvertFormat,
  ConvertWriterBackend,
  PyGanBackendStatus,
} from "@/lib/api";
import {
  buildConvertCliPreview,
  convertAdvancedPayload,
} from "@/lib/convertCommand";
import {
  C5G7_PRODUCTION_DEMO,
  PRODUCTION_MINICASE_DEMO,
  convertDemoRequest,
  isProductionMinicasePath,
} from "@/lib/convertDemo";
import { convertIntentCopy } from "@/lib/convertIntent";
import {
  defaultConvertOutputPath,
  outputPathInDirectory,
  pickConvertBrowserStart,
} from "@/lib/convertPaths";
import { convertShowcaseDefaultOpen } from "@/lib/convertShowcase";
import { useSettings } from "@/lib/settings";
import { parseConvertFormat, queryFlag } from "@/lib/workflowQuery";

const FALLBACK_INPUT = "/path/to/mgxs_library.h5";
const UNKNOWN_PYGAN_BACKEND: PyGanBackendStatus = {
  available: false,
  role: "optional PyGan writer backend",
  install_hint:
    "Restart `openmc2donjon serve` from the current checkout to expose PyGan backend status.",
  modules: [],
  missing_modules: [],
};

type BrowserTarget = "input" | "output-directory";

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
  const queryWriterBackend: ConvertWriterBackend =
    searchParams.get("writer_backend") === "pygan" ? "pygan" : "ascii";
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
    searchParams.get("writer_backend") !== null ||
    searchParams.get("check") !== null ||
    searchParams.get("production") !== null ||
    searchParams.get("require_known_mesh") !== null ||
    queryComment !== null;
  const [inputPath, setInputPath] = useState(queryInput ?? "");
  const [outputPath, setOutputPath] = useState(queryOutput ?? "");
  const [format, setFormat] = useState<ConvertFormat>(queryFormat);
  const [writerBackend, setWriterBackend] =
    useState<ConvertWriterBackend>(queryWriterBackend);
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
  const [backendMode, setBackendMode] = useState<
    "checking" | "mock" | "live" | "unavailable"
  >("checking");
  const [pyganStatus, setPyganStatus] = useState<PyGanBackendStatus | null>(null);
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
    writerBackend,
    dryRun: true,
    overwrite,
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
    backendMode === "live" &&
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
        if (!cancelled) {
          setBackendMode(health.mock_mode ? "mock" : "live");
          const pyganBackend = health.pygan_backend ?? UNKNOWN_PYGAN_BACKEND;
          setPyganStatus(pyganBackend);
          if (!pyganBackend.available) {
            setWriterBackend("ascii");
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBackendMode("unavailable");
          setPyganStatus(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!queryHasPrefill) return;
    setFormat(queryFormat);
    setWriterBackend(queryWriterBackend);
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
    queryWriterBackend,
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
    setWriterBackend("ascii");
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
        writer_backend: writerBackend,
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
        {backendMode === "checking" ? (
          <BackendModeCard
            tone="loading"
            title="Checking backend mode"
            body="The web UI is asking the FastAPI backend whether this is mock mode or live filesystem mode before showing demo paths."
          />
        ) : backendMode === "mock" ? (
          <MockDemoCard
            onApply={applyC5g7Demo}
            onDryRun={() => void runC5g7DemoDryRun()}
            onConvert={() => void runC5g7DemoConvert()}
            dryRunLoading={state.kind === "loading" && state.mode === "dry-run"}
            convertLoading={state.kind === "loading" && state.mode === "convert"}
            canConvert={c5g7DemoDryRunPassed}
            converted={c5g7DemoConverted}
          />
        ) : backendMode === "live" ? (
          <LiveMinicaseCard onApply={applyProductionMinicaseDemo} />
        ) : (
          <BackendModeCard
            tone="error"
            title="Backend status unavailable"
            body="Start or restart the FastAPI backend with `openmc2donjon serve`; the page will not show live minicase paths until `/api/health` responds."
          />
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

          <WriterBackendSelector
            value={writerBackend}
            onChange={setWriterBackend}
            status={pyganStatus}
          />

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
            writerBackend={writerBackend}
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
                  Safe no-write terminal command for the current form values.
                  The result panel shows the exact command for each run.
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

function segmentClass(active: boolean, disabled = false): string {
  if (disabled) {
    return "px-3 py-2 text-[12px] font-semibold uppercase tracking-wider bg-white/[0.01] text-[var(--fg-3)] cursor-not-allowed";
  }
  return (
    "px-3 py-2 text-[12px] font-semibold uppercase tracking-wider transition " +
    (active
      ? "bg-emerald-400/15 text-emerald-200"
      : "bg-white/[0.02] text-[var(--fg-2)] hover:text-[var(--fg-0)]")
  );
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
