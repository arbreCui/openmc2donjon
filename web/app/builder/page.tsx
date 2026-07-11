"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import OpenmcSphWorkflowPanel from "@/components/OpenmcSphWorkflowPanel";
import {
  ApiError,
  CommandCatalog,
  CommandCatalogEntry,
  api,
} from "@/lib/api";
import {
  BuilderField,
  BuilderValues,
  builderCliIssues,
  builderValuesFromQuery,
  buildCommandCli,
  commandBuilderSpec,
  commandBuilderStage,
} from "@/lib/commandBuilder";
import {
  builderCatalogFailureHint,
  builderFallbackCopy,
  commandContextRows,
} from "@/lib/builderCopy";
import { bundlePrefillStatus } from "@/lib/builderPrefill";
import { containingDirectory, outputPathInDirectory } from "@/lib/outputBrowse";
import { isOpenmcSphWorkflowCommand } from "@/lib/openmcSphWorkflow";
import { useSettings } from "@/lib/settings";

type CatalogState =
  | { kind: "loading" }
  | { kind: "ok"; data: CommandCatalog }
  | { kind: "error"; message: string };

export default function CommandBuilderPage() {
  return (
    <Suspense fallback={<BuilderLoading />}>
      <CommandBuilderPageContent />
    </Suspense>
  );
}

function BuilderLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading command builder…
        </section>
      </div>
    </main>
  );
}

function CommandBuilderPageContent() {
  const searchParams = useSearchParams();
  const commandId = searchParams.get("command") ?? "diff";
  const spec = commandBuilderSpec(commandId);
  const [catalogState, setCatalogState] = useState<CatalogState>({ kind: "loading" });
  const [values, setValues] = useState<BuilderValues>(() =>
    spec ? builderValuesFromQuery(spec, searchParams) : {},
  );
  const [browserField, setBrowserField] = useState<BuilderField | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();

  const refreshCatalog = useCallback(async () => {
    setCatalogState({ kind: "loading" });
    try {
      setCatalogState({ kind: "ok", data: await api.commands() });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Unknown error";
      setCatalogState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    refreshCatalog();
  }, [refreshCatalog]);

  useEffect(() => {
    setValues(spec ? builderValuesFromQuery(spec, searchParams) : {});
    setBrowserField(null);
  }, [searchParams, spec]);

  const command = useMemo(
    () =>
      catalogState.kind === "ok"
        ? catalogState.data.commands.find((item) => item.id === commandId) ?? null
        : null,
    [catalogState, commandId],
  );

  const cli = spec ? buildCommandCli(spec, values) : command?.cli ?? "";
  const cliIssues = spec ? builderCliIssues(spec, values) : [];
  const stage = spec ? commandBuilderStage(spec.id) : null;
  // Saved-prefix shortcuts target input files only: directory and
  // output-path fields are not inspect-path material.
  const canUseSavedPrefix =
    settingsHydrated &&
    savedPrefix !== "" &&
    spec?.fields.some(
      (field) =>
        field.kind === "path" &&
        field.browse === "file" &&
        !String(values[field.name] ?? "").startsWith(savedPrefix),
    );

  function patch(name: string, value: string | boolean) {
    setValues((current) => ({ ...current, [name]: value }));
  }

  function applySavedPrefix() {
    if (!spec) return;
    const firstPath = spec.fields.find(
      (field) =>
        field.kind === "path" &&
        field.browse === "file" &&
        !String(values[field.name] ?? "").startsWith(savedPrefix),
    );
    if (!firstPath) return;
    patch(firstPath.name, savedPrefix);
  }

  function applyBrowserPick(path: string) {
    if (browserField) {
      // Output fields browse for a *directory* (the file does not exist
      // yet); the picked directory keeps the current filename, falling
      // back to the field's default filename.
      const value =
        browserField.browse === "output"
          ? outputPathInDirectory(
              path,
              String(values[browserField.name] ?? ""),
              browserField.placeholder ?? "",
            )
          : path;
      patch(browserField.name, value);
    }
    setBrowserField(null);
  }

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--fg-3)]">
            Command builder
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            <span className="grad-text">{spec?.title ?? commandId}</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {spec?.summary ?? "This command does not have a structured web builder yet."}
          </p>
        </header>

        {catalogState.kind === "error" ? (
          <section className="mb-5 rounded-lg border border-amber-300/20 bg-amber-300/[0.06] p-4 text-sm text-amber-100">
            Command catalog failed: {catalogState.message}.{" "}
            {builderCatalogFailureHint(spec != null)}
          </section>
        ) : null}

        {spec ? (
          <section className="glass rounded-xl p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="font-mono text-[11px] text-[var(--fg-3)]">
                  openmc2donjon {spec.id}
                </div>
                <h2 className="mt-1 text-lg font-semibold tracking-tight">
                  Fill inputs, copy CLI, run locally
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
                  Builders are non-mutating. The web UI does not execute this command or
                  write files; it only makes the CLI explicit and repeatable.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link href={`/commands/${spec.id}`} className="btn btn-secondary">
                  Command guide
                </Link>
                <Link href="/commands" className="btn btn-secondary">
                  All commands
                </Link>
              </div>
            </div>

            {stage ? <WorkflowHint stage={stage} /> : null}
            <CommandContextPanel command={command} />
            {isOpenmcSphWorkflowCommand(spec.id) ? (
              <OpenmcSphWorkflowPanel activeCommandId={spec.id} />
            ) : null}

            {spec.id === "bundle" ? (
              <BundlePrefillPanel status={bundlePrefillStatus(values)} />
            ) : null}

            {canUseSavedPrefix ? (
              <button
                type="button"
                onClick={applySavedPrefix}
                className="mt-4 text-[12px] text-[var(--accent-2)] hover:underline"
              >
                Use saved prefix: <code className="font-mono">{savedPrefix}</code>
              </button>
            ) : null}

            <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_380px]">
              <div className="grid gap-3 md:grid-cols-2">
                {spec.fields.map((field) => (
                  <BuilderFieldControl
                    key={field.name}
                    field={field}
                    value={values[field.name]}
                    onChange={(value) => patch(field.name, value)}
                    onBrowse={
                      field.kind === "path" && field.browse
                        ? () => setBrowserField(field)
                        : undefined
                    }
                  />
                ))}
              </div>

              <aside className="h-fit rounded-lg border border-[var(--edge)] bg-black/15 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold tracking-tight">CLI preview</h3>
                    <p className="mt-1 text-[12px] text-[var(--fg-3)]">
                      Copy this exact command into your shell.
                    </p>
                  </div>
                  <CopyCliButton value={cli} compact />
                </div>
                <pre className="mt-3 overflow-x-auto rounded-md border border-[var(--edge)] bg-black/25 px-3 py-2 text-[12px] text-[var(--fg-1)]">
                  {cli}
                </pre>
                {cliIssues.length > 0 ? (
                  <div className="mt-3 rounded-md border border-rose-400/25 bg-rose-400/[0.07] px-3 py-2 text-[12px] leading-relaxed text-rose-100">
                    {cliIssues.map((issue) => (
                      <div key={issue}>{issue}</div>
                    ))}
                  </div>
                ) : null}
                <CommandGuidance notes={spec.notes} />
              </aside>
            </div>
          </section>
        ) : (
          <FallbackCommand
            catalog={catalogState.kind}
            command={command}
            commandId={commandId}
          />
        )}

        <FileBrowserModal
          open={browserField != null}
          initialPath={browserInitialPath(browserField, values, savedPrefix)}
          extensions={browserField?.browse === "file" ? browserField.extensions ?? [] : []}
          fileTypeLabel={
            browserField?.browse === "directory"
              ? "directory"
              : browserField?.browse === "output"
                ? "output directory"
                : "input file"
          }
          chipLabel={browserField?.browse === "file" ? "FILE" : "DIR"}
          recentScope={`builder-${spec?.id ?? "unknown"}-${browserField?.name ?? "path"}`}
          selectMode={browserField?.browse === "file" ? "file" : "directory"}
          onClose={() => setBrowserField(null)}
          onSelect={applyBrowserPick}
        />
      </div>
    </main>
  );
}

function WorkflowHint({
  stage,
}: {
  stage: ReturnType<typeof commandBuilderStage>;
}) {
  return (
    <div className="mt-4 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.045] p-3">
      <div className="grid gap-3 md:grid-cols-[180px_1fr_180px] md:items-start">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-cyan-300">
            workflow step
          </div>
          <div className="mt-1 text-sm font-semibold tracking-tight">{stage.label}</div>
        </div>
        <p className="text-sm leading-relaxed text-[var(--fg-2)]">{stage.summary}</p>
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            fixed reference
          </div>
          <div className="mt-1 text-[12px] text-[var(--fg-1)]">{stage.reference}</div>
        </div>
      </div>
    </div>
  );
}

function CommandContextPanel({
  command,
}: {
  command: CommandCatalogEntry | null;
}) {
  const rows = commandContextRows(command);
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-white/[0.02] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            command in plain language
          </div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            What this builder is for
          </h3>
        </div>
        {command ? (
          <span className="rounded border border-current/20 bg-black/15 px-2 py-0.5 text-[11px] text-[var(--fg-2)]">
            {command.status_label}
          </span>
        ) : null}
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        {rows.map(([label, body]) => (
          <div key={label} className="rounded-md border border-[var(--edge)] bg-black/10 p-3">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {label}
            </div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function BundlePrefillPanel({
  status,
}: {
  status: ReturnType<typeof bundlePrefillStatus>;
}) {
  return (
    <section
      className={
        "mt-4 rounded-lg border p-3 " +
        (status.prefilled
          ? "border-emerald-300/20 bg-emerald-300/[0.05]"
          : "border-cyan-300/20 bg-cyan-300/[0.045]")
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            delivery bundle
          </div>
          <h3 className="mt-1 text-sm font-semibold tracking-tight">
            {status.title}
          </h3>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            {status.body}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {status.validateHref ? (
            <Link href={status.validateHref} className="btn btn-primary">
              Prepare validation
            </Link>
          ) : null}
          {status.donjonHref ? (
            <Link href={status.donjonHref} className="btn btn-secondary">
              Open DONJON guide
            </Link>
          ) : null}
          <Link href="/commands/direct-convert" className="btn btn-secondary">
            Direct convert notes
          </Link>
        </div>
      </div>
      {status.manifestPath ? (
        <div className="mt-3 rounded border border-current/15 bg-black/15 px-3 py-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            manifest path after bundle
          </div>
          <div className="mt-1 break-all font-mono text-[12px] text-[var(--fg-1)]">
            {status.manifestPath}
          </div>
        </div>
      ) : null}
      {status.chips.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {status.chips.map((chip) => (
            <span
              key={chip}
              className="rounded border border-current/20 bg-black/15 px-2 py-0.5 text-[11px] text-[var(--fg-1)]"
            >
              {chip}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 grid gap-2 md:grid-cols-3">
        {BUNDLE_WORKFLOW_STEPS.map((step, index) => (
          <article
            key={step.title}
            className="rounded-md border border-[var(--edge)] bg-black/15 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[11px] text-[var(--fg-3)]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="rounded border border-current/20 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                {step.badge}
              </span>
            </div>
            <h4 className="mt-2 text-[12px] font-semibold tracking-tight">
              {step.title}
            </h4>
            <p className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
              {step.body}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

const BUNDLE_WORKFLOW_STEPS = [
  {
    badge: "inputs",
    title: "Review paths",
    body:
      "Keep the OpenMC MGXS source, DONJON ASCII output, summaries, and logs together.",
  },
  {
    badge: "manifest",
    title: "Run bundle CLI",
    body:
      "The command writes the manifest-backed delivery directory on your local filesystem.",
  },
  {
    badge: "handoff",
    title: "Share or validate",
    body:
      "Send the bundle to DONJON users, or run validate-bundle before delivery.",
  },
] as const;

function BuilderFieldControl({
  field,
  value,
  onChange,
  onBrowse,
}: {
  field: BuilderField;
  value: string | boolean | undefined;
  onChange: (value: string | boolean) => void;
  onBrowse?: () => void;
}) {
  const inputId = `builder-${field.name}`;
  return (
    <label className="block rounded-lg border border-[var(--edge)] bg-white/[0.015] p-3">
      <span className="flex items-center justify-between gap-3">
        <span className="text-sm font-semibold tracking-tight">
          {field.label}
          {field.required ? <span className="text-emerald-300"> *</span> : null}
        </span>
        {field.flag ? (
          <code className="font-mono text-[10px] text-[var(--fg-3)]">{field.flag}</code>
        ) : null}
      </span>
      <span className="mt-1 block min-h-[2rem] text-[12px] leading-relaxed text-[var(--fg-3)]">
        {field.help}
      </span>
      <span className="mt-3 flex gap-2">
        {field.kind === "toggle" ? (
          <input
            id={inputId}
            type="checkbox"
            checked={value === true}
            onChange={(event) => onChange(event.target.checked)}
            className="mt-1 h-4 w-4 accent-emerald-500"
          />
        ) : field.kind === "select" ? (
          <select
            id={inputId}
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
            className="min-w-0 flex-1 rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
          >
            {(field.options ?? []).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={inputId}
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
            placeholder={field.placeholder}
            className="min-w-0 flex-1 rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)] placeholder:text-[var(--fg-3)]"
          />
        )}
        {onBrowse ? (
          <button type="button" onClick={onBrowse} className="btn btn-secondary shrink-0">
            {field.browse === "file" ? "Browse" : "Browse dir"}
          </button>
        ) : null}
      </span>
    </label>
  );
}

function CommandGuidance({
  notes,
}: {
  notes: readonly string[];
}) {
  return (
    <div className="mt-3 space-y-2 text-[12px] leading-relaxed text-[var(--fg-2)]">
      <div className="rounded-md border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-amber-100">
        {notes.map((note) => (
          <div key={note}>{note}</div>
        ))}
      </div>
    </div>
  );
}

function FallbackCommand({
  catalog,
  command,
  commandId,
}: {
  catalog: CatalogState["kind"];
  command: CommandCatalogEntry | null;
  commandId: string;
}) {
  const copy = builderFallbackCopy(catalog, command, commandId);
  return (
    <section className="glass rounded-xl p-5">
      <h2 className="text-lg font-semibold tracking-tight">CLI fallback</h2>
      <p className="mt-2 text-sm text-[var(--fg-2)]">{copy.message}</p>
      {copy.cli != null ? (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--edge)] bg-black/15 p-4">
          <pre className="overflow-x-auto text-[12px] text-[var(--fg-1)]">{copy.cli}</pre>
          <CopyCliButton value={copy.cli} compact />
        </div>
      ) : (
        <div className="mt-4">
          <Link href="/commands" className="btn btn-secondary">
            All commands
          </Link>
        </div>
      )}
    </section>
  );
}

function browserInitialPath(
  field: BuilderField | null,
  values: BuilderValues,
  savedPrefix: string,
): string {
  if (!field) return savedPrefix || "~";
  const value = String(values[field.name] ?? "").trim();
  if (value === "") return savedPrefix || "~";
  // Output values are file paths but the picker lists directories, so
  // start in the directory containing the current value.
  return field.browse === "output" ? containingDirectory(value) : value;
}
