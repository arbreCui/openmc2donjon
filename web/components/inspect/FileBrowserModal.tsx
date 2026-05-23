"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { ApiError, FileEntry, FileListing, api } from "@/lib/api";
import { pathCrumbs } from "@/lib/fileBrowserPath";
import { RecentHandoff, useRecentHandoffs } from "@/lib/recentHandoffs";

// CSS selector for elements that should be reachable via the tab trap.
const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

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
 * Directory picker for the Inspect page.
 *
 * Scope:
 * - Lists one directory at a time via ``/api/files``.
 * - Click a directory to navigate into it; click an HDF5 file to
 *   select it and close.
 * - Hides non-HDF5 files (with a count footer so the user knows the
 *   listing isn't lying about emptiness).
 * - ESC and backdrop click cancel without selecting.
 *
 * Focus management:
 * - On open, captures the previously-focused element (typically the
 *   Browse button on the Inspect form) and focuses the dialog itself.
 * - ``Tab`` / ``Shift+Tab`` cycle through focusable descendants and
 *   bounce back when focus has somehow ended up outside the dialog
 *   (browser GC of a freshly-removed entry button, for example).
 * - On cancel (ESC / backdrop / Cancel button), focus restores to the
 *   captured element. On select, focus restoration is skipped so the
 *   parent can move focus to a more useful target (Inspect button).
 *
 * Not yet shipped (real candidates for follow-up): arrow-key row
 * navigation, pin / clear for the recent list.
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
  // Per-browser list of recently-picked handoff files. We record on
  // every successful pick (not on inspect-success in the parent)
  // because the modal is self-contained that way - the trade-off is
  // that a recent entry might be a file that fails to open, which
  // shows up as the usual error card on the next inspect anyway.
  const { recent, recordPick } = useRecentHandoffs();
  // Editable path bar draft. The committed location is ``currentPath``
  // (drives the fetch); ``pathDraft`` is the user-controlled string in
  // the input. We sync the draft back to ``currentPath`` any time it
  // changes externally (crumb click, ↑ parent, dir entry click) so the
  // input always reflects where the user actually is - typing that
  // hadn't been submitted yet is intentionally discarded, since the
  // user took a competing navigation action.
  const [pathDraft, setPathDraft] = useState(initialPath);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  // Tracks whether the current open instance is closing because the
  // user selected a file (vs. cancelled). The focus-restore effect
  // skips the previousFocus restore when this is true so the parent
  // can land focus on a more useful "next action" target instead of
  // the Browse button.
  const closedViaSelectRef = useRef(false);

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

  // Focus management. On open: remember the element that was focused
  // (typically the "Browse…" button) and move focus into the dialog so
  // keyboard navigation lands inside the modal rather than continuing
  // through the page behind it. On close: restore focus to the
  // remembered element so the user picks back up where they were.
  useEffect(() => {
    if (!open) return;
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    closedViaSelectRef.current = false;
    // The dialog container itself is focusable (``tabIndex={-1}``) so
    // a programmatic ``focus()`` lands here without inserting an entry
    // in the tab order; the user's first Tab then moves to the first
    // real focusable child (Cancel, ↑ parent, then entries).
    dialogRef.current?.focus();
    return () => {
      if (closedViaSelectRef.current) return;
      previousFocusRef.current?.focus?.();
    };
  }, [open]);

  // Tab trap. Without this, Tab from the last focusable element in
  // the dialog escapes to the page behind the backdrop, which both
  // breaks keyboard browsing and contradicts the visual "this is a
  // modal" claim.
  useEffect(() => {
    if (!open) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute("aria-hidden"));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;
      // Pull focus back into the dialog when it has somehow drifted
      // outside (e.g. the entry button that had focus was removed
      // mid-loading and the browser fell back to ``body``). Without
      // this, the next Tab would walk into the page behind the modal.
      const activeInside =
        active != null && (active === dialog || dialog.contains(active));
      if (!activeInside) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  const goUp = useCallback(() => {
    if (state.kind !== "ok") return;
    if (state.data.parent != null) setCurrentPath(state.data.parent);
  }, [state]);

  // Wrap the parent's ``onSelect`` so the focus-restore effect cleanup
  // can tell "user cancelled" from "user picked a file" and leave the
  // parent free to land focus somewhere more useful (the Inspect
  // button) instead of bouncing back to Browse.
  const handleSelect = useCallback(
    (picked: string) => {
      recordPick(picked);
      closedViaSelectRef.current = true;
      onSelect(picked);
    },
    [onSelect, recordPick],
  );

  // Sync the editable draft whenever the committed path moves under
  // it (crumb click, ↑ parent, dir-entry click, modal re-anchor).
  useEffect(() => {
    setPathDraft(currentPath);
  }, [currentPath]);

  const submitPathDraft = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = pathDraft.trim();
      // No-op on empty input or on a draft that matches what's already
      // committed - sparing the backend a pointless refetch and not
      // touching state that would just useEffect-sync back to the same
      // value.
      if (!trimmed || trimmed === currentPath) return;
      setCurrentPath(trimmed);
    },
    [pathDraft, currentPath],
  );

  const draftCommittable =
    pathDraft.trim() !== "" && pathDraft.trim() !== currentPath;

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
        ref={dialogRef}
        // ``tabIndex={-1}`` lets us focus the dialog programmatically
        // on open without inserting it into the natural tab order;
        // user keystrokes still cycle through real controls.
        tabIndex={-1}
        className="glass rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col outline-none"
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

        <div className="px-4 py-2 border-b border-[var(--edge)] flex items-baseline gap-2 flex-wrap">
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
          <PathBreadcrumb
            path={state.kind === "ok" ? state.data.path : state.path}
            pending={state.kind !== "ok"}
            onPick={setCurrentPath}
          />
        </div>

        {/* Editable path bar. Companion to the breadcrumb above:
            breadcrumb is for clicking up the existing hierarchy, this
            row is for pasting / typing a specific directory (deep jump,
            sibling that breadcrumb can't get to). Backend is the source
            of truth for what's valid - garbage input just produces the
            existing 4xx error card. */}
        <form
          onSubmit={submitPathDraft}
          className="px-4 py-2 border-b border-[var(--edge)] flex items-baseline gap-2"
        >
          <label
            htmlFor="file-browser-path-input"
            className="text-[11px] uppercase tracking-wider text-[var(--fg-3)] shrink-0"
          >
            Path
          </label>
          <input
            id="file-browser-path-input"
            type="text"
            value={pathDraft}
            onChange={(event) => setPathDraft(event.target.value)}
            spellCheck={false}
            autoComplete="off"
            aria-label="Type a directory path"
            className="flex-1 min-w-0 px-2 py-1 rounded border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-[12px] focus:outline-none focus:border-[var(--accent)]"
          />
          <button
            type="submit"
            disabled={!draftCommittable}
            className="btn btn-secondary text-[12px] disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Navigate to typed path"
          >
            Go
          </button>
        </form>

        <div className="flex-1 overflow-y-auto px-1 py-1">
          {recent.length > 0 ? (
            <RecentList recent={recent} onPick={handleSelect} />
          ) : null}
          <BrowserBody state={state} onPickDir={setCurrentPath} onPickFile={handleSelect} />
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

function RecentList({
  recent,
  onPick,
}: {
  recent: readonly RecentHandoff[];
  onPick: (path: string) => void;
}) {
  return (
    // Lives in the same scroll container as the directory listing so
    // the user can pop back to a familiar file even when the current
    // directory is unrelated. ``border-b`` separates from the listing
    // below; the "Recent" label keeps the two sections distinguishable.
    <section
      aria-label="Recently picked files"
      className="px-3 pt-1 pb-2 border-b border-[var(--edge)] mb-1"
    >
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)] px-0 mb-1">
        Recent
      </div>
      <ul className="text-sm">
        {recent.map((entry) => (
          <li key={entry.path}>
            <button
              type="button"
              onClick={() => onPick(entry.path)}
              title={entry.path}
              className="w-full px-2 py-1 flex items-baseline gap-3 text-left rounded hover:bg-white/[0.04]"
            >
              <span className="inline-flex items-center justify-center min-w-[28px] h-5 px-1 rounded border border-[var(--edge)] bg-white/[0.03] text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-2)] tab-num">
                H5
              </span>
              <span className="font-mono flex-1 min-w-0 truncate text-[var(--accent-2)]">
                {entry.path}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PathBreadcrumb({
  path,
  pending,
  onPick,
}: {
  path: string;
  pending: boolean;
  onPick: (path: string) => void;
}) {
  const crumbs = pathCrumbs(path);
  return (
    // ``aria-live="polite"`` lives on the nav so screen readers
    // announce the new location when navigation lands. ``aria-current``
    // on the final crumb tells them which one is "here now".
    <nav
      aria-label="Path"
      aria-live="polite"
      className={
        "flex flex-wrap items-baseline gap-x-0.5 gap-y-0.5 font-mono text-[12px] min-w-0 " +
        (pending ? "text-[var(--fg-3)]" : "text-[var(--fg-2)]")
      }
    >
      {crumbs.map((crumb, index) => {
        const isLast = index === crumbs.length - 1;
        return (
          <span
            key={crumb.path}
            className="inline-flex items-baseline gap-0.5"
          >
            {isLast ? (
              // Non-interactive ``<span>`` rather than a disabled
              // button: tab order stays clean and screen readers don't
              // announce a useless "button, disabled" for the current
              // location.
              <span
                aria-current="location"
                className="px-1 text-[var(--fg-0)] font-semibold break-all"
              >
                {crumb.label}
              </span>
            ) : (
              // Crumbs are disabled while a fetch is in flight or has
              // errored, so a user looking at a stale path can't fire
              // a second navigation on top of it. The effect's
              // cancellation flag would tolerate overlap, but a
              // visibly-static breadcrumb is the honest signal.
              <button
                type="button"
                onClick={() => onPick(crumb.path)}
                disabled={pending}
                className="px-1 rounded text-[var(--accent-2)] hover:bg-white/[0.05] break-all disabled:text-[var(--fg-3)] disabled:hover:bg-transparent disabled:cursor-not-allowed"
                title={crumb.path}
              >
                {crumb.label}
              </button>
            )}
            {!isLast ? (
              <span aria-hidden className="text-[var(--fg-3)]">
                /
              </span>
            ) : null}
          </span>
        );
      })}
    </nav>
  );
}

function joinPath(parent: string, name: string): string {
  if (parent.endsWith("/")) return `${parent}${name}`;
  return `${parent}/${name}`;
}

function formatSize(bytes: number): string {
  const KB = 1024;
  const MB = KB * 1024;
  const GB = MB * 1024;
  if (bytes < KB) return `${bytes} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  if (bytes < GB) return `${(bytes / MB).toFixed(1)} MB`;
  return `${(bytes / GB).toFixed(1)} GB`;
}
