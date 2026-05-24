"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ConvertReport, {
  ConvertRunState,
} from "@/components/convert/ConvertReport";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import ConvertConcepts from "@/components/convert/ConvertConcepts";
import MixturePicker from "@/components/convert/MixturePicker";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  ConvertFormat,
  api,
} from "@/lib/api";
import {
  buildConvertCliPreview,
  convertAdvancedPayload,
} from "@/lib/convertCommand";
import {
  C5G7_PRODUCTION_DEMO,
  PRODUCTION_MINICASE_ARTIFACTS,
  PRODUCTION_MINICASE_COMMAND,
  PRODUCTION_MINICASE_DEMO,
  convertDemoWalkthrough,
  isProductionMinicasePath,
} from "@/lib/convertDemo";
import { convertIntentCopy } from "@/lib/convertIntent";
import type { ConvertIntentCopy } from "@/lib/convertIntent";
import {
  defaultConvertOutputPath,
  outputPathInDirectory,
  pickConvertBrowserStart,
} from "@/lib/convertPaths";
import { useSettings } from "@/lib/settings";
import { parseConvertFormat, queryFlag } from "@/lib/workflowQuery";

const FALLBACK_INPUT = "/path/to/mgxs_library.h5";
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
    updateInput(C5G7_PRODUCTION_DEMO.inputPath);
    setOutputPath(C5G7_PRODUCTION_DEMO.outputPath);
    setOutputTouched(true);
    setFormat(C5G7_PRODUCTION_DEMO.format);
    setCheck(C5G7_PRODUCTION_DEMO.check);
    setProduction(C5G7_PRODUCTION_DEMO.production);
    setRequireKnownMesh(C5G7_PRODUCTION_DEMO.requireKnownMesh);
    setOverwrite(false);
    setRootName("CPO");
    setComment("C5G7 mock production demo");
    setBurnup("");
    setHFactorDefault("");
    setMixturesText("");
    setState({ kind: "idle" });
  }

  function applyProductionMinicaseDemo() {
    updateInput(PRODUCTION_MINICASE_DEMO.inputPath);
    setOutputPath(PRODUCTION_MINICASE_DEMO.outputPath);
    setOutputTouched(true);
    setFormat(PRODUCTION_MINICASE_DEMO.format);
    setCheck(PRODUCTION_MINICASE_DEMO.check);
    setProduction(PRODUCTION_MINICASE_DEMO.production);
    setRequireKnownMesh(PRODUCTION_MINICASE_DEMO.requireKnownMesh);
    setOverwrite(false);
    setRootName("CPO");
    setComment("production minicase web repeat");
    setBurnup("");
    setHFactorDefault("");
    setMixturesText("");
    setState({ kind: "idle" });
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
          <MockDemoCard onApply={applyC5g7Demo} />
        ) : (
          <LiveMinicaseCard onApply={applyProductionMinicaseDemo} />
        )}
        <ConvertGuide />
        <ConvertConcepts />

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
              label="Preflight"
              description="Validate the HDF5 contract and quick physics gates before writing."
              checked={check}
              onChange={setCheck}
            />
            <Toggle
              label="Production gates"
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

          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              className="btn btn-secondary"
              disabled={state.kind === "loading"}
            >
              {state.kind === "loading" && state.mode === "dry-run"
                ? "Checking…"
                : "Dry run"}
            </button>
            <button
              ref={convertButtonRef}
              type="button"
              onClick={() => void run("convert")}
              className="btn btn-primary"
              disabled={state.kind === "loading"}
            >
              {state.kind === "loading" && state.mode === "convert"
                ? "Converting…"
                : "Convert"}
            </button>
          </div>
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
          <ConvertReport state={state} onConvert={() => void run("convert")} />
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

function MockDemoCard({ onApply }: { onApply: () => void }) {
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
        <button type="button" onClick={onApply} className="btn btn-primary">
          Fill demo
        </button>
      </div>
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
  return (
    <section className="mb-5 rounded-xl border border-emerald-300/20 bg-emerald-300/[0.05] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] text-emerald-200/80">
            Live production minicase
          </div>
          <h2 className="mt-1 text-sm font-semibold tracking-tight text-emerald-100">
            {PRODUCTION_MINICASE_DEMO.label}
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-[var(--fg-2)]">
            {PRODUCTION_MINICASE_DEMO.description}
          </p>
        </div>
        <button type="button" onClick={onApply} className="btn btn-primary">
          Use generated paths
        </button>
      </div>

      <div className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[12px] font-semibold tracking-tight text-emerald-100">
              Generate the real handoff first
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
              <span className="rounded border border-emerald-200/25 bg-emerald-200/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-emerald-100">
                {artifact.label}
              </span>
              {artifact.href ? (
                <Link
                  href={artifact.href}
                  className="text-[11px] text-[var(--accent-2)] hover:underline"
                >
                  open
                </Link>
              ) : null}
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
            managed MGXS and MULTICOMPO paths used by the live walkthrough.
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

function ConvertGuide() {
  return (
    <section className="mb-5 grid gap-3 lg:grid-cols-4">
      <GuideCard
        step="01"
        title="Inspect the HDF5"
        body="Check the group structure, mixture roster, and optional equivalence data before selecting what to export."
      />
      <GuideCard
        step="02"
        title="Dry run first"
        body="Run preflight without writing output; production gates catch common MGXS contract and physics issues."
      />
      <GuideCard
        step="03"
        title="Write ASCII"
        body="Generate .mcompo.txt for mapped MULTICOMPO handoffs or .macrolib.txt for one-state MACROLIB input."
      />
      <GuideCard
        step="04"
        title="Review and package"
        body="Preview the LCM ASCII blocks, then bundle the HDF5, output, summaries, and logs as the production record."
      />
    </section>
  );
}

function GuideCard({
  step,
  title,
  body,
}: {
  step: string;
  title: string;
  body: string;
}) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-white/[0.02] px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="rounded border border-emerald-300/20 bg-emerald-300/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-emerald-200">
          {step}
        </span>
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-[var(--fg-2)]">{body}</p>
    </article>
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
