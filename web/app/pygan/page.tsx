"use client";

import Link from "next/link";
import type React from "react";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import EvidenceLadder from "@/components/EvidenceLadder";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  ConvertFormat,
  PyGanBackendStatus,
  WriterComparisonResponse,
  api,
} from "@/lib/api";
import {
  PYGAN_CONVERTER_HREF,
  pyganCompareAvailability,
  pyganMissingModulesLabel,
} from "@/lib/pyganBackend";
import { writerComparisonEvidenceLadder } from "@/lib/evidenceLadder";
import {
  browserInitialPath,
  buildCompareCli,
  optionalNumberError,
  optionalNumberValue,
  pyganWorkflowHrefs,
  parseMixtures,
  PYGAN_ATOL_DEFAULT,
  PYGAN_RTOL_DEFAULT,
  toleranceError,
  toleranceValue,
  type PyGanBrowseTarget as BrowseTarget,
} from "@/lib/pyganCompare";
import { useSettings } from "@/lib/settings";
import { projectRootFromSearchParams } from "@/lib/projectWorkspace";

type DoctorState =
  | { kind: "loading" }
  | { kind: "ok"; data: PyGanBackendStatus }
  | { kind: "error"; message: string };

type CompareState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: WriterComparisonResponse }
  | { kind: "error"; message: string; status?: number };

const MOCK_INPUT = "/mock/home/openmc-runs/c5g7/handoff.h5";
const MOCK_SUMMARY = "/mock/home/openmc-runs/c5g7/writer_compare.json";
const MOCK_KEEP = "/mock/home/openmc-runs/c5g7/writer_compare";

export default function PyGanPage() {
  return (
    <Suspense fallback={<PyGanLoading />}>
      <PyGanPageContent />
    </Suspense>
  );
}

function PyGanLoading() {
  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading PyGan workspace…
        </section>
      </div>
    </main>
  );
}

function PyGanPageContent() {
  const searchParams = useSearchParams();
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  const [doctor, setDoctor] = useState<DoctorState>({ kind: "loading" });
  const [compare, setCompare] = useState<CompareState>({ kind: "idle" });
  const [inputH5, setInputH5] = useState(searchParams.get("input_h5") ?? "");
  const [format, setFormat] = useState<ConvertFormat>(
    searchParams.get("format") === "macrolib" ? "macrolib" : "multicompo",
  );
  const [rootName, setRootName] = useState(searchParams.get("root_name") ?? "CPO");
  const [comment, setComment] = useState(searchParams.get("comment") ?? "");
  const [mixtures, setMixtures] = useState(searchParams.getAll("mixture").join(","));
  const [burnup, setBurnup] = useState(searchParams.get("burnup") ?? "");
  const [hFactorDefault, setHFactorDefault] = useState(
    searchParams.get("h_factor_default") ?? "",
  );
  const [rtol, setRtol] = useState(searchParams.get("rtol") ?? "1e-6");
  const [atol, setAtol] = useState(searchParams.get("atol") ?? "1e-8");
  const [summaryJson, setSummaryJson] = useState(
    searchParams.get("summary_json") ?? "",
  );
  const [keepDir, setKeepDir] = useState(searchParams.get("keep_dir") ?? "");
  const [browserTarget, setBrowserTarget] = useState<BrowseTarget | null>(null);
  const projectRoot = projectRootFromSearchParams(searchParams);
  const componentId = searchParams.get("component") ?? "";
  const converterOutput = searchParams.get("output") ?? "";
  const converterReceipt = searchParams.get("receipt") ?? "";

  useEffect(() => {
    let cancelled = false;
    api
      .pyganDoctor()
      .then((data) => {
        if (!cancelled) setDoctor({ kind: "ok", data });
      })
      .catch((err) => {
        const message =
          err instanceof ApiError
            ? err.detail ?? err.message
            : err instanceof Error
              ? err.message
              : "Unknown error";
        if (!cancelled) setDoctor({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cliPreview = useMemo(
    () =>
      buildCompareCli({
        inputH5,
        format,
        rootName,
        comment,
        mixtures,
        burnup,
        hFactorDefault,
        rtol,
        atol,
        summaryJson,
        keepDir,
      }),
    [inputH5, format, rootName, comment, mixtures, burnup, hFactorDefault, rtol, atol, summaryJson, keepDir],
  );
  const doctorData = doctor.kind === "ok" ? doctor.data : null;
  const compareAvailability = pyganCompareAvailability(doctorData);
  const rtolError = toleranceError(rtol);
  const atolError = toleranceError(atol);
  const burnupError = optionalNumberError(burnup, "Burnup");
  const hFactorError = optionalNumberError(hFactorDefault, "H-FACTOR default");
  const workflowHrefs = useMemo(
    () => pyganWorkflowHrefs({
      projectRoot,
      componentId,
      inputH5,
      outputPath: converterOutput,
      receiptPath: converterReceipt,
      format,
      rootName,
      comment,
      mixtures,
      burnup,
      hFactorDefault,
    }),
    [
      burnup,
      comment,
      componentId,
      converterOutput,
      converterReceipt,
      format,
      hFactorDefault,
      inputH5,
      mixtures,
      projectRoot,
      rootName,
    ],
  );
  // In the live available state the availability hint repeats the
  // Doctor panel's "PyGan is importable..." sentence verbatim, so the
  // hint only renders when it adds something (checking / mock / missing
  // modules).
  const hintRepeatsDoctorPanel =
    doctorData !== null && doctorData.available && !doctorData.mock_mode;
  const canUseSavedPrefix =
    settingsHydrated && savedPrefix !== "" && !inputH5.startsWith(savedPrefix);

  function applyMockDemo() {
    setInputH5(MOCK_INPUT);
    setFormat("multicompo");
    setRootName("CPO");
    setComment("PyGan writer comparison web demo");
    setMixtures("");
    setBurnup("");
    setHFactorDefault("");
    setRtol("1e-6");
    setAtol("1e-8");
    setSummaryJson(MOCK_SUMMARY);
    setKeepDir(MOCK_KEEP);
    setCompare({ kind: "idle" });
  }

  async function runCompare() {
    setCompare({ kind: "loading" });
    try {
      const data = await api.pyganCompareWriters({
        input_h5: inputH5.trim(),
        format,
        root_name: rootName.trim() || "CPO",
        comment: comment.trim() || null,
        mixtures: parseMixtures(mixtures),
        burnup: optionalNumberValue(burnup),
        h_factor_default: optionalNumberValue(hFactorDefault),
        rtol: toleranceValue(rtol, PYGAN_RTOL_DEFAULT),
        atol: toleranceValue(atol, PYGAN_ATOL_DEFAULT),
        summary_json: summaryJson.trim() || null,
        keep_dir: keepDir.trim() || null,
      });
      setCompare({ kind: "ok", data });
    } catch (err) {
      if (err instanceof ApiError) {
        setCompare({ kind: "error", status: err.status, message: err.detail ?? err.message });
      } else {
        setCompare({
          kind: "error",
          message: err instanceof Error ? err.message : "Unknown error",
        });
      }
    }
  }

  function applyBrowserPick(path: string) {
    if (browserTarget === "input") setInputH5(path);
    if (browserTarget === "summary") setSummaryJson(path);
    if (browserTarget === "keep") setKeepDir(path);
    setBrowserTarget(null);
  }

  return (
    <main className="app-page">
      <div className="app-container max-w-5xl space-y-5">
        <header>
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--fg-3)]">
            Optional Converter backend
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            <span className="grad-text">PyGan writer &amp; validation</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            The production converter uses the built-in ASCII LCM writer by default.
            When its modules are installed, PyGan is a selectable DRAGON/DONJON-backed
            writer inside Converter as well as a semantic validation layer. Teams can
            therefore write through PyGan, compare it with ASCII, or use ASCII alone.
          </p>
          <Link href={PYGAN_CONVERTER_HREF} className="btn btn-primary mt-4">
            Use PyGan in Converter
            <span aria-hidden="true">→</span>
          </Link>
        </header>

        {projectRoot || converterOutput || converterReceipt ? (
          <section className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.045] p-4">
            <p className="page-kicker">Inherited Converter context</p>
            <h2 className="mt-1 text-sm font-bold">
              Compare the same writer configuration—not a fresh default
            </h2>
            <div className="mt-3 grid gap-2 text-[11px] md:grid-cols-2">
              <PathPill label="project / component" value={projectRoot ? `${projectRoot}${componentId ? ` · ${componentId}` : ""}` : "standalone"} />
              <PathPill label="Converter output" value={converterOutput || "not supplied"} />
              <PathPill label="Converter receipt" value={converterReceipt || "not supplied"} />
              <PathPill label="writer state" value={`root=${rootName || "CPO"} · mixtures=${mixtures || "all"} · burnup=${burnup || "source/default"} · H-factor=${hFactorDefault || "source"}`} />
            </div>
          </section>
        ) : null}

        <DoctorPanel state={doctor} onMockDemo={applyMockDemo} />

        <section className="glass rounded-xl p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold tracking-tight">
                Compare writer backends
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
                This runs the same semantic check as{" "}
                <code className="font-mono">openmc2donjon compare-writers</code>:
                generate ASCII and PyGan outputs, parse both LCM trees, then compare
                payloads with numeric tolerances. It is validation evidence, not a
                prerequisite for normal ASCII conversion.
              </p>
            </div>
            <Link href="/builder?command=compare-writers" className="btn btn-secondary">
              CLI builder
            </Link>
          </div>

          {canUseSavedPrefix ? (
            <button
              type="button"
              onClick={() => setInputH5(savedPrefix)}
              className="btn-link mt-3"
            >
              Use saved prefix: <code className="font-mono">{savedPrefix}</code>
            </button>
          ) : null}

          <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_380px]">
            <div className="grid gap-3 md:grid-cols-2">
              <PathField
                label="MGXS HDF5"
                value={inputH5}
                placeholder="/path/to/mgxs_library.h5"
                onChange={setInputH5}
                onBrowse={() => setBrowserTarget("input")}
              />
              <Field label="Format">
                <select
                  value={format}
                  onChange={(event) => setFormat(event.target.value as ConvertFormat)}
                  className="input"
                >
                  <option value="multicompo">MULTICOMPO</option>
                  <option value="macrolib">MACROLIB</option>
                </select>
              </Field>
              <TextField label="Root name" value={rootName} onChange={setRootName} />
              <TextField label="Comment" value={comment} onChange={setComment} />
              <TextField
                label="Mixture filter"
                value={mixtures}
                onChange={setMixtures}
                placeholder="M1,M2"
              />
              <TextField
                label="Burnup"
                value={burnup}
                onChange={setBurnup}
                placeholder="Inherited Converter value or empty"
                error={burnupError}
              />
              <TextField
                label="H-FACTOR default"
                value={hFactorDefault}
                onChange={setHFactorDefault}
                placeholder="Inherited value or empty"
                error={hFactorError}
              />
              <TextField
                label="Relative tolerance"
                value={rtol}
                onChange={setRtol}
                error={rtolError}
              />
              <TextField
                label="Absolute tolerance"
                value={atol}
                onChange={setAtol}
                error={atolError}
              />
              <PathField
                label="Summary JSON"
                value={summaryJson}
                placeholder="writer_compare.json"
                onChange={setSummaryJson}
                onBrowse={() => setBrowserTarget("summary")}
              />
              <PathField
                label="Keep generated files"
                value={keepDir}
                placeholder="writer_compare"
                onChange={setKeepDir}
                onBrowse={() => setBrowserTarget("keep")}
                directory
              />
            </div>

            <aside className="h-fit rounded-lg border border-[var(--edge)] bg-black/15 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold tracking-tight">CLI preview</h3>
                  <p className="mt-1 text-[12px] text-[var(--fg-3)]">
                    Same command, runnable in a shell.
                  </p>
                </div>
                <CopyCliButton value={cliPreview} compact />
              </div>
              <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
                {cliPreview}
              </pre>
              <button
                type="button"
                onClick={() => void runCompare()}
                disabled={
                  !inputH5.trim() ||
                  compare.kind === "loading" ||
                  !compareAvailability.canRun ||
                  rtolError != null ||
                  atolError != null ||
                  burnupError != null ||
                  hFactorError != null
                }
                className="btn btn-primary mt-4 w-full disabled:cursor-not-allowed disabled:opacity-50"
              >
                {compare.kind === "loading" ? "Comparing…" : "Run compare"}
              </button>
              {hintRepeatsDoctorPanel ? null : (
                <p className="mt-3 text-[12px] leading-5 text-[var(--fg-3)]">
                  {compareAvailability.hint}
                </p>
              )}
            </aside>
          </div>
        </section>

        <ComparePanel state={compare} workflowHrefs={workflowHrefs} />

        <FileBrowserModal
          open={browserTarget != null}
          initialPath={browserInitialPath(browserTarget, inputH5, summaryJson, keepDir, savedPrefix)}
          extensions={browserTarget === "input" ? [".h5", ".hdf5"] : browserTarget === "summary" ? [".json"] : []}
          fileTypeLabel={browserTarget === "keep" ? "directory" : "file"}
          chipLabel={browserTarget === "keep" ? "DIR" : "FILE"}
          recentScope={`pygan-${browserTarget ?? "path"}`}
          selectMode={browserTarget === "keep" ? "directory" : "file"}
          onClose={() => setBrowserTarget(null)}
          onSelect={applyBrowserPick}
        />
      </div>
    </main>
  );
}

function DoctorPanel({
  state,
  onMockDemo,
}: {
  state: DoctorState;
  onMockDemo: () => void;
}) {
  if (state.kind === "loading") {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
        Checking PyGan modules…
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section className="glass rounded-xl border-rose-400/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          PyGan status unavailable
        </div>
        <p className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</p>
        <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
          The default ASCII converter is still usable. Restart{" "}
          <code className="font-mono">openmc2donjon serve</code> from the latest
          checkout if this page was opened before the PyGan routes were added.
        </p>
      </section>
    );
  }
  const data = state.data;
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight">
              Doctor result
            </h2>
            <span
              className={
                "rounded border border-current/25 px-2 py-1 text-[10px] uppercase tracking-[0.14em] " +
                (data.available ? "text-emerald-300" : "text-amber-300")
              }
            >
              {data.available ? "available" : "unavailable"}
            </span>
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {data.role}
          </p>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            {data.available
              ? "PyGan is importable from the running backend."
              : `Missing: ${pyganMissingModulesLabel(data)}.`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.mock_mode ? (
            <button type="button" onClick={onMockDemo} className="btn btn-primary">
              Fill mock compare
            </button>
          ) : null}
          <CopyCliButton value="openmc2donjon pygan-doctor" label="Doctor CLI" />
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {data.modules.map((module) => (
          <div
            key={module.name}
            className={
              "min-w-0 rounded-lg border p-3 " +
              (module.available
                ? "border-emerald-300/20 bg-emerald-300/[0.05]"
                : "border-amber-300/20 bg-amber-300/[0.05]")
            }
          >
            <div className="flex items-center justify-between gap-3">
              <div className="font-mono text-sm">{module.name}</div>
              <span className="rounded border border-current/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em]">
                {module.available ? "found" : "missing"}
              </span>
            </div>
            <div className="mt-2 truncate text-[12px] text-[var(--fg-2)]">
              {module.available ? module.module_file ?? "importable" : module.error ?? "not importable"}
            </div>
          </div>
        ))}
      </div>
      {!data.available ? (
        <p className="mt-4 rounded-lg border border-amber-300/20 bg-amber-300/[0.05] p-3 text-[12px] leading-5 text-amber-100">
          {data.install_hint}
        </p>
      ) : null}
    </section>
  );
}

function ComparePanel({
  state,
  workflowHrefs,
}: {
  state: CompareState;
  workflowHrefs: ReturnType<typeof pyganWorkflowHrefs>;
}) {
  if (state.kind === "idle") return null;
  if (state.kind === "loading") {
    return (
      <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
        Running writer comparison…
      </section>
    );
  }
  if (state.kind === "error") {
    return (
      <section className="glass rounded-xl border-rose-400/20 p-5">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Compare failed"}
        </div>
        <p className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</p>
      </section>
    );
  }
  const data = state.data;
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className={data.ok ? "text-sm font-semibold text-emerald-300" : "text-sm font-semibold text-rose-300"}>
            {data.ok ? "WRITER SEMANTICS PASS" : "WRITER SEMANTICS FAIL"}
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            Semantic writer comparison
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Compared built-in ASCII output against PyGan output as LCM semantic
            trees. A pass means block names, payload types, and numeric values match
            within tolerance.
          </p>
        </div>
        <CopyCliButton value={data.cli_command_text} label="Copy CLI" />
      </div>

      <EvidenceLadder stages={writerComparisonEvidenceLadder(data)} />

      <dl className="mt-4 grid gap-3 text-sm md:grid-cols-3">
        <Meta label="Input" value={data.input_h5} mono />
        <Meta label="Format" value={data.format} />
        <Meta label="Mode" value={data.mock_mode ? "mock fixture" : "live PyGan"} />
        <Meta label="Payloads" value={`${data.compared_payloads}`} />
        <Meta label="Real payloads" value={`${data.compared_real_payloads}`} />
        <Meta label="Issues" value={`${data.issue_count}`} />
        <Meta label="Max abs diff" value={formatSci(data.max_abs_diff)} />
        <Meta label="Max rel diff" value={formatSci(data.max_rel_diff)} />
        <Meta
          label="Tolerance"
          value={`rtol=${formatSci(data.rtol)} atol=${formatSci(data.atol)}`}
        />
      </dl>

      {data.summary_json || data.keep_dir ? (
        <div className="mt-4 grid gap-2 text-[12px] md:grid-cols-2">
          {data.summary_json ? <PathPill label="summary JSON" value={data.summary_json} /> : null}
          {data.keep_dir ? <PathPill label="generated files" value={data.keep_dir} /> : null}
        </div>
      ) : null}

      {data.issues.length > 0 ? (
        <div className="mt-4 rounded-lg border border-rose-300/20 bg-rose-300/[0.05] p-3">
          <h3 className="text-sm font-semibold text-rose-200">Differences</h3>
          <ul className="mt-2 space-y-2 text-[12px] text-[var(--fg-1)]">
            {data.issues.slice(0, 20).map((issue, index) => (
              <li key={`${issue.path}-${index}`}>
                <code className="font-mono text-rose-100">{issue.path}</code>:{" "}
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-4 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.05] p-3 text-sm text-emerald-100">
          No semantic differences were reported.
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2 border-t border-[var(--edge)] pt-4">
        {workflowHrefs.project ? (
          <Link href={workflowHrefs.project} className="btn btn-primary">
            Return to Project
          </Link>
        ) : null}
        <Link href={workflowHrefs.converter} className="btn btn-secondary">
          Reopen same Converter settings
        </Link>
        <Link href={workflowHrefs.bundle} className="btn btn-secondary">
          Bundle output + receipt
        </Link>
        {workflowHrefs.donjon ? (
          <Link href={workflowHrefs.donjon} className="btn btn-secondary">
            Open output in DONJON
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[12px] font-medium text-[var(--fg-2)]">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  error,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  error?: string | null;
}) {
  return (
    <Field label={label}>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="input"
        aria-invalid={error ? true : undefined}
      />
      {error ? (
        <div className="mt-1 text-[11px] text-rose-300">{error}</div>
      ) : null}
    </Field>
  );
}

function PathField({
  label,
  value,
  placeholder,
  onChange,
  onBrowse,
  directory = false,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onBrowse: () => void;
  directory?: boolean;
}) {
  return (
    <Field label={label}>
      <div className="flex gap-2">
        <input
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          className="input min-w-0 flex-1"
        />
        <button type="button" onClick={onBrowse} className="btn btn-secondary shrink-0">
          Browse
        </button>
      </div>
      <div className="mt-1 text-[11px] text-[var(--fg-3)]">
        {directory ? "Directory path." : "File path."}
      </div>
    </Field>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--edge)] bg-black/10 px-3 py-2">
      <dt className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </dt>
      <dd className={"mt-1 truncate text-[12px] text-[var(--fg-1)] " + (mono ? "font-mono" : "")}>
        {value}
      </dd>
    </div>
  );
}

function PathPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-[var(--edge)] bg-black/15 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-[12px] text-[var(--fg-1)]">
        {value}
      </div>
    </div>
  );
}

function formatSci(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  return value.toExponential(3);
}
