"use client";

import { Suspense } from "react";
import ConvertReport from "@/components/convert/ConvertReport";
import BackendModeCard from "@/components/convert/BackendModeCard";
import ConvertForm from "@/components/convert/ConvertForm";
import ConvertIntentBanner from "@/components/convert/ConvertIntentBanner";
import ConvertShowcase from "@/components/convert/ConvertShowcase";
import ColorsetConverterWorkflow from "@/components/convert/ColorsetConverterWorkflow";
import LiveMinicaseCard from "@/components/convert/LiveMinicaseCard";
import MockDemoCard from "@/components/convert/MockDemoCard";
import ProductionMinicaseMissingHint from "@/components/convert/ProductionMinicaseMissingHint";
import { convertIntentBannerVisible } from "@/lib/convertIntent";
import { convertShowcaseDefaultOpen } from "@/lib/convertShowcase";
import { useConvertPageState } from "@/lib/useConvertPageState";
import { WorkflowPageHeader } from "@/components/ui/Workflow";
import Link from "next/link";

export default function ConvertPage() {
  return (
    <Suspense fallback={<ConvertLoading />}>
      <ConvertPageContent />
    </Suspense>
  );
}

function ConvertLoading() {
  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading Converter…
        </section>
      </div>
    </main>
  );
}

function ConvertPageContent() {
  const model = useConvertPageState();
  const conversionBlocked =
    model.withdrawnIrenaColorsetWorkflow ||
    model.projectPolicyChecking ||
    model.projectPolicyUnavailable;
  const sphParams = new URLSearchParams({
    kind: "openmc-sph-sidecar",
    contract: "physical-sph",
  });
  if (model.componentId) sphParams.set("component", model.componentId);
  if (model.projectRoot) sphParams.set("project", model.projectRoot);
  const sphHref = `/equivalence?${sphParams.toString()}`;
  // Never carry a withdrawn five-colorset project into the strict full-core
  // route. A compatible 91/21-domain project must be opened there explicitly.
  const strictIrenaHref = "/donjon?mode=irena30-fullcore";

  return (
    <main className="app-page">
      <div className="app-container max-w-5xl">
        <WorkflowPageHeader
          step="Converter"
          eyebrow={model.withdrawnIrenaColorsetWorkflow ? "Withdrawn diagnostic" : "Direct conversion"}
          title={model.withdrawnIrenaColorsetWorkflow ? "Review the archived IRENA five-colorset handoff" : "Convert an OpenMC handoff to a DONJON object"}
          description={model.withdrawnIrenaColorsetWorkflow ? "This URL belongs to the withdrawn five-colorset IRENA experiment. Its paths remain visible for historical diagnosis, but it cannot run Converter or create a production receipt." : "Select one openmc2donjon MGXS handoff HDF5, run the no-write validation, then write L_MULTICOMPO or L_MACROLIB with a hash-linked receipt. A project is optional."}
          input={model.withdrawnIrenaColorsetWorkflow ? "Archived seven-domain colorset artifact (diagnostic only)" : model.requirePhysicalSph ? "One physical-SPH-applied MGXS HDF5 with arbitrary declared domains" : "One OpenMC MGXS HDF5 handoff"}
          output={model.withdrawnIrenaColorsetWorkflow ? "No production output; historical metadata only" : "One checked L_MULTICOMPO or L_MACROLIB object + receipt"}
          actions={
            <Link
              href={model.withdrawnIrenaColorsetWorkflow ? strictIrenaHref : model.requirePhysicalSph ? sphHref : "/openmc"}
              className="btn btn-secondary"
            >
              {model.withdrawnIrenaColorsetWorkflow ? "Open current IRENA route" : model.requirePhysicalSph ? "Finish physical SPH" : "Need to create an HDF5?"}
            </Link>
          }
        />

        <ColorsetConverterWorkflow />

        {model.projectPolicyChecking ? (
          <section className="rounded-xl border border-[var(--edge)] bg-black/10 p-4 text-sm text-[var(--fg-2)]">
            Checking this project&apos;s workflow policy before exposing Converter actions…
          </section>
        ) : model.projectPolicyUnavailable ? (
          <section className="rounded-xl border border-rose-300/25 bg-rose-300/[0.055] p-4 text-sm text-rose-100">
            Converter actions are blocked because the project manifest policy could not be inspected.
          </section>
        ) : null}

        {model.withdrawnIrenaColorsetWorkflow ? (
          <WithdrawnColorsetDiagnostic
            colorsetId={model.colorsetId}
            inputPath={model.inputPath}
            outputPath={model.displayedOutput}
            strictHref={strictIrenaHref}
          />
        ) : null}

        {convertIntentBannerVisible(model.intent.intent) && !model.requirePhysicalSph && !conversionBlocked ? (
          <ConvertIntentBanner intent={model.intent} />
        ) : null}
        {!conversionBlocked && model.backendMode === "mock" && !model.requirePhysicalSph ? (
          <MockDemoCard
            onApply={model.applyC5g7Demo}
            onDryRun={() => void model.runC5g7DemoDryRun()}
            onConvert={() => void model.runC5g7DemoConvert()}
            dryRunLoading={
              model.state.kind === "loading" && model.state.mode === "dry-run"
            }
            convertLoading={
              model.state.kind === "loading" && model.state.mode === "convert"
            }
            canConvert={model.c5g7DemoDryRunPassed}
            converted={model.c5g7DemoConverted}
          />
        ) : model.backendMode === "unavailable" ? (
          <BackendModeCard
            tone="error"
            title="Backend status unavailable"
            body="Start or restart the FastAPI backend with openmc2donjon serve; the page will not show live minicase paths until /api/health responds."
          />
        ) : null}

        {!conversionBlocked ? <section id="convert-component" className="scroll-mt-24">
          {model.requirePhysicalSph ? <div className="mb-3">
            <p className="page-kicker text-[10px]">Single conversion action</p>
            <h2 className="mt-1 text-xl font-bold tracking-tight">
              Validate and convert one handoff
            </h2>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              This handoff requests strict physical SPH on its own declared domains. One domain or many are valid; Converter does not assume a component, colorset, lattice, or core topology.
            </p>
          </div> : null}
        <ConvertForm
          state={model.state}
          inputPath={model.inputPath}
          inputPlaceholder={model.inputPlaceholder}
          canUseSavedPrefix={model.canUseSavedPrefix}
          savedPrefix={model.savedPrefix}
          outputPath={model.displayedOutput}
          format={model.format}
          writerBackend={model.writerBackend}
          pyganStatus={model.pyganStatus}
          check={model.check}
          production={model.production}
          requireKnownMesh={model.requireKnownMesh}
          overwrite={model.overwrite}
          rootName={model.rootName}
          comment={model.comment}
          burnup={model.burnup}
          hFactorDefault={model.hFactorDefault}
          mixturesText={model.mixturesText}
          onInputChange={model.updateInput}
          onFormatChange={model.updateFormat}
          onOutputChange={model.updateOutput}
          onWriterBackendChange={model.setWriterBackend}
          onCheckChange={model.setCheck}
          onProductionChange={model.setProduction}
          onRequireKnownMeshChange={model.setRequireKnownMesh}
          onOverwriteChange={model.setOverwrite}
          onRootNameChange={model.setRootName}
          onCommentChange={model.setComment}
          onBurnupChange={model.setBurnup}
          onHFactorDefaultChange={model.setHFactorDefault}
          onMixturesTextChange={model.setMixturesText}
          onDryRun={() => void model.run("dry-run")}
          onConvert={() => void model.run("convert")}
          requireAppliedRateSph={model.requirePhysicalSph}
        />
        </section> : null}

        {!conversionBlocked ? <section className="mt-6">
          <ConvertReport
            state={model.state}
            mockBackend={model.backendMode === "mock"}
            outputPath={model.displayedOutput}
            onOverwriteRetry={() => void model.retryOverwrite()}
            downstream={model.projectDestination}
          />
          {model.showMinicaseMissingHint ? (
            <ProductionMinicaseMissingHint
              onApply={model.applyProductionMinicaseDemo}
            />
          ) : null}
        </section> : null}

        {!conversionBlocked ? <section className="mt-6 space-y-5" aria-label="Converter reference">
          {model.backendMode === "live" && !model.projectRoot ? (
            <details className="rounded-xl border border-[var(--edge)] bg-black/10 p-3">
              <summary className="cursor-pointer text-[12px] font-semibold text-[var(--fg-2)]">
                Optional reference minicase
              </summary>
              <div className="mt-3">
                <LiveMinicaseCard onApply={model.applyProductionMinicaseDemo} />
              </div>
            </details>
          ) : null}
          <ConvertShowcase
            format={model.format}
            check={model.check}
            production={model.production}
            requireKnownMesh={model.requireKnownMesh}
            outputPath={model.displayedOutput}
            input={model.preflightInput}
            defaultOpen={convertShowcaseDefaultOpen(model.state.kind)}
            sphHref={model.requirePhysicalSph ? sphHref : undefined}
          />
        </section> : null}
      </div>
    </main>
  );
}

function WithdrawnColorsetDiagnostic({
  colorsetId,
  inputPath,
  outputPath,
  strictHref,
}: {
  colorsetId: string | null;
  inputPath: string;
  outputPath: string;
  strictHref: string;
}) {
  return (
    <section
      data-testid="withdrawn-colorset-diagnostic"
      className="rounded-xl border border-amber-300/25 bg-amber-300/[0.055] p-4"
    >
      <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-amber-200">
        WITHDRAWN DIAGNOSTIC ONLY
      </p>
      <h2 className="mt-2 text-lg font-bold">The five-colorset production chain is closed</h2>
      <p className="mt-2 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
        Reusing five center-domain libraries cannot establish a position-resolved
        IRENA full-core equivalence result. This page therefore ignores any
        <code className="mx-1">production=1</code> request and exposes no validation
        or conversion action. Generic component, generic physical-SPH, and native-SPH
        projects remain available without a <code className="mx-1">colorset</code> query.
      </p>
      <dl className="mt-3 grid gap-2 text-[11px] sm:grid-cols-3">
        <DiagnosticValue label="Archived colorset" value={colorsetId ?? "contract-only legacy route"} />
        <DiagnosticValue label="Historical input reference" value={inputPath || "not provided"} />
        <DiagnosticValue label="Historical output reference" value={outputPath || "not provided"} />
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href={strictHref} className="btn btn-primary">Open strict IRENA full-core route</Link>
        <Link href="/convert" className="btn btn-secondary">Start a generic Converter handoff</Link>
      </div>
    </section>
  );
}

function DiagnosticValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <dt className="text-[9px] uppercase tracking-[0.12em] text-[var(--fg-3)]">{label}</dt>
      <dd className="mt-1 break-all font-mono text-[10px] text-[var(--fg-1)]">{value}</dd>
    </div>
  );
}
