"use client";

import {
  FormEvent,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  HandoffInspection,
  MixtureDetail,
  api,
} from "@/lib/api";
import { scatterMomentClickAction } from "@/lib/inspectScatterMoment";
import { useSettings } from "@/lib/settings";
import CrossSectionPlot from "@/components/inspect/CrossSectionPlot";
import FileBrowserModal from "@/components/inspect/FileBrowserModal";
import GroupVectorTable, {
  type GroupVectorSeries,
} from "@/components/inspect/GroupVectorTable";
import MixtureTable from "@/components/inspect/MixtureTable";
import ScatterHeatmap, {
  type Scale as ScatterScale,
} from "@/components/inspect/ScatterHeatmap";
import Summary from "@/components/inspect/Summary";
import { FormStep, WorkflowPageHeader } from "@/components/ui/Workflow";
import ProjectAcceptance from "@/components/ProjectAcceptance";
import { projectCoreHref, projectRootFromSearchParams } from "@/lib/projectWorkspace";

const FALLBACK_PLACEHOLDER = "/path/to/mgxs_library.h5";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: HandoffInspection; path: string }
  | { kind: "error"; message: string; status?: number };

type MixtureState =
  | { kind: "idle" }
  | {
      kind: "loading";
      mixture: string;
      moment: number;
      calculationState: string | null;
      /** Last successful detail, kept so the panel keeps drawing while
       * the next request is in flight (avoids the chart flashing out
       * on every moment switch). */
      previous?: MixtureDetail;
    }
  | { kind: "ok"; data: MixtureDetail }
  | {
      kind: "error";
      mixture: string;
      moment: number;
      calculationState: string | null;
      message: string;
      status?: number;
      /** As above: keep the previous good payload on screen with an
       * error banner so the user has a clear recovery path (click
       * another moment, or another mixture). */
      previous?: MixtureDetail;
    };

function carryOverPrevious(state: MixtureState): MixtureDetail | undefined {
  if (state.kind === "ok") return state.data;
  if (state.kind === "loading" || state.kind === "error") return state.previous;
  return undefined;
}

/**
 * Same as {@link carryOverPrevious} but scoped to a specific mixture:
 * only returns the previous payload if it really came from the mixture
 * the new request is targeting. This avoids flashing the old row's
 * meta / spectrum / heatmap while a brand-new mixture is loading -
 * the carryover is intentional for moment-only refetches on one
 * mixture, not for jumping between rows.
 */
function carryOverPreviousFor(
  state: MixtureState,
  mixture: string,
): MixtureDetail | undefined {
  const previous = carryOverPrevious(state);
  return previous?.mixture === mixture ? previous : undefined;
}

export default function InspectPage() {
  return (
    <Suspense fallback={<InspectLoading />}>
      <InspectPageContent />
    </Suspense>
  );
}

function InspectLoading() {
  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading inspector…
        </section>
      </div>
    </main>
  );
}

function InspectPageContent() {
  const searchParams = useSearchParams();
  const projectRoot = projectRootFromSearchParams(searchParams);
  const acceptanceMode = searchParams.get("mode") === "acceptance";
  const queryPath = searchParams.get("path") ?? "";
  const [path, setPath] = useState(queryPath);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [selectedMixture, setSelectedMixture] = useState<string | null>(null);
  const [mixtureState, setMixtureState] = useState<MixtureState>({
    kind: "idle",
  });
  // Scatter-heatmap controls are lifted here so a moment change can
  // drive an ``api.inspectMixture`` refetch and so a scale preference
  // survives mixture switches (a user who picked log10 once usually
  // wants log10 for the next mixture too).
  const [scatterMoment, setScatterMoment] = useState(0);
  const [calculationState, setCalculationState] = useState<string | null>(null);
  // Bumped to re-run the mixture fetch with otherwise-identical inputs
  // (retry after a failed moment fetch); part of the fetch effect's
  // dependency key.
  const [scatterFetchToken, setScatterFetchToken] = useState(0);
  const [scatterScale, setScatterScale] = useState<ScatterScale>("linear");
  const [browserOpen, setBrowserOpen] = useState(false);
  // After the browser modal selects a file we hand keyboard focus to
  // the Inspect submit button (Enter submits, far more useful than
  // bouncing focus back to Browse).
  const inspectButtonRef = useRef<HTMLButtonElement | null>(null);
  const [settings, , , settingsHydrated] = useSettings();
  const savedPrefix = settings.default_inspect_path.trim();
  // Show the saved default as a *placeholder* only - never pre-fill the
  // value, so users who want to type a new path don't have to clear
  // the input first. ``FALLBACK_PLACEHOLDER`` keeps the field signalling
  // its intent before the user has saved anything in Settings. An
  // explicit "Use saved prefix" button below the form copies the saved
  // value into the input when the user actually wants to save typing.
  const placeholder = savedPrefix || FALLBACK_PLACEHOLDER;
  const hasPath = path.trim().length > 0;
  const canUseSavedPrefix =
    settingsHydrated && savedPrefix !== "" && !path.startsWith(savedPrefix);

  const runInspect = useCallback(async (rawPath: string) => {
    const trimmed = rawPath.trim();
    if (!trimmed) {
      setState({ kind: "error", message: "Enter a path first." });
      return;
    }
    setPath(trimmed);
    setState({ kind: "loading" });
    setSelectedMixture(null);
    setMixtureState({ kind: "idle" });
    setScatterMoment(0);
    setCalculationState(null);
    try {
      const data = await api.inspect(trimmed);
      setState({ kind: "ok", data, path: trimmed });
    } catch (err) {
      setState(toErrorState(err));
    }
  }, []);

  const inspect = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runInspect(path);
  };

  useEffect(() => {
    if (!queryPath) return;
    void runInspect(queryPath);
  }, [queryPath, runInspect]);

  const handlePickMixture = useCallback((name: string) => {
    setSelectedMixture(name);
    // New mixture = start at P0; scale preference is intentionally
    // preserved so users don't have to re-pick log10 after every row click.
    setScatterMoment(0);
    setCalculationState(null);
  }, []);

  const retryScatterFetch = useCallback(() => {
    setScatterFetchToken((token) => token + 1);
  }, []);

  const handleScatterMomentChange = useCallback(
    (moment: number) => {
      const action = scatterMomentClickAction(
        moment,
        scatterMoment,
        mixtureState.kind === "error" && mixtureState.moment === moment,
      );
      if (action === "switch") {
        setScatterMoment(moment);
      } else if (action === "retry") {
        // Re-clicking the failed moment retries it; setting the same
        // ``scatterMoment`` value alone would bail out of the effect.
        retryScatterFetch();
      }
    },
    [mixtureState, retryScatterFetch, scatterMoment],
  );

  useEffect(() => {
    // ``scatterFetchToken`` participates in the dependency key so a
    // retry re-fires this fetch even though the request inputs are
    // unchanged.
    void scatterFetchToken;
    if (state.kind !== "ok" || selectedMixture == null) return;
    const requested = selectedMixture;
    const requestedMoment = scatterMoment;
    const requestedState = calculationState;
    setMixtureState((prev) => ({
      kind: "loading",
      mixture: requested,
      moment: requestedMoment,
      calculationState: requestedState,
      previous: carryOverPreviousFor(prev, requested),
    }));
    let cancelled = false;
    api
      .inspectMixture(
        state.path,
        requested,
        requestedMoment,
        requestedState ?? undefined,
      )
      .then((data) => {
        if (cancelled) return;
        setMixtureState({ kind: "ok", data });
      })
      .catch((err) => {
        if (cancelled) return;
        const base = toErrorState(err);
        if (base.kind === "error") {
          setMixtureState((prev) => ({
            kind: "error",
            mixture: requested,
            moment: requestedMoment,
            calculationState: requestedState,
            message: base.message,
            status: base.status,
            previous: carryOverPreviousFor(prev, requested),
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    state,
    selectedMixture,
    scatterMoment,
    calculationState,
    scatterFetchToken,
  ]);

  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <WorkflowPageHeader
          step={acceptanceMode ? "Acceptance" : "Inspect"}
          eyebrow={acceptanceMode ? "Project acceptance" : "Read-only HDF5 inspection"}
          title={acceptanceMode ? "Close the project with evidence" : "Inspect and visualize an OpenMC HDF5"}
          description={acceptanceMode ? "Review the components, input contracts, Converter receipts, consumer runs, and independent validation criteria declared by this project. Raw HDF5 inspection remains available below for diagnosis." : "Use Inspect by itself: open an HDF5 read-only, see its structure and provenance, and—when it follows the MGXS handoff schema—review multigroup constants, uncertainty, fission spectrum, calculation states, and scattering moments. Nothing is converted or written."}
          input={acceptanceMode ? "Manifest-driven project + project-specific references" : "One local HDF5; MGXS handoff or generic OpenMC HDF5"}
          output={acceptanceMode ? "Auditable acceptance decision" : "Read-only structure, provenance, group constants, uncertainty, and scatter views"}
          actions={
            <Link
              href={
                acceptanceMode
                  ? projectRoot
                    ? projectCoreHref(projectRoot)
                    : "/projects"
                  : "/convert"
              }
              className="btn btn-secondary"
            >
              {acceptanceMode
                ? projectRoot
                  ? "Review declared consumer"
                  : "Choose project"
                : "Converter (optional)"}
            </Link>
          }
        />

        {acceptanceMode ? <ProjectAcceptance projectRoot={projectRoot} /> : null}

        <details className="rounded-xl border border-[var(--edge)] bg-black/10 p-3" open={!acceptanceMode}>
          <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
            {acceptanceMode ? "Diagnostic: inspect one HDF5 artifact" : "HDF5 inspector"}
          </summary>
          <div className="mt-4">

        <FormStep
          number="A"
          title="Choose one HDF5 artifact"
          description="Start at file level. After the summary loads, choose a mixture—and a calculation state when present—to review its physical group data."
          className="surface"
        >
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-stretch"
            onSubmit={inspect}
          >
            <input
              type="text"
              placeholder={placeholder}
              value={path}
              onChange={(e) => setPath(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-[var(--edge)] bg-[rgba(255,255,255,0.03)] px-3 py-2 font-mono text-sm text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none"
              spellCheck={false}
              autoComplete="off"
              aria-label="HDF5 file path"
            />
            <button
              type="button"
              onClick={() => setBrowserOpen(true)}
              className={`btn ${hasPath ? "btn-secondary" : "btn-primary"}`}
            >
              {hasPath ? "Choose another HDF5" : "Choose HDF5"}
            </button>
            <button
              ref={inspectButtonRef}
              type="submit"
              className="btn btn-primary"
              disabled={!hasPath || state.kind === "loading"}
            >
              {state.kind === "loading" ? "Reading…" : "Inspect HDF5"}
            </button>
          </form>

          <p className="mt-2 text-[12px] text-[var(--fg-3)]">
            {hasPath
              ? "Ready: inspection is read-only and will not change the HDF5."
              : "Choose or paste one HDF5 file to enable inspection."}
          </p>

          {canUseSavedPrefix ? (
            <button
              type="button"
              onClick={() => setPath(savedPrefix)}
              className="btn-link mt-1"
            >
              Use saved prefix: <code className="font-mono">{savedPrefix}</code>
            </button>
          ) : null}
        </FormStep>

        <FileBrowserModal
          open={browserOpen}
          // Prefer whatever the user has already typed - the common
          // flow is "open inspect, point at some/handoff.h5, click
          // Browse to pick a sibling file" rather than starting over
          // from the saved Settings prefix. ``pickBrowserStart``
          // strips a trailing file segment so opening the modal lands
          // in the right directory.
          initialPath={pickBrowserStart(path.trim() || savedPrefix)}
          extensions={["h5", "hdf5"]}
          fileTypeLabel="HDF5"
          chipLabel="H5"
          recentScope="hdf5"
          onClose={() => setBrowserOpen(false)}
          onSelect={(picked) => {
            setPath(picked);
            setBrowserOpen(false);
            // The modal already suppresses its own focus restore when
            // closing via select, so this ``focus()`` is the final word
            // on where the keyboard lands - the Inspect button, primed
            // for Enter.
            inspectButtonRef.current?.focus();
          }}
        />

        <section className="mt-6">
          <FileResultView state={state} />
        </section>

        {state.kind === "ok" ? (
          <section className="mt-6 space-y-6">
            <MixtureTable
              mixtures={state.data.mixtures}
              selectedName={selectedMixture}
              onSelect={handlePickMixture}
            />
            {state.data.mixtures.length > 0 ? (
              <MixturePanel
                handoff={state.data}
                mixtureState={mixtureState}
                selectedMixture={selectedMixture}
                scatterMoment={scatterMoment}
                scatterScale={scatterScale}
                calculationState={calculationState}
                onScatterMomentChange={handleScatterMomentChange}
                onScatterScaleChange={setScatterScale}
                onCalculationStateChange={setCalculationState}
                onScatterRetry={retryScatterFetch}
              />
            ) : null}
          </section>
        ) : null}
          </div>
        </details>
      </div>
    </main>
  );
}

function FileResultView({ state }: { state: State }) {
  if (state.kind === "idle") {
    return (
      <p className="text-sm text-[var(--fg-3)]">
        Tip: with{" "}
        <code className="font-mono">openmc2donjon serve --mock</code>{" "}
        running, any path (even a fake one) returns the bundled
        synthetic UI fixture so you can preview the layout. It is not physics
        evidence.
      </p>
    );
  }
  if (state.kind === "loading") {
    return <p className="text-sm text-[var(--fg-2)] tab-num">Reading…</p>;
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
  return <Summary data={state.data} />;
}

function MixturePanel({
  handoff,
  mixtureState,
  selectedMixture,
  scatterMoment,
  scatterScale,
  calculationState,
  onScatterMomentChange,
  onScatterScaleChange,
  onCalculationStateChange,
  onScatterRetry,
}: {
  handoff: HandoffInspection;
  mixtureState: MixtureState;
  selectedMixture: string | null;
  scatterMoment: number;
  scatterScale: ScatterScale;
  calculationState: string | null;
  onScatterMomentChange: (m: number) => void;
  onScatterScaleChange: (s: ScatterScale) => void;
  onCalculationStateChange: (state: string | null) => void;
  onScatterRetry: () => void;
}) {
  if (selectedMixture == null) {
    return (
      <p className="text-sm text-[var(--fg-3)]">
        Click a row above to load its multigroup constants and scattering data.
      </p>
    );
  }

  const detail = displayedDetail(mixtureState);
  // First-time load (no previous): show the simple loading line.
  if (detail == null && mixtureState.kind === "loading") {
    return (
      <p className="text-sm text-[var(--fg-2)] tab-num">
        Loading <span className="font-mono">{selectedMixture}</span>…
      </p>
    );
  }
  // First-time error (no previous): show a full error card and let the
  // user pick another mixture.
  if (detail == null && mixtureState.kind === "error") {
    return <MixtureErrorCard state={mixtureState} />;
  }
  if (detail == null) {
    return null;
  }

  const bounds = handoff.energy_bounds ?? [];
  // Only flag the heatmap as loading when we have a previous payload
  // to keep on screen; first-time loads already took the earlier
  // ``Loading…`` branch. The flagged moment is the *requested* one,
  // which differs from the currently-rendered ``previous.scatter``.
  const scatterLoadingMoment =
    mixtureState.kind === "loading" && mixtureState.previous != null
      ? mixtureState.moment
      : null;
  return (
    <div className="space-y-3">
      {mixtureState.kind === "error" && mixtureState.previous != null ? (
        <MixtureErrorBanner state={mixtureState} onRetry={onScatterRetry} />
      ) : null}
      {detail.available_states.length > 1 ? (
        <CalculationStateSelector
          states={detail.available_states}
          value={calculationState ?? detail.selected_state ?? ""}
          loading={mixtureState.kind === "loading"}
          onChange={onCalculationStateChange}
        />
      ) : null}
      <MixtureMeta detail={detail} />
      {bounds.length >= 2 ? (
        <CrossSectionPlot
          energyBounds={bounds}
          crossSections={detail.cross_sections}
          standardDeviations={detail.cross_section_std_dev}
          mixtureName={detail.mixture}
          fissionable={detail.fissionable}
        />
      ) : (
        <div className="glass rounded-xl p-5 text-sm text-[var(--fg-3)]">
          Cannot plot: the handoff has no <code>energy_bounds</code>{" "}
          (legacy file). Cross sections are still available via the API.
        </div>
      )}
      <GroupVectorTable
        energyBounds={bounds}
        series={auxiliaryGroupSeries(detail)}
      />
      {detail.scatter ? (
        <ScatterHeatmap
          scatter={detail.scatter}
          scatterStdDev={detail.scatter.std_dev_values}
          energyBounds={bounds}
          mixtureName={detail.mixture}
          moment={scatterMoment}
          scale={scatterScale}
          availableMoments={availableMoments(handoff)}
          onMomentChange={onScatterMomentChange}
          onScaleChange={onScatterScaleChange}
          loadingMoment={scatterLoadingMoment}
        />
      ) : null}
    </div>
  );
}

function displayedDetail(state: MixtureState): MixtureDetail | null {
  if (state.kind === "ok") return state.data;
  if (state.kind === "loading" || state.kind === "error") {
    return state.previous ?? null;
  }
  return null;
}

function CalculationStateSelector({
  states,
  value,
  loading,
  onChange,
}: {
  states: readonly string[];
  value: string;
  loading: boolean;
  onChange: (state: string | null) => void;
}) {
  return (
    <section className="glass rounded-xl p-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h3 className="text-sm font-semibold text-[var(--fg-1)]">
          Calculation state
        </h3>
        <p className="mt-1 text-[12px] text-[var(--fg-3)]">
          Values below come from one explicit <code>states/&lt;state&gt;</code>{" "}
          group. Changing state reloads the state-bound mixture vectors and
          scatter moment. A root reference-flux row, when shown, remains
          file-global and is not attributed to the selected state.
        </p>
      </div>
      <label className="flex min-w-[220px] flex-col gap-1 text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        State
        <select
          value={value}
          disabled={loading}
          onChange={(event) => onChange(event.target.value || null)}
          className="rounded-md border border-[var(--edge)] bg-[var(--bg-1)] px-3 py-2 font-mono text-sm normal-case tracking-normal text-[var(--fg-0)] focus:border-[var(--accent)] focus:outline-none disabled:opacity-60"
          aria-label="Calculation state"
        >
          {states.map((state) => (
            <option key={state} value={state}>
              {state}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

function auxiliaryGroupSeries(detail: MixtureDetail): GroupVectorSeries[] {
  const xs = detail.cross_sections;
  const uncertainty = detail.cross_section_std_dev;
  return [
    {
      key: "kappa_fission",
      label: "H-FACTOR / κΣf",
      description:
        "Energy-production constant consumed as DONJON H-FACTOR; kept separate from the reaction cross-section axis.",
      units: "unit not verified from HDF5",
      // Converter writes H-FACTOR whenever the dataset is present, including
      // for a calculation declared non-fissionable. Inspect must preserve the
      // raw vector instead of treating it like the fission / nu-fission / chi
      // family whose declaration Converter validates separately.
      values: xs.kappa_fission,
      standardDeviations: uncertainty.kappa_fission,
    },
    {
      key: "inverse_velocity",
      label: "Inverse neutron velocity (1/v)",
      description: "Groupwise inverse velocity consumed as DONJON OVERV.",
      units: "unit not verified from HDF5",
      values: xs.inverse_velocity,
      standardDeviations: uncertainty.inverse_velocity,
    },
    {
      key: "flux_weight",
      label: "Legacy local flux-like vector (Inspect only)",
      description:
        "File-local flux_weight/flux/flux_integral vector. Converter does not consume this field; only the bound root openmc_volume_flux route supplies downstream flux weighting.",
      units: "unit not verified from HDF5",
      values: xs.flux_weight,
      standardDeviations: uncertainty.flux_weight,
    },
    {
      key: "openmc_volume_flux",
      label: "OpenMC reference volume flux (file-global)",
      description:
        "Root reference-flux row matched through declared mixture_names and mgxs_donjon group order; it is not bound to the selected calculation state.",
      units: "unit not verified from HDF5",
      values: detail.openmc_volume_flux,
      standardDeviations: detail.openmc_volume_flux_std_dev,
    },
    {
      key: "sph",
      label: "SPH / NSPH factor",
      description:
        "Declared groupwise equivalence factor. Its presence is not evidence that an SPH iteration converged.",
      units: "dimensionless",
      values: xs.sph,
      standardDeviations: uncertainty.sph,
    },
  ];
}

function MixtureErrorCard({
  state,
}: {
  state: Extract<MixtureState, { kind: "error" }>;
}) {
  return (
    <div className="glass rounded-xl p-5 border-rose-500/20">
      <div className="text-sm font-semibold text-rose-300">
        {state.status ? `HTTP ${state.status}` : "Mixture read failed"}
      </div>
      <div className="mt-1 text-sm text-[var(--fg-1)]">{state.message}</div>
    </div>
  );
}

function MixtureErrorBanner({
  state,
  onRetry,
}: {
  state: Extract<MixtureState, { kind: "error" }>;
  onRetry: () => void;
}) {
  return (
    <div className="glass rounded-md px-3 py-2 border-rose-500/20 text-[13px] flex items-baseline gap-2 flex-wrap">
      <span className="font-semibold text-rose-300">
        {state.status ? `HTTP ${state.status}` : "Refresh failed"}
      </span>
      <span className="text-[var(--fg-1)]">{state.message}</span>
      <span className="text-[var(--fg-3)] text-[12px]">
        — {state.calculationState ? `${state.calculationState} · ` : ""}P
        {state.moment} did not load; keeping previous payload (
        {state.previous?.selected_state
          ? `${state.previous.selected_state} · `
          : ""}
        P{state.previous?.scatter?.moment_index ?? 0}).
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="btn-link"
      >
        Retry {state.calculationState ? `${state.calculationState} · ` : ""}P
        {state.moment}
      </button>
    </div>
  );
}

function availableMoments(handoff: HandoffInspection): readonly number[] {
  // Trust the file-level Legendre order. If absent, P0 is the only
  // safe assumption.
  const max = handoff.legendre_order ?? 0;
  return Array.from({ length: max + 1 }, (_, i) => i);
}

function pickBrowserStart(savedPrefix: string): string {
  // Prefer the user's saved Inspect prefix when it looks like a
  // directory (trailing slash, or just a folder path). Otherwise let
  // the backend resolve ``~`` to the server home / mock home.
  const trimmed = savedPrefix.trim();
  if (!trimmed) return "~";
  // Drop a trailing file segment so "~/runs/handoff.h5" still opens
  // the runs/ directory. Heuristic: if the basename has an extension,
  // strip it.
  const lastSlash = trimmed.lastIndexOf("/");
  if (lastSlash >= 0 && lastSlash < trimmed.length - 1) {
    const tail = trimmed.slice(lastSlash + 1);
    if (tail.includes(".")) {
      return trimmed.slice(0, lastSlash + 1);
    }
  }
  return trimmed;
}

function MixtureMeta({ detail }: { detail: MixtureDetail }) {
  const items: { label: string; value: string }[] = [];
  items.push({ label: "Mixture", value: detail.mixture });
  items.push({
    label: "Groups",
    value: detail.energy_groups == null ? "—" : String(detail.energy_groups),
  });
  items.push({
    label: "Legendre",
    value:
      detail.legendre_order == null ? "—" : `P${detail.legendre_order}`,
  });
  items.push({
    label: "Volume",
    value: detail.volume == null ? "—" : detail.volume.toFixed(3),
  });
  items.push({
    label: "Temperature",
    value:
      detail.temperature == null
        ? "—"
        : `${detail.temperature.toFixed(0)} K`,
  });
  items.push({
    label: "Declared fissionable",
    value:
      detail.fissionable == null ? "unknown" : detail.fissionable ? "yes" : "no",
  });
  if (detail.selected_state) {
    items.push({ label: "State", value: detail.selected_state });
  }
  const availableMeans = Object.values(detail.cross_sections).filter(
    (values) => values != null,
  ).length;
  const availableUncertainties = Object.values(
    detail.cross_section_std_dev,
  ).filter((values) => values != null).length;
  items.push({
    label: "Uncertainty",
    value: `${availableUncertainties}/${availableMeans} vectors`,
  });
  if (detail.scatter) {
    items.push({
      label: "Scatter moment",
      value: `P${detail.scatter.moment_index}`,
    });
  }
  return (
    <div className="glass rounded-xl p-4 flex flex-wrap gap-x-6 gap-y-2 text-sm tab-num">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col">
          <span className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
            {it.label}
          </span>
          <span className="font-mono">{it.value}</span>
        </div>
      ))}
    </div>
  );
}

function toErrorState(err: unknown): State {
  if (err instanceof ApiError) {
    return { kind: "error", message: err.message, status: err.status };
  }
  if (err instanceof Error) {
    return { kind: "error", message: err.message };
  }
  return { kind: "error", message: "Unknown error." };
}
