"use client";

/**
 * Browser-local user preferences for the openmc2donjon web UI.
 *
 * M1-S4 ships exactly one preference: the path that gets pre-filled as
 * a placeholder on the Inspect page so users who always work out of
 * ``/shared/.../runs/`` don't have to re-type the prefix every session.
 *
 * Settings live in ``localStorage`` only - we explicitly chose against
 * round-tripping them through the backend or writing a dotfile under
 * ``~/.config``. The web UI is single-user / localhost; if someone
 * needs cross-machine persistence they can ``git add`` a workspace
 * config later. The key is versioned so a future shape change can
 * introduce a fresh key and the migration becomes "first read of the
 * new key falls back to the defaults".
 */

import { useCallback, useEffect, useState } from "react";

export interface Settings {
  /** Pre-fill text for the Inspect path input. Empty string = no prefill. */
  default_inspect_path: string;
}

export const DEFAULT_SETTINGS: Settings = {
  default_inspect_path: "",
};

const STORAGE_KEY = "openmc2donjon-web:settings:v1";

function readSettings(): Settings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<Settings>;
    return {
      default_inspect_path:
        typeof parsed.default_inspect_path === "string"
          ? parsed.default_inspect_path
          : DEFAULT_SETTINGS.default_inspect_path,
    };
  } catch {
    // Corrupt JSON, quota error, disabled storage: fall back to
    // defaults instead of bricking the page.
    return DEFAULT_SETTINGS;
  }
}

function writeSettings(value: Settings): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* localStorage disabled / quota exceeded; nothing useful to do */
  }
}

export type UseSettings = readonly [
  settings: Settings,
  update: (partial: Partial<Settings>) => void,
  reset: () => void,
  hydrated: boolean,
];

/**
 * Read and persist user preferences with SSR-safe hydration.
 *
 * The hook returns ``DEFAULT_SETTINGS`` on the first render (server
 * and client agree) and then re-renders with the real localStorage
 * value after mount. ``hydrated`` lets callers distinguish "we just
 * haven't loaded yet" from "the user really has no preference saved",
 * which matters for the Inspect page placeholder.
 */
export function useSettings(): UseSettings {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setSettings(readSettings());
    setHydrated(true);
  }, []);

  const update = useCallback((partial: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...partial };
      writeSettings(next);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
    writeSettings(DEFAULT_SETTINGS);
  }, []);

  return [settings, update, reset, hydrated] as const;
}
