"use client";

import { FormEvent, Suspense, useId, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  ConvertFormat,
  OpenmcEquivalenceMode,
  OpenmcWorkflowKind,
  OpenmcWorkflowPlan,
  api,
} from "@/lib/api";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import OpenmcArtifactList from "@/components/openmc/OpenmcArtifactList";
import OpenmcCommandList from "@/components/openmc/OpenmcCommandList";
import OpenmcProductionPathPanel from "@/components/openmc/OpenmcProductionPathPanel";
import OpenmcWorkflowChoices from "@/components/openmc/OpenmcWorkflowChoices";
import OpenmcWorkflowSummary from "@/components/openmc/OpenmcWorkflowSummary";
import { useSettings } from "@/lib/settings";
import {
  parseConvertFormat,
  parseOpenmcEquivalence,
  parseOpenmcWorkflow,
  queryFlag,
} from "@/lib/workflowQuery";

type PlanState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: OpenmcWorkflowPlan }
  | { kind: "error"; message: string; status?: number };

type BrowserTarget =
  | "recipe"
  | "statepoint"
  | "run-dir"
  | "hdf5"
  | "output"
  | "adf"
  | "sph";

interface BrowserConfig {
  initialPath: string;
  extensions: readonly string[];
  fileTypeLabel: string;
  chipLabel: string;
  recentScope: string;
  selectMode?: "file" | "directory";
}

const FALLBACK_RUN_DIR = "/path/to/openmc2donjon-run";

export default function OpenmcPage() {
  return (
    <Suspense fallback={<OpenmcLoading />}>
      <OpenmcPageContent />
    </Suspense>
  );
}

function OpenmcLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading OpenMC planner…
        </section>
      </div>
    </main>
  );
}

function OpenmcPageContent() {
  const searchParams = useSearchParams();
  const [workflow, setWorkflow] = useState<OpenmcWorkflowKind>(
    parseOpenmcWorkflow(searchParams.get("workflow")),
  );
  const [equivalence, setEquivalence] = useState<OpenmcEquivalenceMode>(
    parseOpenmcEquivalence(searchParams.get("equivalence")),
  );
  const [format, setFormat] = useState<ConvertFormat>(
    parseConvertFormat(searchParams.get("format")),
  );
  const [recipePath, setRecipePath] = useState("");
  const [statepointPath, setStatepointPath] = useState("");
  const [runDir, setRunDir] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [keepHdf5Path, setKeepHdf5Path] = useState("");
  const [adfSource, setAdfSource] = useState("");
  const [sphSource, setSphSource] = useState("");
  const [loadStatepoint, setLoadStatepoint] = useState(true);
  const [check, setCheck] = useState(true);
  const [production, setProduction] = useState(
    queryFlag(searchParams, "production", false),
  );
  const [requireKnownMesh, setRequireKnownMesh] = useState(false);
  const [strictDryRun, setStrictDryRun] = useState(false);
  const [hFactorText, setHFactorText] = useState("");
  const [state, setState] = useState<PlanState>({ kind: "idle" });
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
        savedPrefix,
        format,
      })
    : null;

  async function plan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const hFactorDefault = parseOptionalNumber(hFactorText);
    if (hFactorDefault === "invalid") {
      setState({
        kind: "error",
        message: "H-factor default must be a finite number.",
      });
      return;
    }
    setState({ kind: "loading" });
    try {
      const data = await api.openmcWorkflowPlan({
        workflow,
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
      default:
        break;
    }
    setBrowserTarget(null);
    planButtonRef.current?.focus();
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="grad-text">OpenMC production workflow</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-[var(--fg-2)]">
            Plan the recipe/statepoint handoff before running OpenMC export:
            choose one-step or two-step, equivalence method, output format, and
            managed artifact paths.
          </p>
        </header>

        <OpenmcWorkflowChoices />

        <OpenmcProductionPathPanel
          state={state}
          workflow={workflow}
          equivalence={equivalence}
          format={format}
          production={production}
          recipePath={recipePath}
          statepointPath={statepointPath}
          loadStatepoint={loadStatepoint}
          runDir={runDir}
        />

        <form className="glass rounded-xl p-4 space-y-4" onSubmit={plan}>
          <div className="grid gap-3 lg:grid-cols-2">
            <Segmented
              label="Workflow"
              value={workflow}
              onChange={(value) => setWorkflow(value as OpenmcWorkflowKind)}
              options={[
                ["one-step", "One-step"],
                ["two-step", "Two-step"],
              ]}
            />
            <Segmented
              label="Output object"
              value={format}
              onChange={(value) => setFormat(value as ConvertFormat)}
              options={[
                ["multicompo", "MULTICOMPO"],
                ["macrolib", "MACROLIB"],
              ]}
            />
          </div>

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
            <TextField
              label="Statepoint HDF5"
              value={statepointPath}
              onChange={setStatepointPath}
              onBrowse={() => setBrowserTarget("statepoint")}
              placeholder="/path/to/statepoint.h5"
              disabled={!loadStatepoint}
            />
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <TextField
              label="Run directory"
              value={runDir}
              onChange={setRunDir}
              onBrowse={() => setBrowserTarget("run-dir")}
              placeholder={runDirPlaceholder}
            />
            <TextField
              label="Intermediate HDF5"
              value={keepHdf5Path}
              onChange={setKeepHdf5Path}
              onBrowse={() => setBrowserTarget("hdf5")}
              placeholder={derivedHdf5}
            />
            <TextField
              label="Output ASCII"
              value={outputPath}
              onChange={setOutputPath}
              onBrowse={() => setBrowserTarget("output")}
              placeholder={derivedOutput}
            />
          </div>

          <Segmented
            label="Equivalence method"
            value={equivalence}
            onChange={(value) => setEquivalence(value as OpenmcEquivalenceMode)}
            options={[
              ["direct", "Direct"],
              ["adf", "ADF/DF sidecar"],
              ["sph", "SPH sidecar"],
              ["flux-ratio-adf", "Build flux-ratio ADF"],
            ]}
          />

          {equivalence === "adf" ? (
            <TextField
              label="ADF sidecar"
              value={adfSource}
              onChange={setAdfSource}
              onBrowse={() => setBrowserTarget("adf")}
              placeholder="/path/to/adf_sidecar.h5"
            />
          ) : null}
          {equivalence === "sph" ? (
            <TextField
              label="SPH sidecar"
              value={sphSource}
              onChange={setSphSource}
              onBrowse={() => setBrowserTarget("sph")}
              placeholder="/path/to/sph_sidecar.h5"
            />
          ) : null}

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            <Toggle
              label="Load statepoint"
              checked={loadStatepoint}
              onChange={setLoadStatepoint}
            />
            <Toggle label="Preflight" checked={check} onChange={setCheck} />
            <Toggle
              label="Production gates"
              checked={production}
              onChange={setProduction}
            />
            <Toggle
              label="Known mesh required"
              checked={requireKnownMesh}
              onChange={setRequireKnownMesh}
            />
            <Toggle
              label="Strict dry run"
              checked={strictDryRun}
              onChange={setStrictDryRun}
            />
          </div>

          <TextField
            label="H-factor default"
            value={hFactorText}
            onChange={setHFactorText}
            placeholder="optional; prefer group-wise kappa-fission in HDF5"
          />

          <button
            ref={planButtonRef}
            type="submit"
            className="btn btn-primary"
            disabled={state.kind === "loading"}
          >
            {state.kind === "loading" ? "Planning…" : "Plan workflow"}
          </button>
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
          <PlanReport state={state} />
        </section>
      </div>
    </main>
  );
}

function PlanReport({ state }: { state: PlanState }) {
  if (state.kind === "idle") {
    return (
      <section className="glass rounded-xl p-5">
        <h2 className="text-base font-semibold tracking-tight">
          Ready to plan
        </h2>
        <p className="mt-2 text-sm text-[var(--fg-2)]">
          This planner does not execute OpenMC. It gives you the exact CLI
          commands and artifact map for a production handoff.
        </p>
      </section>
    );
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
              {plan.ok ? "READY" : "NEEDS INPUT"}
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

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plan.steps.map((step, index) => (
          <article
            key={step.id}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.02] p-4"
          >
            <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              {String(index + 1).padStart(2, "0")}
            </div>
            <h3 className="mt-1 text-sm font-semibold">{step.title}</h3>
            <p className="mt-2 text-sm text-[var(--fg-2)]">{step.summary}</p>
          </article>
        ))}
      </section>

      <OpenmcCommandList
        commands={plan.commands}
        primaryCommandText={plan.primary_command_text}
      />

      <section className="grid gap-4 lg:grid-cols-2">
        <Cards
          title="Readiness"
          items={plan.checks.map((check) => ({
            key: check.name,
            label: check.name,
            detail: check.message,
            tone: check.status,
          }))}
        />
        <OpenmcArtifactList artifacts={plan.artifacts} />
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
  items: { key: string; label: string; detail: string; tone: string }[];
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
          </div>
        ))}
      </div>
    </section>
  );
}

function Segmented({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <fieldset>
      <legend className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </legend>
      <div
        className="mt-1 grid overflow-hidden rounded-md border border-[var(--edge)]"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {options.map(([id, text]) => (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            className={segmentClass(value === id)}
          >
            {text}
          </button>
        ))}
      </div>
    </fieldset>
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
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 text-sm text-[var(--fg-1)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-emerald-500"
      />
      <span>{label}</span>
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

function toneClass(tone: string): string {
  if (tone === "pass") return "border-emerald-400/30 text-emerald-300";
  if (tone === "warn") return "border-amber-400/30 text-amber-300";
  if (tone === "fail") return "border-rose-400/30 text-rose-300";
  return "border-[var(--edge-bright)] text-[var(--fg-2)]";
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
  return {
    initialPath: pickBrowserStart(values.sphSource || values.savedPrefix),
    extensions: ["h5", "hdf5"],
    fileTypeLabel: "SPH sidecar",
    chipLabel: "H5",
    recentScope: "openmc-sph",
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
