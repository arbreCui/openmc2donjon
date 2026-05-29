"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import {
  convertArtifactPaths,
  convertArtifactStatusSummary,
  fetchConvertArtifactStatuses,
  loadingConvertArtifactStatuses,
  type ConvertArtifactStatusMap,
} from "@/lib/convertArtifactStatus";
import {
  convertDeliveryChecklist,
  type ConvertDeliveryItem,
} from "@/lib/convertDeliveryChecklist";
import { convertBlockedGuidance } from "@/lib/convertBlockedGuidance";
import {
  convertBundleHref,
  convertDonjonGuideHref,
  convertBundleManifestPath,
  convertBundleOutputDir,
  convertValidateBundleHref,
  convertWriterCompareHref,
} from "@/lib/convertNextSteps";
import { convertOutputMode } from "@/lib/convertOutputMode";
import { convertPostWriteFocus } from "@/lib/convertPostWriteFocus";
import {
  fileStatusIsDirectory,
  fileStatusIsFile,
  fileStatusLabel,
  fileStatusTone,
  type FileStatusState,
} from "@/lib/fileStatus";
import AsciiReadinessPanel from "./AsciiReadinessPanel";
import BundleManifestProbe from "./BundleManifestProbe";
import RunSummaryCard from "./RunSummaryCard";

export default function OutputActions({
  data,
  onConvert,
}: {
  data: ConvertResponse;
  onConvert?: () => void;
}) {
  const paths = useMemo(() => convertArtifactPaths(data), [data]);
  const [statuses, setStatuses] = useState<ConvertArtifactStatusMap>(
    loadingConvertArtifactStatuses,
  );
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatuses(loadingConvertArtifactStatuses());
    fetchConvertArtifactStatuses(paths).then((next) => {
      if (cancelled) return;
      setStatuses(next);
    });
    return () => {
      cancelled = true;
    };
  }, [paths, refreshToken]);

  const notice = outputNotice(data);
  const input = data.preflight?.inputs[0] ?? null;
  const canConvertNow = data.dry_run && data.ok && !data.output_exists && onConvert;
  const pathLabel =
    data.converted && data.output_exists ? "Copy DONJON path" : "Copy target path";
  const actions = handoffActions(data, onConvert, statuses);
  const deliveryItems = convertDeliveryChecklist(data, input);
  const mode = convertOutputMode(data);

  if (mode === "dry-run-ready") {
    return (
      <DryRunOutputActions
        data={data}
        input={input}
        statuses={statuses}
        deliveryItems={deliveryItems}
        onConvert={onConvert}
        onRefresh={() => setRefreshToken((value) => value + 1)}
      />
    );
  }

  if (mode === "converted") {
    return (
      <ConvertedOutputActions
        data={data}
        input={input}
        statuses={statuses}
        deliveryItems={deliveryItems}
        actions={actions}
        onRefresh={() => setRefreshToken((value) => value + 1)}
      />
    );
  }

  if (mode === "blocked") {
    return (
      <BlockedOutputActions
        data={data}
        input={input}
        statuses={statuses}
        deliveryItems={deliveryItems}
        actions={actions}
        onRefresh={() => setRefreshToken((value) => value + 1)}
      />
    );
  }

  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight">
            Artifacts & next actions
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Use this section to inspect the source evidence, create or preview
            the ASCII artifact, and package the handoff for delivery.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {data.converted ? "artifact ready" : data.dry_run ? "dry run" : "stopped"}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[var(--fg-3)]">
        <span>{convertArtifactStatusSummary(statuses)}</span>
        <button
          type="button"
          onClick={() => setRefreshToken((value) => value + 1)}
          className="text-[var(--accent-2)] hover:underline"
        >
          Refresh file status
        </button>
      </div>

      <DeliveryPathStrip items={deliveryItems} onConvert={onConvert} />

      <AsciiReadinessPanel data={data} outputStatus={statuses.output} />
      <DeliveryCommandPanel data={data} statuses={statuses} onConvert={onConvert} />

      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        {actions.map((action) => (
          <ActionCard key={action.id} action={action} />
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {canConvertNow ? (
          <button type="button" onClick={onConvert} className="btn btn-primary">
            Convert now
          </button>
        ) : null}
        <CopyCliButton
          value={data.output_path}
          label={pathLabel}
          ariaLabel={pathLabel}
        />
        <CopyCliButton
          value={data.cli_command_text}
          label="Copy CLI"
          ariaLabel="Copy CLI command"
        />
      </div>

      <div
        className={
          "mt-3 rounded-md border px-3 py-2 text-sm " + outputNoticeClass(notice.tone)
        }
      >
        <span className="font-semibold">{notice.title}</span>
        <span className="ml-2 text-[var(--fg-1)]">{notice.body}</span>
      </div>

      <RunSummaryCard data={data} input={input} statuses={statuses} />
    </section>
  );
}

function BlockedOutputActions({
  data,
  input,
  statuses,
  deliveryItems,
  actions,
  onRefresh,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  statuses: ConvertArtifactStatusMap;
  deliveryItems: readonly ConvertDeliveryItem[];
  actions: readonly HandoffAction[];
  onRefresh: () => void;
}) {
  const guidance = convertBlockedGuidance(data, input);
  const cardClass =
    guidance.tone === "fail"
      ? "border-rose-300/25 bg-rose-300/[0.07] text-rose-100"
      : "border-amber-300/25 bg-amber-300/[0.07] text-amber-100";
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight">
            Conversion needs attention
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Preview and bundle stay locked until the request reaches a confirmed
            ASCII handoff state.
          </p>
        </div>
        <span
          className={
            "rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-wider " +
            (guidance.tone === "fail"
              ? "border-rose-300/25 text-rose-200"
              : "border-amber-300/25 text-amber-200")
          }
        >
          {guidance.badge}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[var(--fg-3)]">
        <span>{convertArtifactStatusSummary(statuses)}</span>
        <button
          type="button"
          onClick={onRefresh}
          className="text-[var(--accent-2)] hover:underline"
        >
          Refresh file status
        </button>
      </div>

      <section className={"mt-4 rounded-lg border p-4 " + cardClass}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
              first fix
            </div>
            <h4 className="mt-1 text-sm font-semibold tracking-tight">
              {guidance.title}
            </h4>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-1)]">
              {guidance.body}
            </p>
          </div>
        </div>

        <div className="mt-3 rounded border border-current/15 bg-black/15 px-3 py-2 text-[12px] leading-5">
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            recommended next step
          </div>
          <div className="mt-1 text-[var(--fg-1)]">{guidance.primaryFix}</div>
        </div>

        <ul className="mt-3 grid gap-1.5 text-[12px] leading-5 text-[var(--fg-1)] md:grid-cols-2">
          {guidance.facts.map((fact) => (
            <li key={fact} className="flex gap-2">
              <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
              <span>{fact}</span>
            </li>
          ))}
        </ul>

        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            href={`/inspect?path=${encodeURIComponent(data.input_path)}`}
            className="btn btn-primary"
          >
            Inspect HDF5
          </Link>
          <CopyCliButton
            value={data.cli_command_text}
            label="Copy CLI"
            ariaLabel="Copy CLI command"
          />
          <CopyCliButton
            value={data.output_path}
            label="Copy target path"
            ariaLabel="Copy target path"
          />
        </div>
      </section>

      <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer select-none text-sm font-semibold tracking-tight text-[var(--fg-0)]">
          Technical evidence
        </summary>
        <DeliveryPathStrip items={deliveryItems} />
        <AsciiReadinessPanel data={data} outputStatus={statuses.output} />
        <DeliveryCommandPanel data={data} statuses={statuses} />
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {actions.map((action) => (
            <ActionCard key={action.id} action={action} />
          ))}
        </div>
        <RunSummaryCard data={data} input={input} statuses={statuses} />
      </details>
    </section>
  );
}

function ConvertedOutputActions({
  data,
  input,
  statuses,
  deliveryItems,
  actions,
  onRefresh,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  statuses: ConvertArtifactStatusMap;
  deliveryItems: readonly ConvertDeliveryItem[];
  actions: readonly HandoffAction[];
  onRefresh: () => void;
}) {
  const bundleDir = convertBundleOutputDir(data);
  const manifestPath = convertBundleManifestPath(data);
  const focus = convertPostWriteFocus(data);
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight">
            Output ready
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            The DONJON-facing ASCII handoff exists. Review the text, bundle the
            delivery record, or prepare the downstream DONJON input.
          </p>
        </div>
        <span className="rounded border border-emerald-300/25 px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-emerald-200">
          artifact ready
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[var(--fg-3)]">
        <span>{convertArtifactStatusSummary(statuses)}</span>
        <button
          type="button"
          onClick={onRefresh}
          className="text-[var(--accent-2)] hover:underline"
        >
          Refresh file status
        </button>
      </div>

      <section className="mt-4 rounded-lg border border-emerald-300/20 bg-emerald-300/[0.055] p-4 text-emerald-100">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
              DONJON ASCII
            </div>
            <h4 className="mt-1 text-sm font-semibold tracking-tight">
              Preview, bundle, then use in DONJON
            </h4>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              The converter has done its job. The next useful checks are the
              ASCII preview and the manifest-backed bundle.
            </p>
          </div>
          {focus ? (
            <span className="rounded border border-current/20 bg-black/15 px-2 py-1 text-[11px] uppercase tracking-wider">
              {focus.badge}
            </span>
          ) : null}
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <DeliveryPath label="ASCII handoff" value={data.output_path} />
          <DeliveryPath label="Bundle directory" value={bundleDir} />
          {data.summary_written && data.summary_path ? (
            <DeliveryPath label="Conversion summary" value={data.summary_path} />
          ) : null}
          <DeliveryPath label="Manifest after bundle" value={manifestPath} />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <a href="#ascii-output-preview" className="btn btn-primary">
            Preview ASCII
          </a>
          <Link href={convertBundleHref(data)} className="btn btn-secondary">
            Bundle handoff
          </Link>
          <Link href={convertDonjonGuideHref(data)} className="btn btn-secondary">
            DONJON guide
          </Link>
          {data.writer_backend === "pygan" ? (
            <Link href={convertWriterCompareHref(data)} className="btn btn-secondary">
              Validate PyGan
            </Link>
          ) : null}
          <Link
            href={`/inspect?path=${encodeURIComponent(data.input_path)}`}
            className="btn btn-secondary"
          >
            Inspect source
          </Link>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <CopyCliButton
            value={data.output_path}
            label="Copy DONJON path"
            ariaLabel="Copy DONJON path"
          />
          <CopyCliButton
            value={data.cli_command_text}
            label="Copy CLI"
            ariaLabel="Copy CLI command"
          />
        </div>
      </section>

      <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer select-none text-sm font-semibold tracking-tight text-[var(--fg-0)]">
          Advanced delivery evidence
        </summary>
        <DeliveryPathStrip items={deliveryItems} />
        <AsciiReadinessPanel data={data} outputStatus={statuses.output} />
        <DeliveryCommandPanel data={data} statuses={statuses} />
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {actions.map((action) => (
            <ActionCard key={action.id} action={action} />
          ))}
        </div>
        <BundleManifestProbe manifestPath={manifestPath} enabled />
        <RunSummaryCard data={data} input={input} statuses={statuses} />
      </details>
    </section>
  );
}

function DryRunOutputActions({
  data,
  input,
  statuses,
  deliveryItems,
  onConvert,
  onRefresh,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  statuses: ConvertArtifactStatusMap;
  deliveryItems: readonly ConvertDeliveryItem[];
  onConvert?: () => void;
  onRefresh: () => void;
}) {
  return (
    <section className="glass rounded-xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight">
            Dry-run next step
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Dry-run accepted the request and no ASCII file was written. Convert
            is the only main action left before preview or bundle become
            relevant.
          </p>
        </div>
        <span className="rounded border border-cyan-300/25 px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-cyan-200">
          no file written
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-[12px] text-[var(--fg-3)]">
        <span>{convertArtifactStatusSummary(statuses)}</span>
        <button
          type="button"
          onClick={onRefresh}
          className="text-[var(--accent-2)] hover:underline"
        >
          Refresh file status
        </button>
      </div>

      <section className="mt-4 rounded-lg border border-cyan-300/25 bg-cyan-300/[0.06] p-4 text-cyan-100">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
              write target
            </div>
            <h4 className="mt-1 text-sm font-semibold tracking-tight">
              Convert will create the DONJON ASCII handoff
            </h4>
            <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
              The target path is ready for the selected format. After Convert,
              this page will expose ASCII preview, bundle, manifest validation,
              and DONJON guide actions.
            </p>
          </div>
          {onConvert ? (
            <button type="button" onClick={onConvert} className="btn btn-primary">
              Convert now
            </button>
          ) : null}
        </div>
        <div className="mt-3 rounded border border-current/15 bg-black/15 px-3 py-2">
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            target path
          </div>
          <div className="mt-1 break-all font-mono text-[12px] text-[var(--fg-1)]">
            {data.output_path}
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <CopyCliButton
            value={data.output_path}
            label="Copy target path"
            ariaLabel="Copy target path"
          />
          <CopyCliButton
            value={data.cli_command_text}
            label="Copy dry-run CLI"
            ariaLabel="Copy dry-run CLI command"
          />
          <Link
            href={`/inspect?path=${encodeURIComponent(data.input_path)}`}
            className="btn btn-secondary"
          >
            Inspect source
          </Link>
        </div>
      </section>

      <details className="mt-3 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
        <summary className="cursor-pointer select-none text-sm font-semibold tracking-tight text-[var(--fg-0)]">
          Advanced dry-run evidence
        </summary>
        <DeliveryPathStrip items={deliveryItems} onConvert={onConvert} />
        <AsciiReadinessPanel data={data} outputStatus={statuses.output} />
        <RunSummaryCard data={data} input={input} statuses={statuses} />
      </details>
    </section>
  );
}

function DeliveryCommandPanel({
  data,
  statuses,
  onConvert,
}: {
  data: ConvertResponse;
  statuses: ConvertArtifactStatusMap;
  onConvert?: () => void;
}) {
  const outputKnownMissing =
    statuses.output.kind === "ok" && !fileStatusIsFile(statuses.output);
  const outputReady = data.converted && data.output_exists && !outputKnownMissing;
  const canConvertNow = data.dry_run && data.ok && !data.output_exists && onConvert;
  const bundleDir = convertBundleOutputDir(data);
  const manifestPath = convertBundleManifestPath(data);
  const bundleDirReady = fileStatusIsDirectory(statuses.bundle);
  return (
    <section
      className={
        "mt-3 rounded-lg border p-3 " +
        (outputReady
          ? "border-emerald-300/20 bg-emerald-300/[0.055] text-emerald-100"
          : canConvertNow
            ? "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100"
            : "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]")
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            delivery command chain
          </div>
          <h4 className="mt-1 text-sm font-semibold tracking-tight">
            {outputReady
              ? "Preview, bundle, then validate the manifest"
              : canConvertNow
                ? "Convert unlocks preview and bundle delivery"
                : "Delivery waits for a confirmed ASCII file"}
          </h4>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            {outputReady
              ? "The web converter wrote the ASCII handoff. The next local command should collect the HDF5 and ASCII file into a manifest-backed bundle, then validate that manifest."
              : canConvertNow
                ? "The dry run accepted this handoff. Run Convert to write the ASCII file, then this panel will expose the bundle and validation builders."
                : "Run a successful conversion before packaging the handoff for another workflow or collaborator."}
          </p>
        </div>
        {outputReady ? (
          <span className="rounded border border-current/20 bg-black/15 px-2 py-1 text-[11px] uppercase tracking-wider">
            {bundleDirReady ? "bundle dir exists" : "bundle dir target"}
          </span>
        ) : null}
      </div>

      {outputReady ? (
        <>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <DeliveryPath label="Bundle directory" value={bundleDir} />
            <DeliveryPath label="Manifest after bundle" value={manifestPath} />
            {data.summary_written && data.summary_path ? (
              <DeliveryPath label="Conversion summary" value={data.summary_path} />
            ) : null}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <a href="#ascii-output-preview" className="btn btn-primary">
              Preview ASCII
            </a>
            {data.writer_backend === "pygan" ? (
              <Link href={convertWriterCompareHref(data)} className="btn btn-secondary">
                Validate PyGan writer
              </Link>
            ) : null}
            <Link href={convertBundleHref(data)} className="btn btn-secondary">
              Open bundle builder
            </Link>
            <Link href={convertValidateBundleHref(data)} className="btn btn-secondary">
              Prepare validation command
            </Link>
            <Link href={convertDonjonGuideHref(data)} className="btn btn-secondary">
              Open DONJON guide
            </Link>
          </div>
          <BundleManifestProbe manifestPath={manifestPath} enabled={outputReady} />
        </>
      ) : canConvertNow ? (
        <button type="button" onClick={onConvert} className="mt-3 btn btn-primary">
          Convert now
        </button>
      ) : null}
    </section>
  );
}

function DeliveryPath({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-current/15 bg-black/15 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
        {label}
      </div>
      <div className="mt-1 break-all font-mono text-[12px] text-[var(--fg-1)]">
        {value}
      </div>
    </div>
  );
}

function DeliveryPathStrip({
  items,
  onConvert,
}: {
  items: readonly ConvertDeliveryItem[];
  onConvert?: () => void;
}) {
  return (
    <div className="mt-4 rounded-lg border border-[var(--edge)] bg-black/15 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold tracking-tight">
            Handoff path after this result
          </h4>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            Follow this row left to right: source evidence, gates, ASCII write,
            preview, then bundle.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          delivery route
        </span>
      </div>
      <ol className="mt-3 grid gap-2 md:grid-cols-5">
        {items.map((item, index) => (
          <li key={item.id} className={"rounded-md border px-3 py-2 " + deliveryItemClass(item.status)}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[11px] opacity-70">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
                {item.status}
              </span>
            </div>
            <h5 className="mt-2 text-[12px] font-semibold tracking-tight">
              {item.title}
            </h5>
            <p className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
              {item.body}
            </p>
            <DeliveryItemAction item={item} onConvert={onConvert} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function DeliveryItemAction({
  item,
  onConvert,
}: {
  item: ConvertDeliveryItem;
  onConvert?: () => void;
}) {
  if (item.action === "convert" && item.status === "ready" && onConvert) {
    return (
      <button
        type="button"
        onClick={onConvert}
        className="mt-2 text-[11px] font-medium text-[var(--accent-2)] hover:underline"
      >
        Convert now
      </button>
    );
  }
  if (!item.href) return null;
  if (item.href.startsWith("#")) {
    return (
      <a href={item.href} className="mt-2 inline-flex text-[11px] font-medium text-[var(--accent-2)] hover:underline">
        Jump there
      </a>
    );
  }
  return (
    <Link href={item.href} className="mt-2 inline-flex text-[11px] font-medium text-[var(--accent-2)] hover:underline">
      Open
    </Link>
  );
}

interface HandoffAction {
  id: string;
  label: string;
  title: string;
  body: string;
  href?: string;
  disabled?: boolean;
  status: "ready" | "reference" | "blocked";
  fileStatus?: FileStatusState;
  fileStatusLabel?: string;
}

function handoffActions(
  data: ConvertResponse,
  onConvert?: () => void,
  statuses?: ConvertArtifactStatusMap,
): HandoffAction[] {
  const inputKnownMissing =
    statuses?.input.kind === "ok" && !fileStatusIsFile(statuses.input);
  const inputReady = !inputKnownMissing;
  const outputKnownMissing =
    statuses?.output.kind === "ok" && !fileStatusIsFile(statuses.output);
  const outputReady = data.converted && data.output_exists && !outputKnownMissing;
  const bundleDirReady = fileStatusIsDirectory(statuses?.bundle);
  const canConvertNow = data.dry_run && data.ok && !data.output_exists && onConvert;
  const inspect: HandoffAction = {
    id: "inspect",
    label: "Evidence",
    title: inputReady ? "Inspect input HDF5" : "Inspect source path",
    body: inputReady
      ? "Open mixture roster, energy mesh identity, ADF/SPH metadata, and production warnings."
      : "The source path is not confirmed right now; opening the inspector may return a path error.",
    href: `/inspect?path=${encodeURIComponent(data.input_path)}`,
    status: inputReady ? "reference" : "blocked",
    fileStatus: statuses?.input,
    fileStatusLabel: "input",
  };
  const preview: HandoffAction = {
    id: "preview",
    label: "ASCII",
    title: outputReady ? "Preview ASCII blocks" : "Preview waits for output",
    body: outputReady
      ? "Jump to the LCM ASCII signature, visible block tree, and first lines."
      : canConvertNow
        ? "Dry run passed. Convert writes the ASCII file before preview is available."
        : "The output file was not confirmed, so the preview cannot be opened yet.",
    href: outputReady ? "#ascii-output-preview" : undefined,
    disabled: !outputReady,
    status: outputReady ? "ready" : "blocked",
    fileStatus: statuses?.output,
    fileStatusLabel: "output",
  };
  const bundle: HandoffAction = {
    id: "bundle",
    label: bundleDirReady ? "Bundle" : "Bundle target",
    title: outputReady ? "Bundle handoff" : "Bundle after convert",
    body: outputReady
      ? bundleDirReady
        ? "Open the bundle builder with MGXS and ASCII paths filled; an existing bundle directory is present."
        : "Open the bundle builder with MGXS and ASCII paths filled; it will create or update the bundle directory."
      : "Package the input, ASCII output, summaries, and logs after conversion succeeds.",
    href: outputReady ? convertBundleHref(data) : undefined,
    disabled: !outputReady,
    status: outputReady ? "ready" : "blocked",
    fileStatus: statuses?.bundle,
    fileStatusLabel: "bundle dir",
  };
  const compare: HandoffAction = {
    id: "compare-writers",
    label: "PyGan",
    title: outputReady ? "Validate PyGan writer" : "Validate after convert",
    body: outputReady
      ? "Open a command builder that regenerates this handoff with ASCII and PyGan, then compares their LCM trees semantically."
      : "PyGan writer validation is available once the converted handoff is confirmed.",
    href: outputReady ? convertWriterCompareHref(data) : undefined,
    disabled: !outputReady,
    status: outputReady ? "ready" : "blocked",
  };
  const guide: HandoffAction = {
    id: "guide",
    label: "Command",
    title: "Open command guide",
    body: "Review when to use direct conversion, what it writes, and where it sits in the workflow map.",
    href: "/commands/direct-convert",
    status: "reference",
  };
  if (outputReady) {
    return data.writer_backend === "pygan"
      ? [preview, compare, bundle, inspect, guide]
      : [preview, bundle, inspect, guide];
  }
  return data.writer_backend === "pygan"
    ? [inspect, preview, compare, bundle, guide]
    : [inspect, preview, bundle, guide];
}

function ActionCard({ action }: { action: HandoffAction }) {
  return (
    <article className={"rounded-md border p-3 " + actionCardClass(action.status)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
          {action.label}
        </span>
        {action.fileStatus ? (
          <ActionFileStatusBadge
            state={action.fileStatus}
            label={action.fileStatusLabel}
          />
        ) : null}
        {action.disabled || !action.href ? (
          <span className="text-[11px] text-[var(--fg-3)]">waiting</span>
        ) : (
          <ActionLink href={action.href} />
        )}
      </div>
      <h4 className="mt-2 text-sm font-semibold tracking-tight">{action.title}</h4>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
        {action.body}
      </p>
    </article>
  );
}

function ActionFileStatusBadge({
  state,
  label,
}: {
  state: FileStatusState;
  label?: string;
}) {
  if (state.kind === "loading") {
    return (
      <span className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        checking
      </span>
    );
  }
  if (state.kind === "error") {
    return (
      <span
        className="rounded border border-amber-300/25 bg-amber-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-amber-200"
        title={state.message}
      >
        {label ? `${label}: unknown` : "unknown"}
      </span>
    );
  }

  const tone = fileStatusTone(state.status);
  const statusLabel = label
    ? `${label}: ${fileStatusLabel(state.status)}`
    : fileStatusLabel(state.status);
  if (tone === "ready") {
    return (
      <span className="rounded border border-emerald-300/25 bg-emerald-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-emerald-200">
        {statusLabel}
      </span>
    );
  }
  if (tone === "missing") {
    return (
      <span
        className="rounded border border-rose-300/25 bg-rose-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-rose-200"
        title={state.status.detail ?? undefined}
      >
        {statusLabel}
      </span>
    );
  }
  return (
    <span
      className="rounded border border-amber-300/25 bg-amber-300/[0.08] px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em] text-amber-200"
      title={state.status.detail ?? undefined}
    >
      {statusLabel}
    </span>
  );
}

function ActionLink({ href }: { href: string }) {
  if (href.startsWith("#")) {
    return (
      <a href={href} className="text-[11px] text-[var(--accent-2)] hover:underline">
        jump
      </a>
    );
  }
  return (
    <Link href={href} className="text-[11px] text-[var(--accent-2)] hover:underline">
      open
    </Link>
  );
}

function actionCardClass(status: HandoffAction["status"]): string {
  if (status === "ready") {
    return "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-100";
  }
  if (status === "blocked") {
    return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  }
  return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-100";
}

function deliveryItemClass(
  status: "done" | "ready" | "blocked" | "pending" | "skipped",
): string {
  if (status === "done") {
    return "border-emerald-400/20 bg-emerald-400/[0.05] text-emerald-100";
  }
  if (status === "ready") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  if (status === "skipped") {
    return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}

function outputNotice(data: ConvertResponse): {
  tone: "pass" | "warn" | "fail" | "neutral";
  title: string;
  body: string;
} {
  if (data.converted) {
    return {
      tone: "pass",
      title: "Output file written.",
      body: "Review the ASCII preview, then pass this path to the DONJON-side workflow.",
    };
  }
  if (!data.dry_run) {
    return {
      tone: "fail",
      title: "No output file written.",
      body: "Fix the failing checks or request error, then run Convert again.",
    };
  }
  if (data.output_exists) {
    return {
      tone: "warn",
      title: "Dry run only; target already exists.",
      body: "Enable Overwrite output before converting if this file should be replaced.",
    };
  }
  return {
    tone: "neutral",
    title: "Dry run only; no file written.",
    body: "The target path is clear, so Convert will write the ASCII file there.",
  };
}

function outputNoticeClass(tone: "pass" | "warn" | "fail" | "neutral") {
  if (tone === "pass") {
    return "border-emerald-400/25 bg-emerald-400/10 text-emerald-200";
  }
  if (tone === "warn") {
    return "border-amber-400/25 bg-amber-400/10 text-amber-200";
  }
  if (tone === "fail") {
    return "border-rose-400/25 bg-rose-400/10 text-rose-200";
  }
  return "border-[var(--edge)] bg-white/[0.03] text-[var(--fg-2)]";
}
