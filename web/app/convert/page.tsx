"use client";

import { Suspense } from "react";
import ConvertReport from "@/components/convert/ConvertReport";
import BackendModeCard from "@/components/convert/BackendModeCard";
import ConvertForm from "@/components/convert/ConvertForm";
import ConvertIntentBanner from "@/components/convert/ConvertIntentBanner";
import ConvertShowcase from "@/components/convert/ConvertShowcase";
import LiveMinicaseCard from "@/components/convert/LiveMinicaseCard";
import MockDemoCard from "@/components/convert/MockDemoCard";
import ProductionMinicaseMissingHint from "@/components/convert/ProductionMinicaseMissingHint";
import { convertIntentBannerVisible } from "@/lib/convertIntent";
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

        {convertIntentBannerVisible(model.intent.intent) ? (
          <ConvertIntentBanner intent={model.intent} />
        ) : null}
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
            body="Start or restart the FastAPI backend with openmc2donjon serve; the page will not show live minicase paths until /api/health responds."
          />
        ) : null}

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
            mockBackend={model.backendMode === "mock"}
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
