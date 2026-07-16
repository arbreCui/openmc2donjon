import {
  FormEvent,
  useRef,
  useState,
} from "react";
import Link from "next/link";

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
import { FormStep } from "@/components/ui/Workflow";

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
  requireAppliedRateSph = false,
  requireIrenaColorsetSph = false,
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
  requireAppliedRateSph?: boolean;
  requireIrenaColorsetSph?: boolean;
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
    requirePhysicalSph: requireAppliedRateSph,
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
        className="surface space-y-3 p-4 sm:p-5"
        onSubmit={submitDryRun}
      >
        <FormStep
          number="1"
          title={requireIrenaColorsetSph ? "Select the completed IRENA colorset HDF5" : requireAppliedRateSph ? "Select the physical-SPH-applied HDF5" : "Select the Converter input HDF5"}
          description={requireIrenaColorsetSph ? "This IRENA template component explicitly requires its seven-domain center-plus-neighbors topology and pre-applied physical SPH." : requireAppliedRateSph ? "This handoff requires pre-applied physical rate-SPH on the domains declared by this HDF5. No fixed geometry or domain count is assumed." : "Use an openmc2donjon MGXS handoff exported from OpenMC. A raw OpenMC statepoint, summary.h5, or arbitrary MGXS-library file is not yet the Converter contract. No project, fixed domain count, or SPH record is assumed."}
        >
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                MGXS HDF5
              </span>
              <input
                type="text"
                placeholder={inputPlaceholder}
                value={inputPath}
                onChange={(event) => onInputChange(event.target.value)}
                className="mt-1 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
                spellCheck={false}
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              onClick={() => setBrowserTarget("input")}
              className="btn btn-secondary self-end"
            >
              Browse HDF5
            </button>
          </div>

          {canUseSavedPrefix ? (
            <button
              type="button"
              onClick={() => onInputChange(savedPrefix)}
              className="btn-link mt-1"
            >
              Use saved prefix: <code className="font-mono">{savedPrefix}</code>
            </button>
          ) : null}

          <p className="mt-3 text-[11px] leading-5 text-[var(--fg-3)]">
            {inputPath.trim() ? (
              <>
                <Link
                  href={`/inspect?path=${encodeURIComponent(inputPath.trim())}`}
                  className="font-semibold text-[var(--accent-2)] hover:underline"
                >
                  Inspect this handoff contract
                </Link>{" "}
                before the production dry run.
              </>
            ) : (
              <>
                Starting from an OpenMC recipe or statepoint?{" "}
                <Link
                  href="/openmc?workflow=two-step&equivalence=direct"
                  className="font-semibold text-[var(--accent-2)] hover:underline"
                >
                  Prepare the handoff first
                </Link>
                .
              </>
            )}
          </p>
          <p className="mt-1 text-[11px] leading-5 text-[var(--fg-3)]">
            This is a path on the machine running the openmc2donjon backend,
            not a browser upload path.
          </p>
        </FormStep>

        <FormStep
          number="2"
          title="Choose what this handoff contains"
          description="First choose the downstream object and the exact mixture scope. A component-only user can select one component here and stop after Converter writes the receipt."
        >
          <OutputObjectSelector format={format} onChange={onFormatChange} />

          <fieldset className="mb-4 rounded-xl border border-[var(--edge)] bg-black/10 p-4">
            <legend className="px-1 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              Mixture / domain scope
            </legend>
            <p className="mb-3 text-[12px] leading-5 text-[var(--fg-2)]">
              Empty means every mixture in the HDF5. Inspect the file, then keep
              the default or choose an explicit subset for this component.
            </p>
            <MixturePicker
              inputPath={inputPath}
              value={mixturesText}
              onChange={onMixturesTextChange}
            />
            <label
              htmlFor="convert-mixture-filter"
              className="mt-3 block text-[11px] uppercase tracking-wider text-[var(--fg-3)]"
            >
              Exact mixture names
            </label>
            <textarea
              id="convert-mixture-filter"
              value={mixturesText}
              onChange={(event) => onMixturesTextChange(event.target.value)}
              placeholder="Leave empty for all mixtures, or enter one name per line"
              className="mt-1 min-h-20 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
              spellCheck={false}
            />
            <span className="mt-1 block text-[12px] text-[var(--fg-3)]">
              Blank = all mixtures. A non-blank comma/newline list = only that explicit subset.
            </span>
          </fieldset>

          <div>
            <WriterBackendSelector
              value={writerBackend}
              onChange={onWriterBackendChange}
              status={pyganStatus}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
                Output ASCII
              </span>
              <input
                type="text"
                value={outputPath}
                onChange={(event) => onOutputChange(event.target.value)}
                className="mt-1 w-full min-w-0 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
                spellCheck={false}
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              onClick={() => setBrowserTarget("output-directory")}
              className="btn btn-secondary self-end"
            >
              Browse output
            </button>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-[var(--fg-3)]">
            The output is written by the backend host. Choose a directory that
            backend process can write.
          </p>
        </FormStep>

        <FormStep
          number="3"
          title="Choose the validation gate, then run"
          description="Production is the formal handoff gate. Standard is an engineering preflight only; None is reserved for diagnostics."
        >
          <div className="mb-3">
            <ChecksControl
              check={check}
              production={production}
              requireKnownMesh={requireKnownMesh}
              onCheckChange={onCheckChange}
              onProductionChange={onProductionChange}
              onRequireKnownMeshChange={onRequireKnownMeshChange}
            />
          </div>
          <div>
            <DirectConvertActionPanel
              state={state}
              inputPath={inputPath}
              outputPath={outputPath}
              check={check}
              production={production}
              format={format}
              writerBackend={writerBackend}
              onConvert={onConvert}
              convertButtonRef={convertButtonRef}
              requireAppliedRateSph={requireAppliedRateSph}
              requireMulticompo={requireIrenaColorsetSph}
            />
          </div>
        </FormStep>

        <details className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
          <summary className="cursor-pointer text-sm font-semibold tracking-tight text-[var(--fg-0)]">
            Advanced metadata and exact CLI
          </summary>
          <label className="mt-4 flex max-w-xl items-center gap-2 rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2 text-[12px] text-[var(--fg-1)]">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(event) => onOverwriteChange(event.target.checked)}
              className="accent-emerald-500"
            />
            Overwrite an existing output file
          </label>
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
              disabled={production}
              hint={production
                ? "Forbidden for a formal production handoff. Export the physical group-wise H-FACTOR / kappa-fission data in the HDF5."
                : "Diagnostic plumbing only; never a substitute for physical group-wise data in production."}
            />
            <Field
              label="COMMENT block"
              value={comment}
              onChange={onCommentChange}
              placeholder="OpenMC direct homogenization"
              hint="Optional comment written into MULTICOMPO output."
            />
          </div>
          <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold tracking-tight">
                  Exact no-write CLI
                </div>
                <div className="mt-1 text-[12px] text-[var(--fg-3)]">
                  Use this only when running the same validation in a terminal.
                </div>
              </div>
              <CopyCliButton value={cliPreview} />
            </div>
            <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
              {cliPreview}
            </pre>
          </section>
        </details>
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

function OutputObjectSelector({
  format,
  onChange,
}: {
  format: ConvertFormat;
  onChange: (value: ConvertFormat) => void;
}) {
  return (
    <fieldset className="mb-4 rounded-xl border border-[var(--edge)] bg-black/10 p-4">
      <legend className="px-1 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        Output object
      </legend>
      <div className="grid max-w-xl grid-cols-2 overflow-hidden rounded-md border border-[var(--edge)]">
        <button
          type="button"
          onClick={() => onChange("multicompo")}
          aria-pressed={format === "multicompo"}
          className={segmentClass(format === "multicompo")}
        >
          Component / state library · L_MULTICOMPO
        </button>
        <button
          type="button"
          onClick={() => onChange("macrolib")}
          aria-pressed={format === "macrolib"}
          className={segmentClass(format === "macrolib")}
        >
          Direct macrolib · L_MACROLIB
        </button>
      </div>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-3)]">
        {format === "multicompo"
          ? "Choose this for a reusable component or state library. DONJON can select named mixtures and calculation records later. This does not mean the model is a full core."
          : "Choose this only when the downstream calculation expects one root macrolib directly, without a MULTICOMPO component/state container."}
      </p>
    </fieldset>
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
    return "control-segment px-3 py-2 text-[12px] font-semibold uppercase tracking-wider bg-white/[0.01] text-[var(--fg-3)] cursor-not-allowed";
  }
  return (
    "control-segment px-3 py-2 text-[12px] font-semibold uppercase tracking-wider transition " +
    (active
      ? "bg-emerald-400/15 text-emerald-200"
      : "bg-white/[0.02] text-[var(--fg-2)] hover:text-[var(--fg-0)]")
  );
}
