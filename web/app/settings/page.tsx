"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSettings } from "@/lib/settings";

export default function SettingsPage() {
  const [settings, update, , hydrated] = useSettings();
  const [draft, setDraft] = useState<string>("");
  const [savedFlash, setSavedFlash] = useState(false);

  // Initialise the draft from persisted settings once they hydrate.
  useEffect(() => {
    if (hydrated) {
      setDraft(settings.default_inspect_path);
    }
  }, [hydrated, settings.default_inspect_path]);

  // Auto-dismiss the "Saved" indicator a few seconds after a save.
  useEffect(() => {
    if (!savedFlash) return;
    const handle = window.setTimeout(() => setSavedFlash(false), 1800);
    return () => window.clearTimeout(handle);
  }, [savedFlash]);

  const onSave = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    update({ default_inspect_path: draft.trim() });
    setSavedFlash(true);
  };

  return (
    <main className="app-page">
      <div className="app-container max-w-3xl">
        <header className="mb-8">
          <p className="page-kicker">Local preferences</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            <span className="grad-text">Settings</span>
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-2)]">
            Browser-local preferences. Nothing here is sent to the
            openmc2donjon backend; values are stored only in this
            browser&apos;s
            <code className="font-mono"> localStorage</code>.
          </p>
        </header>

        <form
          className="surface space-y-4 p-5"
          onSubmit={onSave}
        >
          <div>
            <label
              htmlFor="default_inspect_path"
              className="block text-sm font-semibold"
            >
              Default path prefix
            </label>
            <p className="mt-1 text-[12px] text-[var(--fg-3)]">
              Default path prefix for path inputs and the file browser
              on the Inspect, Convert, PyGan, Equivalence, Builder, and
              OpenMC pages: it appears as the path-input{" "}
              <em>placeholder</em>, is filled in by their &quot;Use
              saved prefix&quot; buttons, and picks the file
              browser&apos;s starting directory. Leave blank to disable.
            </p>
            <input
              id="default_inspect_path"
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={!hydrated}
              placeholder="/shared/you/openmc-runs/"
              className="mt-3 w-full min-w-0 px-3 py-2 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] text-[var(--fg-0)] font-mono text-sm focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
              spellCheck={false}
              autoComplete="off"
            />
          </div>

          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="text-[12px] tab-num text-[var(--fg-3)]">
              {hydrated ? (
                savedFlash ? (
                  <span className="text-emerald-300">Saved.</span>
                ) : (
                  <span>
                    Current value:{" "}
                    <span className="font-mono text-[var(--fg-1)]">
                      {settings.default_inspect_path || "(none)"}
                    </span>
                  </span>
                )
              ) : (
                <span>Loading…</span>
              )}
            </div>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!hydrated}
            >
              Save settings
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
