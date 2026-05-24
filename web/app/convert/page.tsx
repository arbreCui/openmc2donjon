"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import ConvertReport, {
  ConvertRunState,
} from "@/components/convert/ConvertReport";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  ConvertFormat,
  api,
} from "@/lib/api";
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

function segmentClass(active: boolean): string {
  return (
    "px-3 py-2 text-[12px] font-semibold uppercase tracking-wider transition " +
    (active
      ? "bg-emerald-400/15 text-emerald-200"
      : "bg-white/[0.02] text-[var(--fg-2)] hover:text-[var(--fg-0)]")
  );
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
