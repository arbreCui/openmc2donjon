"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import ConvertReport, {
  ConvertRunState,
} from "@/components/convert/ConvertReport";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
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
import { useSettings } from "@/lib/settings";

const FALLBACK_INPUT = "/path/to/mgxs_library.h5";

export default function ConvertPage() {
  const [inputPath, setInputPath] = useState("");
  const [outputPath, setOutputPath] = useState("");
  const [format, setFormat] = useState<ConvertFormat>("multicompo");
  const [check, setCheck] = useState(true);
  const [production, setProduction] = useState(false);
  const [requireKnownMesh, setRequireKnownMesh] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [rootName, setRootName] = useState("CPO");
  const [comment, setComment] = useState("");
  const [burnup, setBurnup] = useState("");
  const [hFactorDefault, setHFactorDefault] = useState("");
  const [mixturesText, setMixturesText] = useState("");
  const [browserOpen, setBrowserOpen] = useState(false);
  const [outputTouched, setOutputTouched] = useState(false);
  const [state, setState] = useState<ConvertRunState>({ kind: "idle" });
  const convertButtonRef = useRef<HTMLButtonElement | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const inputPlaceholder = savedPrefix || FALLBACK_INPUT;
  const derivedOutput = useMemo(
    () => defaultOutputPath(inputPath, format),
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

  function updateInput(value: string) {
    setInputPath(value);
    if (!outputTouched) setOutputPath(defaultOutputPath(value, format));
  }

  function updateFormat(value: ConvertFormat) {
    setFormat(value);
    if (!outputTouched) setOutputPath(defaultOutputPath(inputPath, value));
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
              onClick={() => setBrowserOpen(true)}
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

          <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
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
            </label>
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Toggle
              label="Preflight"
              checked={check}
              onChange={setCheck}
            />
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
              label="Overwrite output"
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
          open={browserOpen}
          initialPath={pickBrowserStart(inputPath.trim() || savedPrefix)}
          extensions={["h5", "hdf5"]}
          fileTypeLabel="HDF5"
          chipLabel="H5"
          recentScope="hdf5"
          onClose={() => setBrowserOpen(false)}
          onSelect={(picked) => {
            updateInput(picked);
            setBrowserOpen(false);
            convertButtonRef.current?.focus();
          }}
        />

        <section className="mt-6">
          <ConvertReport state={state} />
        </section>
      </div>
    </main>
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

function optionalNumberError(label: string, value: string): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  if (Number.isFinite(Number(trimmed))) return null;
  return `${label} must be a number.`;
}

function defaultOutputPath(input: string, format: ConvertFormat): string {
  const trimmed = input.trim();
  const extension = format === "macrolib" ? ".macrolib.txt" : ".mcompo.txt";
  if (!trimmed) return `out${extension}`;
  const slash = trimmed.lastIndexOf("/");
  const dirname = slash >= 0 ? trimmed.slice(0, slash + 1) : "";
  const basename = slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
  const dot = basename.lastIndexOf(".");
  const stem = dot > 0 ? basename.slice(0, dot) : basename;
  return `${dirname}${stem}${extension}`;
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
