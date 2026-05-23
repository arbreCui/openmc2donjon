"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, FileEntry, FileListing, api } from "@/lib/api";

const HDF5_EXTENSIONS = /\.(h5|hdf5)$/i;

export interface FileBrowserModalProps {
  open: boolean;
  /** Initial directory to load when the modal opens. ``"~"`` is the
   * common default and the backend will resolve it to the server
   * home (or to the mock-home tree in mock mode). */
  initialPath: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

type State =
  | { kind: "loading"; path: string }
  | { kind: "ok"; data: FileListing }
  | { kind: "error"; path: string; message: string; status?: number };

/**
 * Minimal directory picker for the Inspect page.
 *
 * Scope (M3 first iteration):
 * - Lists one directory at a time via ``/api/files``.
 * - Click a directory to navigate into it; click an HDF5 file to
 *   select it and close.
 * - Hides non-HDF5 files (with a count footer so the user knows the
 *   listing isn't lying about emptiness).
 * - ESC and backdrop click cancel without selecting.
 * - No focus trap, no breadcrumb, no recently-used list - those are
 *   M3 follow-ups if real usage demands them.
 */
export default function FileBrowserModal({
  open,
  initialPath,
  onSelect,
  onClose,
}: FileBrowserModalProps) {
  const [state, setState] = useState<State>({
    kind: "loading",
    path: initialPath,
  });
  const [currentPath, setCurrentPath] = useState(initialPath);

  // Re-anchor to ``initialPath`` whenever the modal opens fresh.
  useEffect(() => {
    if (!open) return;
    setCurrentPath(initialPath);
  }, [open, initialPath]);

  // Fetch the listing whenever the current path changes (and the
  // modal is open).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setState({ kind: "loading", path: currentPath });
    api
      .listFiles(currentPath)
      .then((data) => {
        if (cancelled) return;
        setState({ kind: "ok", data });
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err instanceof ApiError ? err.status : undefined;
        const message =
          err instanceof Error ? err.message : "Unknown error.";
        setState({ kind: "error", path: currentPath, message, status });
      });
    return () => {
      cancelled = true;
    };
  }, [open, currentPath]);

  // ESC closes.
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const goUp = useCallback(() => {
    if (state.kind !== "ok") return;
    if (state.data.parent != null) setCurrentPath(state.data.parent);
  }, [state]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8 bg-black/60 backdrop-blur-sm"
      onClick={(event) => {
        // Backdrop click cancels; clicks inside the dialog body
        // bubble up but we ignore them via the inner stopPropagation.
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Browse for HDF5 file"
    >
      <div
        className="glass rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-baseline justify-between gap-3 px-4 py-3 border-b border-[var(--edge)]">
          <h3 className="text-sm font-semibold tracking-tight">
            <span className="grad-text">Browse for HDF5 file</span>
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="btn btn-secondary text-[12px]"
            aria-label="Close browser"
          >
            Cancel
          </button>
        </div>

        <div className="px-4 py-2 border-b border-[var(--edge)] flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={goUp}
            disabled={
              state.kind !== "ok" || state.data.parent == null
            }
            className="btn btn-secondary text-[12px]"
            aria-label="Go to parent directory"
          >
            ↑ parent
          </button>
          <span
            className="font-mono text-[12px] text-[var(--fg-2)] break-all"
            aria-live="polite"
          >
            {state.kind === "ok"
              ? state.data.path
              : state.path}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-1 py-1">
          <BrowserBody state={state} onPickDir={setCurrentPath} onPickFile={onSelect} />
        </div>
      </div>
    </div>
  );
}

function BrowserBody({
  state,
  onPickDir,
  onPickFile,
}: {
  state: State;
  onPickDir: (path: string) => void;
  onPickFile: (path: string) => void;
}) {
  if (state.kind === "loading") {
    return (
      <p className="p-4 text-sm text-[var(--fg-2)] tab-num">Listing…</p>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="m-3 glass rounded-md p-4 border-rose-500/20">
        <div className="text-sm font-semibold text-rose-300">
          {state.status ? `HTTP ${state.status}` : "Listing failed"}
        </div>
        <div className="mt-1 text-sm text-[var(--fg-1)]">
          {state.message}
        </div>
      </div>
    );
  }
  const allEntries = state.data.entries;
  const visible = allEntries.filter(
    (e) => e.kind === "dir" || HDF5_EXTENSIONS.test(e.name),
  );
  const hiddenCount = allEntries.length - visible.length;
  // Dirs first (already alphabetical from backend), then files.
  const dirs = visible.filter((e) => e.kind === "dir");
  const files = visible.filter((e) => e.kind === "file");

  if (visible.length === 0) {
    return (
      <div className="p-4 space-y-1 text-sm text-[var(--fg-3)]">
        <div>No HDF5 files or subdirectories here.</div>
        {hiddenCount > 0 ? (
          <div className="text-[12px]">
            ({hiddenCount} non-HDF5 file
            {hiddenCount === 1 ? "" : "s"} hidden.)
          </div>
        ) : null}
      </div>
    );
  }

  return (
    // No ``role="listbox"`` here: the children are full action
    // ``<button>`` elements (each one navigates or selects), not the
    // listbox-option pattern. Leaving it as a plain unordered list
    // keeps screen-reader semantics straight.
    <ul className="text-sm">
      {dirs.map((entry) => (
        <EntryRow
          key={`dir:${entry.name}`}
          entry={entry}
          onClick={() => onPickDir(joinPath(state.data.path, entry.name))}
        />
      ))}
      {files.map((entry) => (
        <EntryRow
          key={`file:${entry.name}`}
          entry={entry}
          onClick={() => onPickFile(joinPath(state.data.path, entry.name))}
        />
      ))}
      {hiddenCount > 0 ? (
        <li className="px-3 py-2 text-[12px] text-[var(--fg-3)]">
          {hiddenCount} non-HDF5 file{hiddenCount === 1 ? "" : "s"} hidden.
        </li>
      ) : null}
    </ul>
  );
}

function EntryRow({
  entry,
  onClick,
}: {
  entry: FileEntry;
  onClick: () => void;
}) {
  const isDir = entry.kind === "dir";
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="w-full px-3 py-1.5 flex items-baseline gap-3 text-left rounded hover:bg-white/[0.04]"
      >
        <span className="inline-flex items-center justify-center min-w-[28px] h-5 px-1 rounded border border-[var(--edge)] bg-white/[0.03] text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-2)] tab-num">
          {isDir ? "DIR" : "H5"}
        </span>
        <span
          className={
            "font-mono flex-1 min-w-0 truncate " +
            (isDir ? "text-[var(--fg-0)]" : "text-[var(--accent-2)]")
          }
        >
          {entry.name}
          {isDir ? "/" : ""}
        </span>
        {entry.size != null ? (
          <span className="text-[12px] tab-num text-[var(--fg-3)]">
            {formatSize(entry.size)}
          </span>
        ) : null}
      </button>
    </li>
  );
}

function joinPath(parent: string, name: string): string {
  if (parent.endsWith("/")) return `${parent}${name}`;
  return `${parent}/${name}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
