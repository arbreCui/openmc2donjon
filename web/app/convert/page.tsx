"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  ConvertFormat,
  ConvertPreflightInput,
  ConvertResponse,
  api,
} from "@/lib/api";
import { useSettings } from "@/lib/settings";

const FALLBACK_INPUT = "/path/to/mgxs_library.h5";

type State =
  | { kind: "idle" }
  | { kind: "loading"; mode: "dry-run" | "convert" }
  | { kind: "ok"; data: ConvertResponse }
  | { kind: "error"; message: string; status?: number };

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
  const [state, setState] = useState<State>({ kind: "idle" });
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
          <ConvertResult state={state} />
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

function ConvertResult({ state }: { state: State }) {
  if (state.kind === "idle") {
    return (
      <p className="text-sm text-[var(--fg-3)]">
        Mock backend returns a C5G7-shape conversion preview for any path.
      </p>
    );
  }
  if (state.kind === "loading") {
    return (
      <p className="text-sm text-[var(--fg-2)] tab-num">
        {state.mode === "dry-run" ? "Checking…" : "Converting…"}
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="glass rounded-xl p-5 border-rose-500/20">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Request failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
      </div>
    );
  }
  return <ConvertReport data={state.data} />;
}

function ConvertReport({ data }: { data: ConvertResponse }) {
  const input = data.preflight?.inputs[0] ?? null;
  const status = data.ok ? "PASS" : "FAIL";
  const tone = data.ok ? "text-emerald-300" : "text-rose-300";
  return (
    <div className="space-y-4">
      <section className="glass rounded-xl p-5">
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <div className={`text-sm font-semibold ${tone}`}>{status}</div>
            <h2 className="mt-1 text-lg font-semibold tracking-tight">
              {data.dry_run
                ? "Dry run complete"
                : data.converted
                  ? "ASCII written"
                  : "Conversion stopped"}
            </h2>
          </div>
          <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
            {data.format}
          </span>
        </div>

        <dl className="mt-4 grid gap-3 md:grid-cols-2 text-sm">
          <Meta label="Input" value={data.input_path} mono />
          <Meta label="Output" value={data.output_path} mono />
          <Meta
            label="Output size"
            value={data.output_size == null ? "—" : formatSize(data.output_size)}
          />
          <Meta
            label="Preflight"
            value={data.preflight_ok ? "pass" : "fail"}
          />
        </dl>

        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            CLI equivalent
          </div>
          <pre className="mt-1 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-[12px] text-[var(--fg-1)]">
            {data.cli_command_text}
          </pre>
        </div>
      </section>

      {input ? <PreflightCard input={input} /> : null}
    </div>
  );
}

function PreflightCard({ input }: { input: ConvertPreflightInput }) {
  const mesh = input.energy_mesh_id ?? "unknown";
  const stats = [
    ["groups", input.energy_groups],
    ["moments", input.legendre_order == null ? null : input.legendre_order + 1],
    ["mixtures", input.mixtures],
    ["states", input.state_points],
    ["fissionable", input.fissionable_mixtures],
    ["ADF mixes", input.adf_mixtures],
    ["SPH calcs", input.sph_calculations],
    ["std_dev", coverage(input)],
  ];
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <h2 className="text-base font-semibold tracking-tight">
          Input contract
        </h2>
        <span
          className={
            "rounded border px-2 py-1 text-[11px] uppercase tracking-wider " +
            (input.ok
              ? "border-emerald-400/30 text-emerald-300"
              : "border-rose-400/30 text-rose-300")
          }
        >
          {input.ok ? "pass" : "fail"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
        {stats.map(([label, value]) => (
          <div
            key={label}
            className="rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2"
          >
            <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
              {label}
            </div>
            <div className="mt-1 text-sm tab-num text-[var(--fg-0)]">
              {value == null ? "—" : String(value)}
            </div>
          </div>
        ))}
      </div>

      <dl className="mt-4 grid gap-2 md:grid-cols-2 text-sm">
        <Meta label="Energy mesh" value={mesh} />
        <Meta
          label="Row balance"
          value={formatRelative(input.scatter_row_balance?.max_rel)}
        />
        <Meta
          label="Chi max error"
          value={formatRelative(input.physics_checks?.chi_sum_max_abs_error)}
        />
        <Meta
          label="Uncertainty max"
          value={formatRelative(input.uncertainty?.max_rel)}
        />
      </dl>

      <IssueList title="Issues" items={input.issues} tone="rose" />
      <IssueList title="Warnings" items={input.warnings} tone="amber" />
    </section>
  );
}

function IssueList({
  title,
  items,
  tone,
}: {
  title: string;
  items: readonly string[];
  tone: "rose" | "amber";
}) {
  if (items.length === 0) return null;
  const color = tone === "rose" ? "text-rose-300" : "text-amber-300";
  return (
    <div className="mt-4">
      <div className={`text-sm font-semibold ${color}`}>{title}</div>
      <ul className="mt-1 space-y-1 text-sm text-[var(--fg-1)]">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function Meta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </dt>
      <dd
        className={
          "mt-0.5 truncate text-[var(--fg-1)] " + (mono ? "font-mono" : "")
        }
        title={value}
      >
        {value}
      </dd>
    </div>
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

function coverage(input: ConvertPreflightInput): string | null {
  const datasets = input.uncertainty?.datasets;
  const expected = input.uncertainty?.expected_datasets;
  if (datasets == null || expected == null) return null;
  return `${datasets}/${expected}`;
}

function formatRelative(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs < 1.0e-3 || abs >= 1.0e3) return value.toExponential(3);
  return value.toPrecision(4);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

function toErrorState(err: unknown): Extract<State, { kind: "error" }> {
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
