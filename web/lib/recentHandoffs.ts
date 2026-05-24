/**
 * Recent-handoffs storage for the file browser modal.
 *
 * Tracks the last few HDF5 files the user picked through the browser
 * so we can offer a one-click shortcut on next open. Pure splitting /
 * merging / parsing helpers live here so they can be unit-tested
 * without React; the hook at the bottom is the React glue.
 *
 * Storage shape (under ``localStorage`` key
 * ``openmc2donjon-web:recent-handoffs:v1``):
 *
 *   { "version": 1, "entries": [{ "path": "...", "selectedAt": 0 }] }
 *
 * Anything else (older shape, malformed JSON, missing fields) parses
 * to an empty list - there's no migration logic, since the value is
 * a usage hint rather than data the user typed.
 */

import { useCallback, useEffect, useState } from "react";

export interface RecentHandoff {
  /** Absolute path of the picked HDF5 file. */
  path: string;
  /** Milliseconds since epoch when the pick happened. */
  selectedAt: number;
}

export const RECENT_CAPACITY = 8;
const STORAGE_KEY_PREFIX = "openmc2donjon-web:recent-handoffs:v1";
const STORAGE_VERSION = 1;

/**
 * Build the localStorage key for a given browser ``scope``. Each
 * file-type-specific browser gets its own slot so HDF5 picks don't
 * pollute the JSON browser's recent list (and vice versa).
 */
export function recentStorageKey(scope: string): string {
  return `${STORAGE_KEY_PREFIX}:${scope}`;
}

/**
 * Prepend a freshly-picked path to the recent list, deduplicating
 * any prior entry for the same path so the user sees a single
 * up-to-date row and pruning to {@link RECENT_CAPACITY}.
 */
export function mergeRecentPick(
  list: readonly RecentHandoff[],
  path: string,
  now: number,
): RecentHandoff[] {
  const filtered = list.filter((entry) => entry.path !== path);
  return [{ path, selectedAt: now }, ...filtered].slice(0, RECENT_CAPACITY);
}

/**
 * Decode a stored payload into a recent list. Returns ``[]`` for any
 * shape we don't recognise (older schema, malformed JSON, individual
 * entries missing required fields) - this is a usage hint, not user
 * data, so a clean reset beats a half-broken migration.
 */
export function parseStoredRecent(raw: string | null): RecentHandoff[] {
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    (parsed as { version?: unknown }).version !== STORAGE_VERSION ||
    !Array.isArray((parsed as { entries?: unknown }).entries)
  ) {
    return [];
  }
  const entries = (parsed as { entries: unknown[] }).entries;
  const cleaned: RecentHandoff[] = [];
  for (const raw of entries) {
    if (typeof raw !== "object" || raw === null) continue;
    const candidate = raw as Partial<RecentHandoff>;
    if (
      typeof candidate.path === "string" &&
      typeof candidate.selectedAt === "number"
    ) {
      cleaned.push({
        path: candidate.path,
        selectedAt: candidate.selectedAt,
      });
    }
  }
  return cleaned.slice(0, RECENT_CAPACITY);
}

export function serializeRecent(list: readonly RecentHandoff[]): string {
  return JSON.stringify({ version: STORAGE_VERSION, entries: list });
}

/**
 * React hook around the helpers above. SSR-safe: the first render
 * returns an empty list (so server and client markup agree) and the
 * stored value hydrates on mount.
 */
export function useRecentHandoffs(scope: string): {
  recent: RecentHandoff[];
  recordPick: (path: string) => void;
  hydrated: boolean;
} {
  const [recent, setRecent] = useState<RecentHandoff[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setRecent(
      parseStoredRecent(
        window.localStorage.getItem(recentStorageKey(scope)),
      ),
    );
    setHydrated(true);
  }, [scope]);

  const recordPick = useCallback(
    (path: string) => {
      setRecent((current) => {
        const updated = mergeRecentPick(current, path, Date.now());
        if (typeof window !== "undefined") {
          try {
            window.localStorage.setItem(
              recentStorageKey(scope),
              serializeRecent(updated),
            );
          } catch {
            // localStorage write can fail in private browsing or under
            // quota - the UI keeps the in-memory list so the current
            // session still benefits.
          }
        }
        return updated;
      });
    },
    [scope],
  );

  return { recent, recordPick, hydrated };
}
