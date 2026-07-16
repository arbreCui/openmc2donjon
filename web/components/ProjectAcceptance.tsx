"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type ProjectStatus } from "@/lib/api";
import { projectConsumerHref } from "@/lib/projectWorkspace";

export default function ProjectAcceptance({ projectRoot }: { projectRoot: string }) {
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!projectRoot) { setStatus(null); return; }
    let cancelled = false;
    setFailed(false);
    api.projectStatus(projectRoot).then((data) => !cancelled && setStatus(data)).catch(() => !cancelled && setFailed(true));
    return () => { cancelled = true; };
  }, [projectRoot]);

  if (!projectRoot) return <section className="surface mb-6 p-5"><p className="page-kicker">No project selected</p><h2 className="mt-1 text-lg font-bold">Open a manifest-driven project first</h2><p className="mt-2 text-sm text-[var(--fg-2)]">Acceptance criteria depend on that project&apos;s components and consumer.</p><Link href="/projects" className="btn btn-primary mt-4">Choose project</Link></section>;
  if (!status) return <section className="surface mb-6 p-5 text-sm text-[var(--fg-2)]">{failed ? "Project status could not be read." : "Reading project acceptance evidence…"}</section>;
  if (!status.configured) return <section className="surface mb-6 p-5"><p className="page-kicker">Unconfigured directory</p><h2 className="mt-1 text-lg font-bold">No project acceptance model exists yet</h2><p className="mt-2 text-sm text-[var(--fg-2)]">{status.configuration_issues.join("; ")}</p></section>;

  const required = status.required_components;
  const completedRuns = status.consumer.runs.filter((item) => item.state === "completed").length;
  const acceptance = status.acceptance;
  const passedCriteria = acceptance.criteria.filter((item) => item.status === "passed").length;
  const acceptanceLabel = acceptanceStateLabel(acceptance.state);
  const acceptanceTone = acceptanceStateTone(acceptance.state);
  const machineVerified = acceptance.basis === "machine-verified";
  const notRequired = acceptance.basis === "not-required";
  const acceptanceBasisLabel = notRequired
    ? "Physics gate not required"
    : machineVerified
    ? "Machine-verified acceptance"
    : "Project-declared acceptance";
  const acceptanceDescription = notRequired
    ? "This is a handoff-only project. Converter still validates every required input, output, and hash-linked receipt, but no physics-acceptance decision is requested or implied."
    : machineVerified
      ? "This project requires both its decision ledger and a file-backed machine validator. The validator rechecks every declared input hash and binds the result to the project component and native-SPH summary."
      : "This model owner declares external acceptance criteria and evidence. Converter checks the ledger structure and hashes, but does not turn those project-owned criteria into a generic machine-verified physics verdict.";
  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-[var(--edge)] bg-[var(--surface)]">
      <div className="border-b border-[var(--edge)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="page-kicker">{acceptanceBasisLabel}</p><h2 className="mt-1 text-xl font-bold">{status.name}</h2><p className="mt-2 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">{acceptanceDescription}</p></div>
          <span className={`rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.13em] ${acceptanceTone}`}>{acceptanceLabel}</span>
        </div>
      </div>
      <div className="grid gap-px bg-[var(--edge)] md:grid-cols-4">
        <LedgerItem label="Declared inputs" value={`${status.accepted_inputs}/${required}`} tone={status.accepted_inputs === required ? "pass" : "pending"} body="Each component uses its own manifest contract" />
        <LedgerItem label="Converter outputs" value={`${status.accepted_outputs}/${required}`} tone={status.accepted_outputs === required ? "pass" : "pending"} body="Hash-linked object + receipt" />
        <LedgerItem label="Consumer runs" value={status.consumer.runs.length ? `${completedRuns}/${status.consumer.runs.length}` : "external"} tone={!status.consumer.runs.length ? "neutral" : completedRuns === status.consumer.runs.length ? "pass" : "pending"} body={status.consumer.label} />
        <LedgerItem label={notRequired ? "Physics gate" : machineVerified ? "Machine validation" : "External acceptance"} value={notRequired ? "N/A" : machineVerified && acceptance.machine_validation.checks_total ? `${acceptance.machine_validation.checks_passed}/${acceptance.machine_validation.checks_total}` : acceptance.criteria.length ? `${passedCriteria}/${acceptance.criteria.length}` : acceptanceLabel} tone={notRequired ? "neutral" : acceptance.state === "accepted" ? "pass" : acceptance.state === "rejected" || acceptance.state === "invalid" ? "fail" : "pending"} body={notRequired ? "Not required by handoff-only mode; no physics verdict" : machineVerified ? `${acceptance.machine_validation.contract ?? "Declared validator"}; live hashes required` : "Project-declared criteria; not a generic Converter physics verdict"} />
      </div>
      <div className="border-t border-[var(--edge)] p-4">
        {notRequired ? (
          <p className="rounded-lg border border-[var(--edge)] bg-black/10 px-3 py-2 text-[12px] text-[var(--fg-2)]">No acceptance ledger is created in handoff-only mode. Consumer READY means every required handoff contract passed; it does not mean physics equivalence or reactor acceptance passed.</p>
        ) : !acceptance.declared ? (
          <p className="rounded-lg border border-rose-300/20 bg-rose-300/[0.05] px-3 py-2 text-[12px] text-rose-100">This physics-gated project is missing its required <code>acceptance.decision</code> declaration and remains fail-closed.</p>
        ) : (
          <div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><h3 className="text-sm font-bold">{acceptanceBasisLabel} decision</h3>{acceptance.summary ? <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">{acceptance.summary}</p> : null}</div>
              {acceptance.decision_path ? <code className="max-w-full break-all text-[10px] text-[var(--fg-3)]">{acceptance.decision_path}</code> : null}
            </div>
            {acceptance.criteria.length ? <div className="mt-3 grid gap-2 md:grid-cols-2">{acceptance.criteria.map((criterion) => <article key={criterion.id} className="rounded-lg border border-[var(--edge)] bg-black/10 p-3"><div className="flex items-center justify-between gap-2"><strong className="text-[12px]">{criterion.label}</strong><span className={`rounded-full border px-2 py-0.5 text-[9px] uppercase ${criterion.status === "passed" ? "border-emerald-300/25 text-emerald-100" : criterion.status === "failed" ? "border-rose-300/25 text-rose-100" : "border-amber-300/25 text-amber-100"}`}>{criterion.status}</span></div><p className="mt-2 text-[10px] text-[var(--fg-3)]">{criterion.evidence.length ? `${criterion.evidence.length} declared evidence file${criterion.evidence.length === 1 ? "" : "s"}` : "No evidence file declared yet"}</p></article>)}</div> : null}
            {machineVerified ? <div className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-[12px]">Machine validator: {acceptance.machine_validation.contract}</strong><span className="font-mono text-[10px] uppercase text-[var(--fg-3)]">{acceptance.machine_validation.state}</span></div>{acceptance.machine_validation.summary_path ? <code className="mt-2 block break-all text-[10px] text-[var(--fg-3)]">{acceptance.machine_validation.summary_path}</code> : null}{acceptance.machine_validation.issues.length ? <p className="mt-2 text-[11px] leading-5 text-rose-100">{acceptance.machine_validation.issues.join("; ")}</p> : null}</div> : null}
            {acceptance.issues.length ? <p className="mt-3 rounded-lg border border-rose-300/20 bg-rose-300/[0.05] px-3 py-2 text-[11px] leading-5 text-rose-100">{acceptance.issues.join("; ")}</p> : null}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--edge)] bg-black/15 p-4"><div className="font-mono text-[11px] text-[var(--fg-3)]">{projectRoot}</div><Link href={projectConsumerHref(projectRoot, status.consumer)} className="btn btn-secondary">{status.ready_for_consumer ? notRequired ? "Open handoff consumer" : "Open released consumer" : "Review HOLD consumer"}</Link></div>
    </section>
  );
}

function LedgerItem({ label, value, body, tone }: { label: string; value: string; body: string; tone: "pass" | "pending" | "fail" | "neutral" }) { const color = tone === "pass" ? "text-emerald-100" : tone === "fail" ? "text-rose-100" : tone === "neutral" ? "text-[var(--fg-1)]" : "text-amber-100"; return <article className="bg-[var(--surface)] p-4"><div className="text-[9px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">{label}</div><div className={`mt-2 font-mono text-lg font-bold ${color}`}>{value}</div><p className="mt-1 text-[10px] leading-4 text-[var(--fg-3)]">{body}</p></article>; }

function acceptanceStateLabel(state: ProjectStatus["acceptance"]["state"]): string { if (state === "accepted") return "accepted"; if (state === "rejected") return "rejected"; if (state === "invalid") return "invalid decision"; if (state === "missing") return "decision missing"; if (state === "not-required") return "not required"; return "acceptance pending"; }

function acceptanceStateTone(state: ProjectStatus["acceptance"]["state"]): string { if (state === "accepted") return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100"; if (state === "not-required") return "border-[var(--edge)] bg-black/10 text-[var(--fg-2)]"; if (state === "rejected" || state === "invalid") return "border-rose-300/25 bg-rose-300/10 text-rose-100"; return "border-amber-300/25 bg-amber-300/10 text-amber-100"; }
