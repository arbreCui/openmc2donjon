"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, type ProjectComponentStatus, type ProjectStatus } from "@/lib/api";
import { WITHDRAWN_COLORSET_DIAGNOSTIC } from "@/lib/colorsetWorkflow";
import {
  isIrenaColorsetSphContract,
  isPhysicalSphContract,
  isWithdrawnDiagnosticProject,
  projectComponentConvertHref,
  projectComponentEquivalenceHref,
  projectComponentPrepareHref,
  projectConsumerHref,
  projectEquivalenceActionLabel,
  projectRootFromSearchParams,
} from "@/lib/projectWorkspace";

export default function ColorsetConverterWorkflow() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const projectRoot = projectRootFromSearchParams(searchParams);
  const requestedId = searchParams.get("component") ?? searchParams.get("colorset") ?? "";
  const [projectStatus, setProjectStatus] = useState<ProjectStatus | null>(null);
  const [selectedId, setSelectedId] = useState(requestedId);

  useEffect(() => {
    if (!projectRoot) {
      setProjectStatus(null);
      return;
    }
    let cancelled = false;
    api.projectStatus(projectRoot).then((data) => {
      if (cancelled) return;
      setProjectStatus(data);
      const nextId = data.components.some((item) => item.id === requestedId)
        ? requestedId
        : data.components[0]?.id ?? "";
      setSelectedId(nextId);
      if (isWithdrawnDiagnosticProject(data)) {
        router.replace(withdrawnProjectViewHref(projectRoot, nextId), { scroll: false });
      } else if (!requestedId && data.components[0]) {
        router.replace(projectComponentConvertHref(projectRoot, data.components[0]), { scroll: false });
      }
    }).catch(() => !cancelled && setProjectStatus(null));
    return () => { cancelled = true; };
  }, [projectRoot, requestedId, router]);

  const components = useMemo(() => projectStatus?.components ?? [], [projectStatus]);
  const selected = useMemo(
    () => components.find((item) => item.id === selectedId) ?? components[0] ?? null,
    [components, selectedId],
  );

  function chooseComponent(component: ProjectComponentStatus) {
    setSelectedId(component.id);
    router.replace(
      projectStatus && isWithdrawnDiagnosticProject(projectStatus)
        ? withdrawnProjectViewHref(projectRoot, component.id)
        : projectComponentConvertHref(projectRoot, component),
      { scroll: false },
    );
  }

  if (!projectRoot || !projectStatus?.configured || !selected) {
    return null;
  }

  const required = projectStatus.required_components;
  const isIrena = projectStatus.template === "irena30-colorset-core";
  const withdrawnProject = isWithdrawnDiagnosticProject(projectStatus);
  const withdrawnSelected =
    withdrawnProject || isIrenaColorsetSphContract(selected.contract);
  return (
    <section data-testid="project-converter-workflow" className="mb-6 overflow-hidden rounded-2xl border border-emerald-200/30 bg-[var(--surface)] shadow-[var(--shadow-sm)]">
      <div className="flex flex-col gap-4 border-b border-[var(--edge)] bg-emerald-300/[0.045] p-4 sm:p-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-emerald-200/80">Project component control</p>
          <h2 className="mt-1 text-xl font-bold tracking-tight">{projectStatus.name}</h2>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            This manifest defines {required} required component{required === 1 ? "" : "s"}.
            {withdrawnProject ? " This project is permanently withdrawn diagnostic-only; component contracts cannot reopen production actions." : isIrena ? " This archived five-component colorset manifest is diagnostic only; it cannot establish IRENA full-core acceptance." : " Their names and contracts come from this project, not from Converter."}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Stat value={`${projectStatus.accepted_inputs}/${required}`} label="inputs" />
          <Stat value={`${projectStatus.accepted_outputs}/${required}`} label="outputs" emphasized />
        </div>
      </div>

      <div className="grid gap-px bg-[var(--edge)]" style={{ gridTemplateColumns: `repeat(${Math.min(components.length, 6)}, minmax(0, 1fr))` }}>
        {components.map((item) => (
          <button key={item.id} type="button" onClick={() => chooseComponent(item)} className={"min-h-20 bg-[var(--surface)] p-3 text-left transition hover:bg-white/[0.04] " + (selected.id === item.id ? "ring-1 ring-inset ring-emerald-300/35" : "")}>
            <span className="flex items-center justify-between gap-2"><strong className="text-[11px]">{item.label}</strong><TinyState state={item.output.state} /></span>
            <span className="mt-1 block font-mono text-[9px] text-[var(--fg-3)]">{item.id}</span>
            <span className="mt-1 block text-[9px] text-[var(--fg-3)]">{item.required ? "required" : "optional"}</span>
          </button>
        ))}
      </div>

      <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <div>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">Working component</span>
            <select data-testid="component-selector" value={selected.id} onChange={(event) => { const item = components.find((candidate) => candidate.id === event.target.value); if (item) chooseComponent(item); }} className="mt-2 w-full rounded-md border border-[var(--edge)] px-3 py-2 text-sm">
              {components.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.id}</option>)}
            </select>
          </label>
          {isIrena && selected.target && selected.neighbors ? <EnvironmentGlyph target={selected.target} neighbors={selected.neighbors} /> : <GenericComponentGlyph label={selected.label} />}
          <p className="mt-3 text-[11px] leading-5 text-[var(--fg-3)]">Contract: <code>{selected.contract}</code></p>
        </div>

        <article className="rounded-xl border border-[var(--edge)] bg-black/15 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <span className="rounded-md border border-emerald-200/25 bg-emerald-300/10 px-2 py-1 font-mono text-[11px] font-bold text-emerald-100">{selected.id}</span>
              <h3 className="mt-3 text-base font-bold">{selected.label}</h3>
              {selected.role ? <p className="mt-1 text-[12px] text-[var(--fg-2)]">{selected.role}</p> : null}
              <p className="mt-2 text-[10px] text-[var(--fg-3)]">Output: <code>{selected.paths.output}</code></p>
              <p className="mt-1 text-[10px] text-[var(--fg-3)]">Receipt: <code>{selected.paths.receipt}</code></p>
            </div>
            <span className="text-[10px] text-[var(--fg-3)]">{selected.required ? "required" : "optional"}</span>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <StageStatus label="evidence" state={selected.evidence.state} />
            <StageStatus label="Converter input" state={selected.handoff.state} />
            <StageStatus label="output + receipt" state={selected.output.state} emphasized />
          </div>
          {firstIssue(selected) ? <p className="mt-3 rounded-lg border border-amber-300/15 bg-amber-300/[0.045] px-3 py-2 text-[11px] leading-5 text-amber-100/85">{firstIssue(selected)}</p> : null}
          <p className="mt-3 text-[11px] leading-5 text-[var(--fg-3)]">
            {withdrawnProject
              ? "These artifact paths and declared contracts are historical metadata only. The project-level withdrawal overrides every component action."
              : "OpenMC MGXS preparation is optional. If the declared HDF5 already exists, start with Converter; physical SPH remains a separate coarse-model step."}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {withdrawnProject ? (
              <Link href={projectConsumerHref(projectRoot, projectStatus.consumer)} className="btn btn-secondary">
                Review archived diagnostic →
              </Link>
            ) : <><Link href={projectComponentPrepareHref(projectRoot, selected)} className="btn btn-secondary">
              {withdrawnSelected ? "Review archived MGXS path" : "Prepare MGXS (optional)"}
            </Link>
            <Link href={projectComponentConvertHref(projectRoot, selected)} className={withdrawnSelected ? "btn btn-secondary" : "btn btn-primary"}>
              {withdrawnSelected ? "Review withdrawn Converter route" : "Run Converter"}
            </Link>
            {isPhysicalSphContract(selected.contract) ? <Link href={projectComponentEquivalenceHref(projectRoot, selected)} className="btn btn-secondary">{withdrawnSelected ? "Review archived SPH evidence" : projectEquivalenceActionLabel(selected.contract)}</Link> : null}
            </>}
          </div>
        </article>
      </div>
    </section>
  );
}

function withdrawnProjectViewHref(projectRoot: string, componentId: string): string {
  const params = new URLSearchParams({
    project: projectRoot,
    diagnostic: WITHDRAWN_COLORSET_DIAGNOSTIC,
  });
  if (componentId) params.set("component", componentId);
  return `/convert?${params.toString()}`;
}

function Stat({ value, label, emphasized = false }: { value: string; label: string; emphasized?: boolean }) { return <div className={"min-w-24 rounded-lg border px-3 py-2 text-center " + (emphasized ? "border-emerald-200/30 bg-emerald-300/10" : "border-[var(--edge)] bg-black/15")}><div className="font-mono text-lg font-bold">{value}</div><div className="text-[9px] uppercase tracking-[0.12em] text-[var(--fg-3)]">{label}</div></div>; }
function TinyState({ state }: { state?: string }) { return <span className={"h-2 w-2 rounded-full " + (state === "accepted" ? "bg-emerald-300" : state === "rejected" ? "bg-rose-300" : "bg-white/20")} aria-label={state ?? "not inspected"} />; }
function StageStatus({ label, state, emphasized = false }: { label: string; state?: string; emphasized?: boolean }) { const text = state === "accepted" ? "accepted" : state === "present" ? "present" : state === "not-required" ? "not required" : state === "rejected" ? "rejected" : state === "missing" ? "missing" : "pending"; return <div className={"rounded-lg border p-3 " + (emphasized ? "border-emerald-200/25 bg-emerald-300/[0.06]" : "border-[var(--edge)] bg-black/10")}><div className="text-[9px] uppercase tracking-[0.12em] text-[var(--fg-3)]">{label}</div><div className={"mt-1 text-[11px] font-bold " + (text === "accepted" || text === "present" ? "text-emerald-100" : text === "rejected" ? "text-rose-100" : "text-[var(--fg-2)]")}>{text}</div></div>; }
function firstIssue(component: ProjectComponentStatus): string | null { return component.handoff.issues[0] ?? component.output.issues[0] ?? component.evidence.issues[0] ?? null; }
function GenericComponentGlyph({ label }: { label: string }) { return <div className="mt-4 grid place-items-center"><div className="grid h-20 w-20 place-items-center rounded-2xl border border-emerald-200/25 bg-emerald-300/[0.07] px-2 text-center text-[11px] font-bold text-emerald-100">{label}</div></div>; }
function EnvironmentGlyph({ target, neighbors }: { target: string; neighbors: string }) { return <div aria-label={`${target} center with six ${neighbors} neighbors`} className="mt-4 flex justify-center"><div className="grid grid-cols-3 gap-1 font-mono text-[9px]"><span /><Hex label={neighbors} /><span /><Hex label={neighbors} /><Hex label={target} target /><Hex label={neighbors} /><Hex label={neighbors} /><Hex label={neighbors} /><Hex label={neighbors} /></div></div>; }
function Hex({ label, target = false }: { label: string; target?: boolean }) { return <span className={"flex h-7 w-9 items-center justify-center border " + (target ? "border-emerald-200/45 bg-emerald-300/15 text-emerald-100" : "border-sky-200/20 bg-sky-300/[0.06] text-sky-100/75")} style={{ clipPath: "polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%)" }}>{label}</span>; }
