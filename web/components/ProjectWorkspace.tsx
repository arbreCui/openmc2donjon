"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type ProjectArtifactStatus,
  type ProjectComponentStatus,
  type ProjectStatus,
} from "@/lib/api";
import {
  PROJECT_ROOT_STORAGE_KEY,
  addProjectComponentToManifest,
  addProjectEvidenceToManifest,
  canEditProjectManifest,
  formatProjectManifest,
  isIrenaColorsetSphContract,
  isNativeSphContract,
  isPhysicalSphContract,
  isWithdrawnDiagnosticProject,
  normalizeProjectRoot,
  parseProjectManifestDraft,
  projectAcceptanceHref,
  projectComponentConvertHref,
  projectComponentEquivalenceHref,
  projectComponentPrepareHref,
  projectConsumerActionLabel,
  projectConsumerHref,
  projectEquivalenceActionLabel,
  projectReadinessPresentation,
  type ProjectComponentDraft,
} from "@/lib/projectWorkspace";

type StatusState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; data: ProjectStatus }
  | { kind: "error"; message: string };

type ManifestEditorPhase = "idle" | "loading" | "ready" | "saving" | "error";
type ProjectCreationMode = "handoff-only" | "physics-gated";
type ProjectWriter = "ascii" | "pygan";

const EMPTY_COMPONENT_DRAFT = {
  id: "",
  label: "",
  role: "",
  input: "",
  output: "",
  format: "multicompo" as const,
  contract: "converter-hdf5" as const,
  writerBackend: "ascii" as const,
  required: true,
};

export default function ProjectWorkspace() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryRoot = normalizeProjectRoot(searchParams.get("project"));
  const queryComponent =
    searchParams.get("component") ?? searchParams.get("colorset") ?? "";
  const candidateEvidence = searchParams.get("add_evidence") ?? "";
  const candidateEvidenceLabel = searchParams.get("evidence_label") ?? "Consumer diagnostic result";
  const [projectRoot, setProjectRoot] = useState(queryRoot);
  const [draftRoot, setDraftRoot] = useState(queryRoot);
  const [activeComponent, setActiveComponent] = useState(queryComponent);
  const [creationMode, setCreationMode] = useState<ProjectCreationMode>("handoff-only");
  const [creationWriter, setCreationWriter] = useState<ProjectWriter>("ascii");
  const [status, setStatus] = useState<StatusState>({ kind: "idle" });
  const [manifestDraft, setManifestDraft] = useState("");
  const [savedManifestDraft, setSavedManifestDraft] = useState("");
  const [manifestEditorPhase, setManifestEditorPhase] =
    useState<ManifestEditorPhase>("idle");
  const [manifestEditorMessage, setManifestEditorMessage] = useState<string | null>(
    null,
  );
  const [componentDraft, setComponentDraft] =
    useState<ProjectComponentDraft>(EMPTY_COMPONENT_DRAFT);
  const [componentAddMessage, setComponentAddMessage] = useState<string | null>(null);
  const [componentAdding, setComponentAdding] = useState(false);
  const [evidenceAdding, setEvidenceAdding] = useState(false);

  const refresh = useCallback(async (root: string) => {
    if (!root) {
      setStatus({ kind: "idle" });
      return;
    }
    setStatus({ kind: "loading" });
    try {
      const data = await api.projectStatus(root);
      setStatus({ kind: "ready", data });
      setActiveComponent((current) =>
        data.components.some((item) => item.id === current)
          ? current
          : data.components[0]?.id ?? "",
      );
    } catch (error) {
      setStatus({
        kind: "error",
        message:
          error instanceof ApiError
            ? error.detail ?? error.message
            : error instanceof Error
              ? error.message
              : "Could not inspect the project",
      });
    }
  }, []);

  useEffect(() => {
    if (queryRoot) {
      setProjectRoot(queryRoot);
      setDraftRoot(queryRoot);
      window.localStorage.setItem(PROJECT_ROOT_STORAGE_KEY, queryRoot);
      void refresh(queryRoot);
      return;
    }
    const saved = normalizeProjectRoot(window.localStorage.getItem(PROJECT_ROOT_STORAGE_KEY));
    if (saved) {
      setProjectRoot(saved);
      setDraftRoot(saved);
      void refresh(saved);
    }
  }, [queryRoot, refresh]);

  useEffect(() => {
    setManifestDraft("");
    setSavedManifestDraft("");
    setManifestEditorPhase("idle");
    setManifestEditorMessage(null);
  }, [projectRoot]);

  const data = status.kind === "ready" ? status.data : null;
  const rows = useMemo(() => data?.components ?? [], [data]);

  function openProject() {
    const root = normalizeProjectRoot(draftRoot);
    if (!root) return;
    setProjectRoot(root);
    window.localStorage.setItem(PROJECT_ROOT_STORAGE_KEY, root);
    const params = new URLSearchParams();
    params.set("project", root);
    if (activeComponent) params.set("component", activeComponent);
    router.replace(`/projects?${params.toString()}`);
    void refresh(root);
  }

  async function createProject() {
    const root = normalizeProjectRoot(draftRoot);
    if (!root) return;
    setStatus({ kind: "loading" });
    try {
      const created = await api.createProject(
        root,
        undefined,
        creationMode,
        creationWriter,
      );
      setProjectRoot(root);
      setActiveComponent(created.components[0]?.id ?? "");
      setStatus({ kind: "ready", data: created });
      window.localStorage.setItem(PROJECT_ROOT_STORAGE_KEY, root);
      router.replace(`/projects?project=${encodeURIComponent(root)}`);
    } catch (error) {
      setStatus({
        kind: "error",
        message:
          error instanceof ApiError
            ? error.detail ?? error.message
            : error instanceof Error
              ? error.message
              : "Could not create the project",
      });
    }
  }

  async function addProjectComponent() {
    if (!projectRoot || componentAdding) return;
    setComponentAdding(true);
    setComponentAddMessage(null);
    try {
      const current = await api.projectManifest(projectRoot);
      const appended = addProjectComponentToManifest(current.manifest, componentDraft);
      if (!appended.ok) {
        setComponentAddMessage(appended.message);
        return;
      }
      const response = await api.saveProjectManifest(projectRoot, appended.manifest);
      const formatted = formatProjectManifest(response.manifest);
      if (manifestEditorPhase !== "idle") {
        setManifestDraft(formatted);
        setSavedManifestDraft(formatted);
        setManifestEditorPhase("ready");
      }
      const refreshed = await api.projectStatus(projectRoot);
      setStatus({ kind: "ready", data: refreshed });
      setActiveComponent(componentDraft.id.trim());
      setComponentDraft(EMPTY_COMPONENT_DRAFT);
      setComponentAddMessage("Component added. Its manifest-owned Converter path is ready.");
    } catch (error) {
      setComponentAddMessage(
        projectEditorErrorMessage(error, "Could not add the project component"),
      );
    } finally {
      setComponentAdding(false);
    }
  }

  async function attachCandidateEvidence() {
    if (!projectRoot || !activeComponent || !candidateEvidence || evidenceAdding) return;
    setEvidenceAdding(true);
    setComponentAddMessage(null);
    try {
      const current = await api.projectManifest(projectRoot);
      const attached = addProjectEvidenceToManifest(
        current.manifest,
        projectRoot,
        activeComponent,
        candidateEvidence,
        candidateEvidenceLabel,
      );
      if (!attached.ok) {
        setComponentAddMessage(attached.message);
        return;
      }
      const response = await api.saveProjectManifest(projectRoot, attached.manifest);
      if (manifestEditorPhase !== "idle") {
        const formatted = formatProjectManifest(response.manifest);
        setManifestDraft(formatted);
        setSavedManifestDraft(formatted);
        setManifestEditorPhase("ready");
      }
      await refresh(projectRoot);
      setComponentAddMessage("Consumer result added to this component's declared evidence.");
      const params = new URLSearchParams({ project: projectRoot, component: activeComponent });
      router.replace(`/projects?${params.toString()}`);
    } catch (error) {
      setComponentAddMessage(
        projectEditorErrorMessage(error, "Could not add the consumer result evidence"),
      );
    } finally {
      setEvidenceAdding(false);
    }
  }

  async function loadProjectManifest(force = false) {
    if (!projectRoot || manifestEditorPhase === "loading" || manifestEditorPhase === "saving") {
      return;
    }
    if (!force && manifestEditorPhase !== "idle") return;
    setManifestEditorPhase("loading");
    setManifestEditorMessage(null);
    try {
      const response = await api.projectManifest(projectRoot);
      const formatted = formatProjectManifest(response.manifest);
      setManifestDraft(formatted);
      setSavedManifestDraft(formatted);
      setManifestEditorPhase("ready");
    } catch (error) {
      setManifestEditorPhase("error");
      setManifestEditorMessage(
        projectEditorErrorMessage(error, "Could not load the project manifest"),
      );
    }
  }

  async function saveProjectManifest() {
    if (!projectRoot || manifestEditorPhase === "saving") return;
    const parsed = parseProjectManifestDraft(manifestDraft);
    if (!parsed.ok) {
      setManifestEditorPhase("error");
      setManifestEditorMessage(parsed.message);
      return;
    }
    setManifestEditorPhase("saving");
    setManifestEditorMessage(null);
    let saved = false;
    try {
      const response = await api.saveProjectManifest(projectRoot, parsed.manifest);
      saved = true;
      const formatted = formatProjectManifest(response.manifest);
      setManifestDraft(formatted);
      setSavedManifestDraft(formatted);
      const refreshed = await api.projectStatus(projectRoot);
      setStatus({ kind: "ready", data: refreshed });
      setActiveComponent((current) =>
        refreshed.components.some((item) => item.id === current)
          ? current
          : refreshed.components[0]?.id ?? "",
      );
      setManifestEditorPhase("ready");
      setManifestEditorMessage("Saved. Project components and readiness were refreshed.");
    } catch (error) {
      setManifestEditorPhase("error");
      setManifestEditorMessage(
        projectEditorErrorMessage(
          error,
          saved
            ? "The manifest was saved, but project status could not be refreshed"
            : "The manifest was not saved",
        ),
      );
    }
  }

  const readiness = data ? projectReadinessPresentation(data) : null;
  const ready = data?.ready_for_consumer === true;
  const withdrawnProject = data ? isWithdrawnDiagnosticProject(data) : false;
  const manifestEditingAvailable = data ? canEditProjectManifest(data) : false;
  const selectedComponent = data?.components.find(
    (component) => component.id === activeComponent,
  );
  const converterHref = selectedComponent
    ? projectComponentConvertHref(projectRoot, selectedComponent)
    : projectRoot
      ? `/convert?project=${encodeURIComponent(projectRoot)}`
      : "/convert";

  return (
    <section className="overflow-hidden rounded-2xl border border-emerald-200/30 bg-[var(--surface)] shadow-[var(--shadow-md)]">
      <div className="border-b border-[var(--edge)] bg-emerald-300/[0.045] p-5 sm:p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="page-kicker">Manifest-driven project</p>
            <h2 className="mt-1 text-2xl font-bold tracking-[-0.03em]">
              Your project defines its components
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--fg-2)]">
              Converter does not assume five components, colorset geometry, SPH, or a
              91-position core. <code>openmc2donjon.project.json</code> declares each
              component, its input contract, output path, and downstream consumer.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-2 text-center sm:grid-cols-3">
            <ProjectStat
              value={readiness?.handoffValue ?? "0/–"}
              label={readiness?.handoffLabel ?? "handoffs"}
              tone={readiness?.handoffTone ?? "neutral"}
            />
            <ProjectStat
              value={readiness?.physicsValue ?? "N/A"}
              label={readiness?.physicsLabel ?? "acceptance"}
              tone={readiness?.physicsTone ?? "neutral"}
            />
            <ProjectStat
              value={readiness?.consumerValue ?? "HOLD"}
              label="consumer gate"
              tone={readiness?.consumerTone ?? "neutral"}
            />
          </div>
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_190px_170px_170px_auto] lg:items-end">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
              Project root
            </span>
            <input
              value={draftRoot}
              onChange={(event) => setDraftRoot(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && openProject()}
              placeholder="/runs/my-converter-project"
              className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm"
            />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
              Working component
            </span>
            <select
              value={activeComponent}
              onChange={(event) => setActiveComponent(event.target.value)}
              disabled={!rows.length}
              className="mt-2 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
            >
              {!rows.length ? <option value="">Defined by manifest</option> : null}
              {rows.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} · {item.id}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
              New project mode
            </span>
            <select
              value={creationMode}
              onChange={(event) => setCreationMode(event.target.value as ProjectCreationMode)}
              className="mt-2 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
            >
              <option value="handoff-only">Handoff only</option>
              <option value="physics-gated">Physics gated</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
              Initial writer
            </span>
            <select
              value={creationWriter}
              onChange={(event) => setCreationWriter(event.target.value as ProjectWriter)}
              className="mt-2 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
            >
              <option value="ascii">ASCII (default)</option>
              <option value="pygan">PyGan</option>
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void createProject()} disabled={!normalizeProjectRoot(draftRoot) || status.kind === "loading"} className="btn btn-secondary">
              Create starter
            </button>
            <button type="button" onClick={openProject} disabled={!normalizeProjectRoot(draftRoot) || status.kind === "loading"} className="btn btn-primary">
              {status.kind === "loading" ? "Working…" : "Open project"}
            </button>
          </div>
        </div>
        <p className="mt-2 text-[10px] leading-4 text-[var(--fg-3)]">
          {creationMode === "handoff-only"
            ? "Handoff only: validated Converter artifacts can be delivered without creating a physics-acceptance ledger. READY is a delivery state, not a physics verdict."
            : "Physics gated: create a project-declared pending ledger; the consumer stays on HOLD until its hash-linked criteria pass. A machine-verified label requires a supported validator."}
          {` Initial component writer: ${creationWriter === "pygan" ? "PyGan" : "built-in ASCII"}. Each later component may declare its own writer policy.`}
        </p>
        {status.kind === "error" ? <Message tone="error">{status.message}</Message> : null}
        {data && !data.configured ? (
          <Message tone="warning">
            This directory is not configured as a Converter project: {data.configuration_issues.join("; ")}. It is not treated as IRENA automatically. Create a generic starter here, or open one of the bundled examples below.
          </Message>
        ) : null}
        {data?.configured ? (
          <p className="mt-3 text-[11px] text-[var(--fg-3)]">
            <strong className="text-[var(--fg-1)]">{data.name}</strong>
            {data.template ? ` · example template: ${data.template}` : " · custom project"}
            {data.acceptance_mode === "handoff-only" ? " · handoff only" : " · physics gated"}
            {data.description ? ` · ${data.description}` : ""}
          </p>
        ) : null}
        {data?.configured && readiness?.explanation ? (
          <p
            className={
              "mt-3 rounded-lg border px-3 py-2 text-[11px] leading-5 " +
              (ready
                ? "border-emerald-300/20 bg-emerald-300/[0.05] text-emerald-100"
                : "border-amber-300/20 bg-amber-300/[0.05] text-amber-100")
            }
          >
            {readiness.explanation}
          </p>
        ) : null}
        {withdrawnProject ? (
          <Message tone="warning">
            This archived project is permanently rejected and diagnostic-only.
            Its component contracts cannot create OpenMC, Converter, or SPH actions.
          </Message>
        ) : null}
      </div>

      {data && manifestEditingAvailable ? (
        <div className="border-b border-[var(--edge)] bg-emerald-300/[0.025] px-5 py-4 sm:px-6">
          {candidateEvidence ? (
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-cyan-300/20 bg-cyan-300/[0.05] p-3 text-[11px] text-cyan-100">
              <div className="min-w-0">
                <strong>Add consumer evidence to {activeComponent || "the selected component"}</strong>
                <code className="mt-1 block truncate text-[10px] text-cyan-100/70" title={candidateEvidence}>
                  {candidateEvidence}
                </code>
              </div>
              <button
                type="button"
                onClick={() => void attachCandidateEvidence()}
                disabled={!activeComponent || evidenceAdding}
                className="btn btn-primary"
              >
                {evidenceAdding ? "Adding…" : "Confirm evidence link"}
              </button>
            </div>
          ) : null}
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="page-kicker">Normal project editing</p>
              <h3 className="mt-1 text-sm font-bold">Add another Converter component</h3>
              <p className="mt-1 max-w-3xl text-[11px] leading-5 text-[var(--fg-3)]">
                Components are independent manifest rows. Choose the exact input, output,
                format, contract, and writer for this model; no fixed component count or
                full-core map is assumed.
              </p>
            </div>
            <span className="rounded-full border border-emerald-300/20 bg-emerald-300/[0.06] px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-emerald-100">
              Raw JSON remains advanced
            </span>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <ProjectDraftField
              label="Component ID"
              value={componentDraft.id}
              placeholder="reflector"
              onChange={(value) => setComponentDraft((current) => ({ ...current, id: value }))}
            />
            <ProjectDraftField
              label="Label"
              value={componentDraft.label}
              placeholder="Reflector"
              onChange={(value) => setComponentDraft((current) => ({ ...current, label: value }))}
            />
            <ProjectDraftField
              label="MGXS HDF5 (project-relative)"
              value={componentDraft.input}
              placeholder="components/reflector/mgxs_library.h5"
              onChange={(value) => setComponentDraft((current) => ({ ...current, input: value }))}
            />
            <ProjectDraftField
              label="Converter output (project-relative)"
              value={componentDraft.output}
              placeholder="outputs/reflector.mcompo.txt"
              onChange={(value) => setComponentDraft((current) => ({ ...current, output: value }))}
            />
            <ProjectDraftField
              label="Role (optional)"
              value={componentDraft.role}
              placeholder="Radial reflector component"
              onChange={(value) => setComponentDraft((current) => ({ ...current, role: value }))}
            />
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--fg-3)]">Output object</span>
              <select
                value={componentDraft.format}
                onChange={(event) => setComponentDraft((current) => ({ ...current, format: event.target.value as ProjectComponentDraft["format"] }))}
                className="mt-1 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
              >
                <option value="multicompo">MULTICOMPO · reusable component/state library</option>
                <option value="macrolib">MACROLIB · one coarse model state</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--fg-3)]">Physics contract</span>
              <select
                value={componentDraft.contract}
                onChange={(event) => setComponentDraft((current) => ({ ...current, contract: event.target.value as ProjectComponentDraft["contract"] }))}
                className="mt-1 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
              >
                <option value="converter-hdf5">Converter HDF5</option>
                <option value="physical-sph">Physical SPH sidecar</option>
                <option value="native-sph">Native DRAGON SPH</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--fg-3)]">Writer policy</span>
              <select
                value={componentDraft.writerBackend}
                onChange={(event) => setComponentDraft((current) => ({ ...current, writerBackend: event.target.value as ProjectWriter }))}
                className="mt-1 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm"
              >
                <option value="ascii">Built-in ASCII</option>
                <option value="pygan">PyGan</option>
              </select>
            </label>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[11px] text-[var(--fg-2)]">
              <input
                type="checkbox"
                checked={componentDraft.required}
                onChange={(event) => setComponentDraft((current) => ({ ...current, required: event.target.checked }))}
              />
              Required before the consumer can open
            </label>
            <button
              type="button"
              onClick={() => void addProjectComponent()}
              disabled={componentAdding}
              className="btn btn-primary"
            >
              {componentAdding ? "Adding…" : "Add component"}
            </button>
            {componentAddMessage ? (
              <span className="text-[11px] text-[var(--fg-2)]">{componentAddMessage}</span>
            ) : null}
          </div>
        </div>
      ) : null}

      {data && manifestEditingAvailable ? (
        <div className="border-b border-[var(--edge)] bg-black/[0.08] px-5 py-3 sm:px-6">
          <details
            onToggle={(event) => {
              if (event.currentTarget.open) void loadProjectManifest();
            }}
          >
            <summary className="cursor-pointer select-none text-[11px] font-bold text-[var(--fg-2)]">
              Edit raw project manifest JSON (advanced)
            </summary>
            <div className="mt-3 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
              <p className="max-w-3xl text-[11px] leading-5 text-[var(--fg-3)]">
                Edit the project JSON directly when this model needs more, fewer, or different
                components. Saving is fail-closed: schema, component IDs, paths, contracts, and
                output formats must validate before the file is replaced. A <code>native-sph</code>
                component may add <code>native_sph</code> with project-relative <code>deck</code> and
                <code>working_directory</code>; Project then carries those exact paths into the runner.
                Its <code>receipt</code> is the Converter receipt, while <code>physics_summary</code>
                is a separate native-SPH result and can never substitute for that receipt.
              </p>
              <code className="mt-2 block break-all text-[10px] text-[var(--fg-3)]">
                {data.manifest_path}
              </code>
              {manifestEditorPhase === "loading" ? (
                <p className="mt-3 text-[11px] text-[var(--fg-3)]">Loading manifest…</p>
              ) : null}
              {manifestEditorPhase !== "idle" && manifestEditorPhase !== "loading" ? (
                <textarea
                  value={manifestDraft}
                  onChange={(event) => {
                    setManifestDraft(event.target.value);
                    setManifestEditorPhase("ready");
                    setManifestEditorMessage(null);
                  }}
                  disabled={manifestEditorPhase === "saving"}
                  spellCheck={false}
                  aria-label="Project manifest JSON"
                  className="mt-3 min-h-[320px] w-full resize-y rounded-lg border border-[var(--edge)] bg-black/25 p-3 font-mono text-[11px] leading-5 text-[var(--fg-1)]"
                />
              ) : null}
              {manifestEditorMessage ? (
                <p
                  className={
                    "mt-3 rounded-lg border px-3 py-2 text-[11px] leading-5 " +
                    (manifestEditorPhase === "error"
                      ? "border-rose-300/20 bg-rose-300/[0.06] text-rose-100"
                      : "border-emerald-300/20 bg-emerald-300/[0.05] text-emerald-100")
                  }
                >
                  {manifestEditorMessage}
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void saveProjectManifest()}
                  disabled={
                    manifestEditorPhase === "idle" ||
                    manifestEditorPhase === "loading" ||
                    manifestEditorPhase === "saving" ||
                    manifestDraft === savedManifestDraft
                  }
                  className="btn btn-primary"
                >
                  {manifestEditorPhase === "saving" ? "Saving…" : "Save manifest"}
                </button>
                <button
                  type="button"
                  onClick={() => void loadProjectManifest(true)}
                  disabled={manifestEditorPhase === "loading" || manifestEditorPhase === "saving"}
                  className="btn btn-secondary"
                >
                  Reload from disk
                </button>
              </div>
            </div>
          </details>
        </div>
      ) : null}

      {rows.length ? (
        <div className="overflow-x-auto">
          <div className="min-w-[760px]">
            <div className="grid grid-cols-[190px_1fr_1fr_1fr_150px] gap-px border-b border-[var(--edge)] bg-[var(--edge)] text-[9px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">
              <div className="bg-black/20 px-4 py-3">Component</div>
              <div className="bg-black/20 px-4 py-3">Declared evidence</div>
              <div className="bg-black/20 px-4 py-3">Converter input</div>
              <div className="bg-emerald-300/[0.07] px-4 py-3 text-emerald-100">Output + proof</div>
              <div className="bg-black/20 px-4 py-3">Next action</div>
            </div>
            {rows.map((component) => (
              <div key={component.id} className="grid grid-cols-[190px_1fr_1fr_1fr_150px] gap-px border-b border-[var(--edge)] bg-[var(--edge)] last:border-b-0">
                <button
                  type="button"
                  onClick={() => setActiveComponent(component.id)}
                  className={"bg-[var(--surface)] px-4 py-3 text-left transition hover:bg-white/[0.04] " + (activeComponent === component.id ? "ring-1 ring-inset ring-emerald-300/30" : "")}
                >
                  <strong className="block text-[12px] text-[var(--fg-0)]">{component.label}</strong>
                  <span className="mt-1 block font-mono text-[9px] text-[var(--fg-3)]">{component.id}</span>
                  <span className="mt-1 block text-[9px] text-[var(--fg-3)]">{contractLabel(component.contract)}{component.required ? "" : " · optional"}</span>
                  <span className="mt-1 block text-[9px] text-[var(--fg-3)]">
                    {component.format.toUpperCase()} · {component.conversion?.writer_backend === "pygan" ? "PyGan writer" : "ASCII writer"}
                  </span>
                  {component.native_sph ? (
                    <span
                      className="mt-1 block truncate text-[9px] text-cyan-100/80"
                      title={`${component.native_sph.deck_path} · working directory ${component.native_sph.working_directory}`}
                    >
                      native-SPH deck declared · not yet validated
                    </span>
                  ) : null}
                  {isNativeSphContract(component.contract) ? (
                    <span
                      className="mt-1 block truncate text-[9px] text-[var(--fg-3)]"
                      title={`Converter receipt: ${component.paths.receipt || "not declared"}\nSPH physics summary: ${component.paths.physics_summary || "not declared"}`}
                    >
                      Converter receipt + SPH summary are separate
                    </span>
                  ) : null}
                  {component.metadata.node_side_cm != null ? (
                    <span className="mt-1 block text-[9px] text-[var(--fg-3)]">
                      declared node side · {String(component.metadata.node_side_cm)} cm
                    </span>
                  ) : null}
                </button>
                <StageCell status={component.evidence} pendingLabel="not inspected" />
                <StageCell status={component.handoff} pendingLabel="input pending" />
                <StageCell status={component.output} pendingLabel={isNativeSphContract(component.contract) ? "native SPH pending" : "Converter pending"} emphasized />
                <div className="flex items-center bg-[var(--surface)] px-3 py-2">
                  <NextAction
                    projectRoot={projectRoot}
                    component={component}
                    withdrawnReviewHref={
                      withdrawnProject && data
                        ? projectConsumerHref(projectRoot, data.consumer)
                        : null
                    }
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="grid gap-4 p-5 md:grid-cols-2">
          <TemplateCard title="Generic starting point" count="1 component; edit to any model" path="examples/project_templates/minimal" onUse={() => setDraftRoot("examples/project_templates/minimal")} />
          <TemplateCard title="IRENA-30 strict full-core candidate" count="1 full-core handoff · starts on HOLD" path="examples/project_templates/irena30_fullcore" onUse={() => setDraftRoot("examples/project_templates/irena30_fullcore")} />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--edge)] bg-black/15 p-4">
        <p className="text-[11px] leading-5 text-[var(--fg-3)]">
          {projectRoot ? `Active project: ${projectRoot}` : "Open a manifest-driven project or use Converter directly."}
        </p>
        <div className="flex flex-wrap gap-2">
          {!withdrawnProject ? <Link href={converterHref} className="btn btn-secondary">Open Converter directly</Link> : null}
          <Link href={projectAcceptanceHref(projectRoot)} className="btn btn-secondary">{data?.acceptance_required ? "Review acceptance" : "Review handoff evidence"}</Link>
          {data?.configured && ready ? (
            <Link href={projectConsumerHref(projectRoot, data.consumer, selectedComponent)} className="btn btn-primary">
              {withdrawnProject ? "Review archived diagnostic →" : projectConsumerActionLabel(true, data.consumer.label)}
            </Link>
          ) : data?.configured ? (
            <Link href={projectAcceptanceHref(projectRoot)} className="btn btn-secondary">
              Consumer on HOLD · review project
            </Link>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function Message({ tone, children }: { tone: "error" | "warning"; children: React.ReactNode }) {
  return <p className={"mt-3 rounded-lg border px-3 py-2 text-[12px] " + (tone === "error" ? "border-rose-300/20 bg-rose-300/[0.06] text-rose-100" : "border-amber-300/20 bg-amber-300/[0.06] text-amber-100")}>{children}</p>;
}

function TemplateCard({ title, count, path, onUse }: { title: string; count: string; path: string; onUse: () => void }) {
  return <article className="rounded-xl border border-[var(--edge)] bg-black/10 p-4"><div className="text-sm font-bold">{title}</div><div className="mt-1 text-[10px] text-[var(--accent)]">{count}</div><code className="mt-3 block text-[10px] text-[var(--fg-3)]">{path}</code><button type="button" onClick={onUse} className="btn btn-secondary mt-3">Use this example path</button></article>;
}

function ProjectDraftField({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--fg-3)]">
        {label}
      </span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm"
      />
    </label>
  );
}

function ProjectStat({ value, label, tone }: { value: string; label: string; tone: "ready" | "hold" | "rejected" | "neutral" }) {
  const valueColor = tone === "ready" ? "text-emerald-100" : tone === "rejected" ? "text-rose-100" : tone === "hold" ? "text-amber-100" : "text-[var(--fg-1)]";
  return <div className="min-w-28 rounded-lg border border-emerald-200/20 bg-black/15 px-3 py-2"><div className={`font-mono text-lg font-bold ${valueColor}`}>{value}</div><div className="text-[9px] uppercase tracking-[0.12em] text-[var(--fg-3)]">{label}</div></div>;
}

function StageCell({ status, pendingLabel, emphasized = false }: { status: ProjectArtifactStatus | null; pendingLabel: string; emphasized?: boolean }) {
  const state = status?.state ?? "pending";
  const label = state === "accepted" ? "accepted" : state === "present" ? "present" : state === "not-required" ? "not required" : state === "rejected" ? "rejected" : state === "missing" ? "missing" : pendingLabel;
  const tone = state === "accepted" || state === "present" ? "border-emerald-300/20 bg-emerald-300/[0.07] text-emerald-100" : state === "rejected" ? "border-rose-300/20 bg-rose-300/[0.07] text-rose-100" : "border-[var(--edge)] bg-black/10 text-[var(--fg-3)]";
  return <div className={emphasized ? "bg-emerald-300/[0.035] px-4 py-3" : "bg-[var(--surface)] px-4 py-3"}><span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-semibold ${tone}`}>{label}</span>{status?.issues[0] ? <span className="mt-1.5 block truncate text-[10px] text-[var(--fg-3)]" title={status.issues.join("; ")}>{status.issues[0]}</span> : null}</div>;
}

function NextAction({ projectRoot, component, withdrawnReviewHref }: { projectRoot: string; component: ProjectComponentStatus; withdrawnReviewHref: string | null }) {
  if (withdrawnReviewHref) return <Link href={withdrawnReviewHref} className="text-[11px] font-bold text-amber-100">Review archived diagnostic →</Link>;
  if (component.handoff.state !== "accepted") return (
    <div className="space-y-1.5">
      <Link href={projectComponentConvertHref(projectRoot, component)} className="block text-[11px] font-bold text-[var(--accent)]">
        Provide / inspect HDF5 →
      </Link>
      <Link href={projectComponentPrepareHref(projectRoot, component)} className="block text-[9px] text-[var(--fg-3)] hover:text-[var(--fg-1)]">
        Create it with OpenMC (optional)
      </Link>
    </div>
  );
  if (isNativeSphContract(component.contract) && nativeConverterReferenceMissing(component)) return <Link href={projectComponentConvertHref(projectRoot, component)} className="text-[11px] font-bold text-[var(--accent)]">Run Converter →</Link>;
  if (isPhysicalSphContract(component.contract) && (component.evidence.state === "missing" || component.evidence.state === "rejected" || component.output.state !== "accepted")) return <Link href={projectComponentEquivalenceHref(projectRoot, component)} className="text-[11px] font-bold text-[var(--accent)]">{projectEquivalenceActionLabel(component.contract)} →</Link>;
  if (component.output.state !== "accepted") return <Link href={projectComponentConvertHref(projectRoot, component)} className="text-[11px] font-bold text-[var(--accent)]">Run Converter →</Link>;
  return <span className="text-[11px] font-bold text-emerald-100">Complete ✓</span>;
}

function nativeConverterReferenceMissing(component: ProjectComponentStatus): boolean {
  const reference = component.paths.evidence.find((item) => item.id.toLowerCase() === "reference" || item.label.toLowerCase().includes("converter reference"));
  if (!reference) return component.evidence.state !== "present" && component.evidence.state !== "accepted";
  const label = reference.label.toLowerCase();
  return component.evidence.issues.some((issue) => issue.toLowerCase().includes("missing") && issue.toLowerCase().includes(label));
}

function contractLabel(contract: ProjectComponentStatus["contract"]): string {
  if (isNativeSphContract(contract)) return "Converter reference + native DRAGON SPH";
  if (isIrenaColorsetSphContract(contract)) return "IRENA seven-domain physical SPH";
  if (isPhysicalSphContract(contract)) return "strict physical SPH (arbitrary declared domains)";
  return "standard Converter HDF5";
}

function projectEditorErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.detail ?? error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}
