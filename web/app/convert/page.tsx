"use client";

import { Suspense } from "react";
import ConvertReport from "@/components/convert/ConvertReport";
import BackendModeCard from "@/components/convert/BackendModeCard";
import ConvertForm from "@/components/convert/ConvertForm";
import ConvertIntentBanner from "@/components/convert/ConvertIntentBanner";
import ConvertPrimer from "@/components/convert/ConvertPrimer";
import ConvertShowcase from "@/components/convert/ConvertShowcase";
import LiveMinicaseCard from "@/components/convert/LiveMinicaseCard";
import MockDemoCard from "@/components/convert/MockDemoCard";
import ProductionMinicaseMissingHint from "@/components/convert/ProductionMinicaseMissingHint";
import { convertShowcaseDefaultOpen } from "@/lib/convertShowcase";
import { useConvertPageState } from "@/lib/useConvertPageState";

export default function ConvertPage() {
  return (
    <Suspense fallback={<ConvertLoading />}>
      <ConvertPageContent />
    </Suspense>
  );
}

function ConvertLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading converter…
        </section>
      </div>
    </main>
  );
}

function ConvertPageContent() {
  const model = useConvertPageState();

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="grad-text">Direct converter</span>
          </h1>
          <p className="mt-2 text-sm text-[var(--fg-2)]">
            Turn an existing OpenMC MGXS HDF5 into DONJON-readable ASCII.
            OpenMC-side SPH or ADF should already be present in the handoff
            before this page writes the final library.
          </p>
        </header>

        <ConvertIntentBanner intent={model.intent} />
        {model.backendMode === "checking" ? (
          <BackendModeCard
            tone="loading"
            title="Checking backend mode"
            body="The web UI is asking the FastAPI backend whether this is mock mode or live filesystem mode before showing demo paths."
          />
        ) : model.backendMode === "mock" ? (
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
            body="Start or restart the FastAPI backend with `openmc2donjon serve`; the page will not show live minicase paths until `/api/health` responds."
          />
        ) : null}

        <ConverterFirstSteps />

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
        />

        <section className="mt-6">
          <ConvertReport
            state={model.state}
            onConvert={() => void model.run("convert")}
            draftInputPath={model.inputPath}
            draftOutputPath={model.displayedOutput}
            format={model.format}
          />
          {model.showMinicaseMissingHint ? (
            <ProductionMinicaseMissingHint
              onApply={model.applyProductionMinicaseDemo}
            />
          ) : null}
        </section>

        <section className="mt-6 space-y-5" aria-label="Converter reference">
          {model.backendMode === "live" ? (
            <LiveMinicaseCard onApply={model.applyProductionMinicaseDemo} />
          ) : null}
          <ConvertPrimer
            state={model.state}
            inputPath={model.inputPath}
            outputPath={model.displayedOutput}
            format={model.format}
          />
          <ConvertShowcase
            format={model.format}
            check={model.check}
            production={model.production}
            requireKnownMesh={model.requireKnownMesh}
            outputPath={model.displayedOutput}
            input={model.preflightInput}
            defaultOpen={convertShowcaseDefaultOpen(model.state.kind)}
          />
        </section>
      </div>
    </main>
  );
}

function ConverterFirstSteps() {
  const steps = [
    {
      label: "1",
      title: "Pick HDF5",
      body: "Use an OpenMC MGXS handoff. If SPH is required, inject the SPH sidecar before converting.",
    },
    {
      label: "2",
      title: "Dry-run",
      body: "Run production checks without writing. Fix contract or physics-gate issues here.",
    },
    {
      label: "3",
      title: "Convert",
      body: "Write .mcompo.txt or .macrolib.txt with the default ASCII writer, or optional PyGan.",
    },
    {
      label: "4",
      title: "Preview / bundle",
      body: "Inspect the ASCII output and package the handoff for DONJON consumption.",
    },
  ] as const;

  return (
    <section className="mb-5 rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
            User path
          </p>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            One file in, one DONJON library out
          </h2>
        </div>
        <div className="rounded-full border border-[var(--edge)] px-3 py-1 text-[11px] text-[var(--fg-2)]">
          dry-run before write
        </div>
      </div>
      <ol className="mt-4 grid gap-2 md:grid-cols-4">
        {steps.map((step) => (
          <li
            key={step.label}
            className="rounded-lg border border-[var(--edge)] bg-white/[0.02] p-3"
          >
            <div className="flex items-center gap-2">
              <span className="tab-num rounded border border-current/25 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--accent)]">
                {step.label}
              </span>
              <h3 className="text-sm font-semibold tracking-tight">
                {step.title}
              </h3>
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
              {step.body}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
