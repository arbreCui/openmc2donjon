import Link from "next/link";
import type { DemoShortcut } from "@/lib/demoShortcuts";

type DemoBackendState =
  | { kind: "checking" }
  | { kind: "unavailable" }
  | { kind: "ready"; mockMode: boolean };

interface Props {
  state: DemoBackendState;
  shortcuts: readonly DemoShortcut[];
}

export default function HomeDemoShortcuts({ state, shortcuts }: Props) {
  const enabled = state.kind === "ready" && state.mockMode;
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent-2)]">
            Bundled demos
          </p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">
            Try the full flow without finding files
          </h2>
        </div>
        <DemoBadge state={state} />
      </div>

      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
        In mock mode, these shortcuts open prefilled localhost examples for the
        direct converter, HDF5 inspector, and OpenMC-side SPH sidecar builder.
      </p>

      {enabled ? (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {shortcuts.map((shortcut) => (
            <Link
              key={shortcut.id}
              href={shortcut.href}
              className="rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4 transition hover:border-[var(--edge-bright)] hover:bg-white/[0.045]"
            >
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--fg-3)]">
                {shortcut.eyebrow}
              </div>
              <div className="mt-2 text-sm font-semibold text-[var(--fg-0)]">
                {shortcut.title}
              </div>
              <p className="mt-1 min-h-[3rem] text-[12px] leading-relaxed text-[var(--fg-2)]">
                {shortcut.body}
              </p>
              <div className="mt-3 text-[12px] font-medium text-[var(--accent-2)]">
                {shortcut.cta}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-lg border border-[var(--edge)] bg-white/[0.025] p-4 text-sm text-[var(--fg-2)]">
          <DemoDisabledMessage state={state} />
        </div>
      )}
    </section>
  );
}

function DemoDisabledMessage({ state }: { state: DemoBackendState }) {
  if (state.kind === "checking") {
    return <>Checking backend mode before enabling demo shortcuts.</>;
  }
  if (state.kind === "unavailable") {
    return (
      <>
        Start the backend with{" "}
        <code className="font-mono">openmc2donjon serve --mock</code> to enable
        bundled demos.
      </>
    );
  }
  return (
    <>
      Bundled demo shortcuts are hidden in live mode so real runs do not
      accidentally use <code className="font-mono">/mock</code> paths.
    </>
  );
}

function DemoBadge({ state }: { state: DemoBackendState }) {
  if (state.kind === "checking") {
    return (
      <span className="rounded-full border border-[var(--edge)] px-2.5 py-1 text-[11px] text-[var(--fg-2)]">
        checking
      </span>
    );
  }
  if (state.kind === "unavailable") {
    return (
      <span className="rounded-full border border-rose-400/20 bg-rose-400/10 px-2.5 py-1 text-[11px] text-rose-200">
        backend offline
      </span>
    );
  }
  return (
    <span
      className={
        state.mockMode
          ? "rounded-full border border-amber-300/30 bg-amber-300/10 px-2.5 py-1 text-[11px] text-amber-200"
          : "rounded-full border border-[var(--edge)] px-2.5 py-1 text-[11px] text-[var(--fg-2)]"
      }
    >
      {state.mockMode ? "mock mode" : "live mode"}
    </span>
  );
}
