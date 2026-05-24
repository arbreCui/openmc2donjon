"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import {
  ApiError,
  CommandCatalog,
  CommandCatalogEntry,
  api,
} from "@/lib/api";
import {
  BuilderField,
  BuilderValues,
  buildCommandCli,
  commandBuilderSpec,
  defaultBuilderValues,
} from "@/lib/commandBuilder";
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
    spec ? defaultBuilderValues(spec) : {},
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
    setValues(spec ? defaultBuilderValues(spec) : {});
    setBrowserField(null);
  }, [spec]);

  const command = useMemo(
    () =>
      catalogState.kind === "ok"
        ? catalogState.data.commands.find((item) => item.id === commandId) ?? null
        : null,
    [catalogState, commandId],
  );

  const cli = spec ? buildCommandCli(spec, values) : command?.cli ?? "";
  const canUseSavedPrefix =
    settingsHydrated &&
    savedPrefix !== "" &&
    spec?.fields.some(
      (field) =>
        field.kind === "path" &&
        field.browse !== "directory" &&
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
        field.browse !== "directory" &&
        !String(values[field.name] ?? "").startsWith(savedPrefix),
    );
    if (!firstPath) return;
    patch(firstPath.name, savedPrefix);
  }

  function applyBrowserPick(path: string) {
    if (browserField) patch(browserField.name, path);
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
            {spec?.summary ??
              "This command does not have a structured web builder yet. Use the catalog CLI below as the source of truth."}
          </p>
        </header>

        {catalogState.kind === "error" ? (
          <section className="mb-5 rounded-lg border border-amber-300/20 bg-amber-300/[0.06] p-4 text-sm text-amber-100">
            Command catalog failed: {catalogState.message}. The local builder can still
            assemble its CLI preview.
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
                <CommandGuidance command={command} notes={spec.notes} />
              </aside>
            </div>
          </section>
        ) : (
          <FallbackCommand command={command} commandId={commandId} />
        )}

        <FileBrowserModal
          open={browserField != null}
          initialPath={browserInitialPath(browserField, values, savedPrefix)}
          extensions={browserField?.extensions ?? []}
          fileTypeLabel={browserField?.browse === "directory" ? "directory" : "input file"}
          chipLabel={browserField?.browse === "directory" ? "DIR" : "FILE"}
          recentScope={`builder-${spec?.id ?? "unknown"}-${browserField?.name ?? "path"}`}
          selectMode={browserField?.browse === "directory" ? "directory" : "file"}
          onClose={() => setBrowserField(null)}
          onSelect={applyBrowserPick}
        />
      </div>
    </main>
  );
}

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
            Browse
          </button>
        ) : null}
      </span>
    </label>
  );
}

function CommandGuidance({
  command,
  notes,
}: {
  command: CommandCatalogEntry | null;
  notes: readonly string[];
}) {
  return (
    <div className="mt-3 space-y-2 text-[12px] leading-relaxed text-[var(--fg-2)]">
      {command ? (
        <div className="rounded-md border border-[var(--edge)] bg-white/[0.02] px-3 py-2">
          <div className="text-[var(--fg-3)]">Use when</div>
          <div>{command.use_when}</div>
        </div>
      ) : null}
      <div className="rounded-md border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-amber-100">
        {notes.map((note) => (
          <div key={note}>{note}</div>
        ))}
      </div>
    </div>
  );
}

function FallbackCommand({
  command,
  commandId,
}: {
  command: CommandCatalogEntry | null;
  commandId: string;
}) {
  const cli = command?.cli ?? `openmc2donjon ${commandId}`;
  return (
    <section className="glass rounded-xl p-5">
      <h2 className="text-lg font-semibold tracking-tight">CLI fallback</h2>
      <p className="mt-2 text-sm text-[var(--fg-2)]">
        This command is visible in the catalog, but no structured builder exists yet.
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--edge)] bg-black/15 p-4">
        <pre className="overflow-x-auto text-[12px] text-[var(--fg-1)]">{cli}</pre>
        <CopyCliButton value={cli} compact />
      </div>
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
  if (value !== "") return value;
  return savedPrefix || "~";
}
