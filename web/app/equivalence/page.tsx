"use client";

import Link from "next/link";
import { Suspense, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import OpenmcSphWorkflowPanel from "@/components/OpenmcSphWorkflowPanel";
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
import { isOpenmcSphEquivalenceKind } from "@/lib/openmcSphWorkflow";
import { useSettings } from "@/lib/settings";

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
  | "table";

export default function EquivalencePage() {
  return (
    <Suspense fallback={<EquivalenceLoading />}>
      <EquivalencePageContent />
    </Suspense>
  );
}

function EquivalenceLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading equivalence tools…
        </section>
      </div>
    </main>
  );
}

function EquivalencePageContent() {
  const searchParams = useSearchParams();
  const kind = parseEquivalenceKind(searchParams.get("kind"));
  const info = equivalenceKindInfo(kind);
  const [options, setOptions] = useState<EquivalenceCommandOptions>(
    defaultEquivalenceOptions(kind),
  );
  const [outputTouched, setOutputTouched] = useState(false);
  const [browserTarget, setBrowserTarget] = useState<BrowserTarget | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const firstInputRef = useRef<HTMLInputElement | null>(null);

  const activeOptions = useMemo(
    () => ({
      ...options,
      kind,
      outputPath: outputTouched ? options.outputPath : info.outputPlaceholder,
    }),
    [info.outputPlaceholder, kind, options, outputTouched],
  );
  const cli = buildEquivalenceCli(activeOptions);
  const canUseSavedPrefix =
    settingsHydrated &&
    savedPrefix !== "" &&
    !options.inputH5.startsWith(savedPrefix);

  function patch(values: Partial<EquivalenceCommandOptions>) {
    setOptions((current) => ({ ...current, ...values }));
  }

  function applyBrowserPick(path: string) {
    if (browserTarget === "outputDir") {
      patch({
        outputPath: outputPathInDirectory(path, activeOptions.outputPath, info.outputPlaceholder),
      });
      setOutputTouched(true);
    } else if (browserTarget) {
      patch({ [browserTarget]: path } as Partial<EquivalenceCommandOptions>);
    }
    setBrowserTarget(null);
    firstInputRef.current?.focus();
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="grad-text">Equivalence sidecars</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Build trustworthy CLI commands for one-shot ADF/DF or SPH sidecar workflows.
            This web page does not mutate files; run the copied command in a terminal.
          </p>
        </header>

        <EquivalenceTabs active={kind} />

        <section className="glass rounded-xl p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
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
            <Link href={`/commands/${info.commandId}`} className="btn btn-secondary shrink-0">
              Command guide
            </Link>
          </div>

          {isOpenmcSphEquivalenceKind(kind) ? (
            <OpenmcSphWorkflowPanel activeCommandId={info.commandId} />
          ) : null}

          <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_360px]">
            <div className="space-y-4">
              <PathField
                label="Input MGXS HDF5"
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
                  className="text-[12px] text-[var(--accent-2)] hover:underline"
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
              {kind === "sph-sidecar" ? (
                <SphSidecarFields options={options} patch={patch} setBrowserTarget={setBrowserTarget} />
              ) : null}
              {kind === "augment-sph" ? (
                <AugmentSphFields options={options} patch={patch} setBrowserTarget={setBrowserTarget} />
              ) : null}

              <details className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
                <summary className="cursor-pointer text-sm font-semibold tracking-tight">
                  Common CLI options
                </summary>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <TextField
                    label="Summary JSON"
                    value={options.summaryJson}
                    onChange={(value) => patch({ summaryJson: value })}
                    placeholder="summary.json"
                    mono
                    hint="Optional machine-readable command summary path."
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

            <aside className="h-fit rounded-lg border border-[var(--edge)] bg-black/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold tracking-tight">CLI preview</h3>
                  <p className="mt-1 text-[12px] text-[var(--fg-3)]">
                    Copy and run this command locally. No web endpoint writes files here.
                  </p>
                </div>
                <CopyCliButton value={cli} compact />
              </div>
              <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
                {cli}
              </pre>
              <div className="mt-3 rounded-md border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-[12px] leading-relaxed text-amber-100">
                ADF/SPH factors are physics inputs. This builder helps avoid flag mistakes;
                it does not judge whether the sidecar values are physically appropriate.
              </div>
            </aside>
          </div>
        </section>

        <FileBrowserModal
          open={browserTarget != null}
          initialPath={browserInitialPath(browserTarget, activeOptions, savedPrefix)}
          extensions={browserExtensions(browserTarget)}
          fileTypeLabel={browserTarget === "outputDir" ? "output directory" : "input file"}
          chipLabel={browserTarget === "outputDir" ? "DIR" : browserChip(browserTarget)}
          recentScope={`equivalence-${browserTarget ?? "file"}`}
          selectMode={browserTarget === "outputDir" ? "directory" : "file"}
          onClose={() => setBrowserTarget(null)}
          onSelect={applyBrowserPick}
        />
      </div>
    </main>
  );
}

function EquivalenceTabs({ active }: { active: EquivalenceKind }) {
  return (
    <nav className="mb-5 grid gap-2 md:grid-cols-3 lg:grid-cols-5" aria-label="Equivalence tool">
      {EQUIVALENCE_KINDS.map((item) => (
        <Link
          key={item.kind}
          href={`/equivalence?kind=${item.kind}`}
          className={
            "rounded-lg border px-3 py-2 transition " +
            (active === item.kind
              ? "border-emerald-300/30 bg-emerald-300/[0.08] text-emerald-100"
              : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)] hover:text-[var(--fg-0)]")
          }
          aria-current={active === item.kind ? "page" : undefined}
        >
          <div className="text-sm font-semibold tracking-tight">{item.label}</div>
          <div className="mt-1 font-mono text-[11px] text-[var(--fg-3)]">
            {item.commandId}
          </div>
        </Link>
      ))}
    </nav>
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
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-white/[0.015] p-4">
      <h3 className="text-sm font-semibold tracking-tight">OpenMC CE/MG SPH options</h3>
      <p className="mt-1 text-[12px] leading-relaxed text-[var(--fg-3)]">
        Use fluxes from the same OpenMC geometry and output regions: CE is the reference;
        MG is the macro calculation being corrected.
      </p>
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
        <PathField
          label="SPH CSV table"
          value={options.tableOutput}
          onChange={(value) => patch({ tableOutput: value })}
          onBrowse={() => setBrowserTarget("tableOutput")}
          placeholder="sph_sidecar.sph.csv"
        />
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
          hint="Use 1.0 for one-shot factors; lower values damp an iterative update."
        />
        <SelectField
          label="Flux normalization"
          value={options.fluxNormalization}
          onChange={(value) =>
            patch({ fluxNormalization: value as "none" | "total" | "power" | "auto" })
          }
          options={[
            ["none", "none"],
            ["total", "total flux"],
            ["power", "power weighted"],
            ["auto", "auto"],
          ]}
          hint="Optional global scaling before forming MG/CE flux ratios."
        />
        <SelectField
          label="SPH target"
          value={options.sphTarget}
          onChange={(value) => patch({ sphTarget: value as "flux" | "rate" })}
          options={[
            ["flux", "flux (match CE flux)"],
            ["rate", "rate (preserve reaction rates)"],
          ]}
          hint="flux matches the corrected MG flux to CE; rate preserves reaction rates in spatially coupled regions."
        />
        <SelectField
          label="Zero-flux policy"
          value={options.zeroFluxPolicy}
          onChange={(value) => patch({ zeroFluxPolicy: value as "reject" | "identity" })}
          options={[
            ["reject", "reject (fail on zero bins)"],
            ["identity", "identity (keep previous SPH)"],
          ]}
          hint="identity keeps previous SPH where both CE and MG flux are exactly zero, e.g. fast-spectrum thermal groups."
        />
        <TextField
          label="Flux floor (relative)"
          value={options.fluxFloorRel}
          onChange={(value) => patch({ fluxFloorRel: value })}
          placeholder="1e-3"
          mono
          hint="Freeze bins below this fraction of the mixture's peak CE flux so noisy near-zero groups are not fitted."
        />
        <TextField
          label="Freeze groups"
          value={options.freezeGroups}
          onChange={(value) => patch({ freezeGroups: value })}
          placeholder="1,31"
          mono
          hint="Comma-separated 1-based group indices whose SPH is frozen at the previous value for all mixtures."
        />
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
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
  placeholder: string;
  inputRef?: React.Ref<HTMLInputElement>;
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
          Browse…
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

function browserInitialPath(
  target: BrowserTarget | null,
  options: EquivalenceCommandOptions,
  savedPrefix: string,
): string {
  const value = browserTargetValue(target, options);
  return browserStart(value || savedPrefix || "~");
}

function browserTargetValue(
  target: BrowserTarget | null,
  options: EquivalenceCommandOptions,
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
  };
  return values[target];
}

function browserStart(path: string): string {
  const trimmed = path.trim();
  if (trimmed === "") return "~";
  if (trimmed.endsWith("/")) return trimmed;
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return "~";
  return trimmed.slice(0, index);
}

function browserExtensions(target: BrowserTarget | null): readonly string[] {
  if (target === "outputDir") return [];
  if (target === "table" || target === "tableOutput") return ["csv"];
  if (target === "previousSph") return ["h5", "hdf5", "csv"];
  if (target === "macrolib") return ["txt", "mco"];
  return ["h5", "hdf5"];
}

function browserChip(target: BrowserTarget | null): string {
  if (target === "table" || target === "tableOutput") return "CSV";
  if (target === "macrolib") return "TXT";
  return "H5";
}

function outputPathInDirectory(
  directory: string,
  currentOutput: string,
  fallbackName: string,
): string {
  const filename = basename(currentOutput) || fallbackName;
  return `${directory.replace(/\/+$/, "")}/${filename}`;
}

function basename(path: string): string {
  const trimmed = path.trim();
  if (trimmed === "") return "";
  const index = trimmed.lastIndexOf("/");
  return index >= 0 ? trimmed.slice(index + 1) : trimmed;
}
