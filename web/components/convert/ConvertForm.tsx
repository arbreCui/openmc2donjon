import {
  FormEvent,
  useRef,
  useState,
} from "react";

import { CopyCliButton } from "@/components/commands/CopyCliButton";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import type {
  ConvertFormat,
  ConvertWriterBackend,
  PyGanBackendStatus,
} from "@/lib/api";
import {
  CONVERT_CHECKS_LEVELS,
  convertChecksFlags,
  convertChecksLevel,
  convertChecksLevelDescription,
  convertChecksLevelLabel,
  type ConvertChecksLevel,
} from "@/lib/convertChecks";
import { buildConvertCliPreview } from "@/lib/convertCommand";
import {
  outputPathInDirectory,
  pickConvertBrowserStart,
} from "@/lib/convertPaths";
import type { ConvertRunState } from "./ConvertReportState";
import DirectConvertActionPanel from "./DirectConvertActionPanel";
import MixturePicker from "./MixturePicker";
import WriterBackendSelector from "./WriterBackendSelector";

type BrowserTarget = "input" | "output-directory";

export default function ConvertForm({
  state,
  inputPath,
  inputPlaceholder,
  canUseSavedPrefix,
  savedPrefix,
  outputPath,
  format,
  writerBackend,
  pyganStatus,
  check,
  production,
  requireKnownMesh,
  overwrite,
  rootName,
  comment,
  burnup,
  hFactorDefault,
  mixturesText,
  onInputChange,
  onFormatChange,
  onOutputChange,
  onWriterBackendChange,
  onCheckChange,
  onProductionChange,
  onRequireKnownMeshChange,
  onOverwriteChange,
  onRootNameChange,
  onCommentChange,
  onBurnupChange,
  onHFactorDefaultChange,
  onMixturesTextChange,
  onDryRun,
  onConvert,
}: {
  state: ConvertRunState;
  inputPath: string;
  inputPlaceholder: string;
  canUseSavedPrefix: boolean;
  savedPrefix: string;
  outputPath: string;
  format: ConvertFormat;
  writerBackend: ConvertWriterBackend;
  pyganStatus: PyGanBackendStatus | null;
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
  overwrite: boolean;
  rootName: string;
  comment: string;
  burnup: string;
  hFactorDefault: string;
  mixturesText: string;
  onInputChange: (value: string) => void;
  onFormatChange: (value: ConvertFormat) => void;
  onOutputChange: (value: string) => void;
  onWriterBackendChange: (value: ConvertWriterBackend) => void;
  onCheckChange: (value: boolean) => void;
  onProductionChange: (value: boolean) => void;
  onRequireKnownMeshChange: (value: boolean) => void;
  onOverwriteChange: (value: boolean) => void;
  onRootNameChange: (value: string) => void;
  onCommentChange: (value: string) => void;
  onBurnupChange: (value: string) => void;
  onHFactorDefaultChange: (value: string) => void;
  onMixturesTextChange: (value: string) => void;
  onDryRun: () => void;
  onConvert: () => void;
}) {
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const convertButtonRef = useRef<HTMLButtonElement | null>(null);
  const cliPreview = buildConvertCliPreview({
    inputPath,
    outputPath,
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

  function submitDryRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onDryRun();
  }

  function applyBrowserPick(picked: string) {
    if (browserTarget === "input") {
      onInputChange(picked);
    } else if (browserTarget === "output-directory") {
      onOutputChange(
        outputPathInDirectory({
          directory: picked,
          currentOutput: outputPath,
          inputPath,
          format,
        }),
      );
    }
    setBrowserTarget(null);
    convertButtonRef.current?.focus();
  }

  return (
    <>
      <form
        className="glass rounded-xl p-4 space-y-4"
        onSubmit={submitDryRun}
      >
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              MGXS HDF5
            </span>
            <input
              type="text"
              placeholder={inputPlaceholder}
              value={inputPath}
              onChange={(event) => onInputChange(event.target.value)}
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
            onClick={() => onInputChange(savedPrefix)}
            className="text-[12px] text-[var(--accent-2)] hover:underline"
          >
            Use saved prefix: <code className="font-mono">{savedPrefix}</code>
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
                onClick={() => onFormatChange("multicompo")}
                className={segmentClass(format === "multicompo")}
              >
                MULTICOMPO
              </button>
              <button
                type="button"
                onClick={() => onFormatChange("macrolib")}
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
              value={outputPath}
              onChange={(event) => onOutputChange(event.target.value)}
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

        <p className="text-[12px] leading-snug text-[var(--fg-3)]">
          Carrying SPH factors? Choose MACROLIB (DSPH: + MAC:) or pre-apply
          with apply-sph — NCR: does not read NSPH from MULTICOMPO. Clean XS
          for NCR:? MULTICOMPO.
        </p>

        <ChecksControl
          check={check}
          production={production}
          requireKnownMesh={requireKnownMesh}
          onCheckChange={onCheckChange}
          onProductionChange={onProductionChange}
          onRequireKnownMeshChange={onRequireKnownMeshChange}
        />

        <DirectConvertActionPanel
          state={state}
          inputPath={inputPath}
          outputPath={outputPath}
          check={check}
          production={production}
          format={format}
          writerBackend={writerBackend}
          overwrite={overwrite}
          onOverwriteChange={onOverwriteChange}
          onConvert={onConvert}
          convertButtonRef={convertButtonRef}
        />

        <details className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
          <summary className="cursor-pointer text-sm font-semibold tracking-tight text-[var(--fg-0)]">
            Advanced converter options
          </summary>
          <div className="mt-4">
            <WriterBackendSelector
              value={writerBackend}
              onChange={onWriterBackendChange}
              status={pyganStatus}
            />
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <Field
              label="LCM root name"
              value={rootName}
              onChange={onRootNameChange}
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
              onChange={onBurnupChange}
              placeholder="0.0"
              mono
              hint="Optional single-point BURN axis metadata."
            />
            <Field
              label="H-FACTOR default"
              value={hFactorDefault}
              onChange={onHFactorDefaultChange}
              placeholder="200.0"
              mono
              hint="Only for plumbing/demo cases when the HDF5 lacks H-FACTOR."
            />
            <Field
              label="COMMENT block"
              value={comment}
              onChange={onCommentChange}
              placeholder="OpenMC direct homogenization"
              hint="Optional comment written into MULTICOMPO output."
            />
            <div className="lg:col-span-2">
              <label
                htmlFor="convert-mixture-filter"
                className="block text-[11px] uppercase tracking-wider text-[var(--fg-3)]"
              >
                Mixture filter
              </label>
              <div className="mt-1 space-y-3">
                <MixturePicker
                  inputPath={inputPath}
                  value={mixturesText}
                  onChange={onMixturesTextChange}
                />
                <textarea
                  id="convert-mixture-filter"
                  value={mixturesText}
                  onChange={(event) => onMixturesTextChange(event.target.value)}
                  placeholder="ASM_Y01_X01, ASM_Y01_X02"
                  className="min-h-20 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
                  spellCheck={false}
                />
              </div>
              <span className="mt-1 block text-[12px] text-[var(--fg-3)]">
                Optional comma/newline list. Empty means write every mixture.
              </span>
            </div>
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
            ? pickConvertBrowserStart(outputPath || savedPrefix)
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
    </>
  );
}

function ChecksControl({
  check,
  production,
  requireKnownMesh,
  onCheckChange,
  onProductionChange,
  onRequireKnownMeshChange,
}: {
  check: boolean;
  production: boolean;
  requireKnownMesh: boolean;
  onCheckChange: (value: boolean) => void;
  onProductionChange: (value: boolean) => void;
  onRequireKnownMeshChange: (value: boolean) => void;
}) {
  const level = convertChecksLevel(check, production);

  function applyLevel(next: ConvertChecksLevel) {
    const flags = convertChecksFlags(next);
    onCheckChange(flags.check);
    onProductionChange(flags.production);
    // "Known mesh required" is scoped to the production preset; clear it when
    // leaving so no hidden flag leaks into the copied CLI.
    if (next !== "production" && requireKnownMesh) {
      onRequireKnownMeshChange(false);
    }
  }

  return (
    <fieldset className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-3">
      <legend className="px-1 text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        Checks
      </legend>
      <div className="grid max-w-md grid-cols-3 overflow-hidden rounded-md border border-[var(--edge)]">
        {CONVERT_CHECKS_LEVELS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => applyLevel(option)}
            aria-pressed={level === option}
            className={segmentClass(level === option)}
          >
            {convertChecksLevelLabel(option)}
          </button>
        ))}
      </div>
      <span className="mt-1 block text-[12px] leading-snug text-[var(--fg-3)]">
        {convertChecksLevelDescription(level)}
      </span>
      {level === "production" ? (
        <div className="mt-2 max-w-md">
          <Toggle
            label="Known mesh required"
            description="Fail unless the energy grid matches a known standard mesh."
            checked={requireKnownMesh}
            onChange={onRequireKnownMeshChange}
          />
        </div>
      ) : null}
    </fieldset>
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
