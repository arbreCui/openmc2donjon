import Link from "next/link";
import type { ReactNode } from "react";
import {
  HandoffAttrValue,
  HandoffInspection,
  HandoffRootAttr,
  TopLevelEntry,
} from "@/lib/api";
import {
  inspectConvertHref,
  inspectDiffHref,
  inspectProductionStats,
  type InspectProductionStat,
} from "@/lib/inspectSummary";
import { formatEnergy } from "./formatEnergy";
import OpenmcProvenanceCard from "@/components/OpenmcProvenanceCard";

export default function Summary({ data }: { data: HandoffInspection }) {
  const production = inspectProductionStats(data);
  const isMgxsHandoff = data.ok;
  return (
    <div className="glass rounded-xl p-5">
      {data.mock_mode === true ? (
        <div className="mb-4 rounded-md border border-amber-300/30 bg-amber-300/[0.08] p-3 text-[12px] text-amber-100">
          <strong className="block uppercase tracking-[0.12em]">
            Demonstration fixture — not the requested file
          </strong>
          <span className="mt-1 block text-amber-100/80">
            This backend is in mock mode. The values below come from the bundled
            fixture; the path is shown only to preview the interface.
          </span>
        </div>
      ) : null}
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-[12px] uppercase tracking-wider text-[var(--fg-3)]">
            Path
          </div>
          <div className="font-mono text-sm break-all">{data.path}</div>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <ReadableHdf5Badge isMgxsHandoff={isMgxsHandoff} />
        </div>
      </div>

      {isMgxsHandoff ? (
        <dl className="mt-5 grid grid-cols-2 gap-4 text-sm tab-num sm:grid-cols-5">
          <Stat label="Mixtures" value={data.mixture_count} />
          <Stat label="Energy groups" value={data.energy_groups ?? "—"} />
          <Stat
            label="Legendre"
            value={
              data.legendre_order == null ? "—" : `P${data.legendre_order}`
            }
          />
          <Stat
            label="State points"
            value={data.state_points ?? data.calculation_count}
          />
          <Stat
            label="Fissionable"
            value={`${data.fissionable_mixtures} / ${data.mixture_count}`}
          />
          <Stat
            label="ADF mixtures"
            value={`${data.adf_mixtures} / ${data.mixture_count}`}
          />
          <Stat
            label="SPH"
            value={data.sph_applied ? "applied" : data.sph_calculations}
            tone={
              data.sph_applied || data.sph_calculations > 0
                ? "pass"
                : undefined
            }
            detail={
              data.sph_applied
                ? `Cross sections already corrected${data.sph_kind ? ` · ${data.sph_kind}` : ""}.`
                : undefined
            }
          />
          <Stat
            label="Scatter"
            value={data.scatter_shapes.length > 0 ? "available" : "—"}
          />
        </dl>
      ) : (
        <p className="mt-4 rounded-md border border-sky-300/20 bg-sky-300/[0.05] p-3 text-[12px] leading-5 text-sky-100">
          The file is readable HDF5, but it does not match the
          openmc2donjon MGXS handoff schema. Its root metadata and structure are
          shown below; this is not a file-read failure.
        </p>
      )}

      {isMgxsHandoff ? (
        <div className="mt-5 grid grid-cols-1 gap-4 text-[13px] tab-num sm:grid-cols-2">
          <DetailRow
            label="Energy range"
            value={
              data.energy_min != null && data.energy_max != null
                ? `${formatEnergy(data.energy_min)} — ${formatEnergy(
                    data.energy_max,
                  )}`
                : "—"
            }
          />
          <DetailRow
            label="Bounds shape"
            value={
              data.energy_bounds_shape
                ? `[${data.energy_bounds_shape.join(", ")}]`
                : "—"
            }
          />
          <DetailRow
            label="ADF faces"
            value={data.adf_faces.length ? data.adf_faces.join(", ") : "—"}
          />
          <DetailRow
            label="Scatter axes"
            value={
              data.scatter_axes.length ? data.scatter_axes.join(", ") : "—"
            }
          />
        </div>
      ) : null}

      {data.openmc_provenance ? (
        <div className="mt-5">
          <OpenmcProvenanceCard provenance={data.openmc_provenance} />
        </div>
      ) : null}

      {data.issues.length > 0 ? (
        <div className="mt-5 text-[13px]">
          <div className="text-amber-300 font-semibold mb-1">
            {isMgxsHandoff ? "Inspection notes" : "MGXS contract notes"} (
            {data.issues.length})
          </div>
          <ul className="list-disc pl-5 space-y-0.5 text-[var(--fg-1)]">
            {data.issues.map((issue, index) => (
              <li key={index}>{issue}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {data.root_attrs.length > 0 || data.top_level_keys.length > 0 ? (
        <FilePeek
          rootAttrs={data.root_attrs}
          topLevelKeys={data.top_level_keys}
          rootAttrsTotal={data.root_attrs_total}
          topLevelKeysTotal={data.top_level_keys_total}
          peekTruncated={data.peek_truncated}
          mixtureCount={data.mixture_count}
          ok={data.ok}
        />
      ) : null}

      {isMgxsHandoff ? (
        <details className="mt-5 border-t border-[var(--edge)] pt-4 text-[13px]">
          <summary className="cursor-pointer select-none text-[var(--fg-2)] hover:text-[var(--fg-0)]">
            Optional: Converter readiness and next steps
          </summary>
          <p className="mt-2 text-[12px] leading-5 text-[var(--fg-3)]">
            These checks matter only if you later choose to convert this file.
            They do not affect read-only visualization.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <ReadinessStat label="Energy mesh" stat={production.mesh}>
              <MeshBadge match={data.mesh_match} hint={production.mesh} />
            </ReadinessStat>
            <ReadinessStat
              label="Transport total"
              stat={production.transport}
            />
            <ReadinessStat label="H-factor" stat={production.hFactor} />
            <ReadinessStat label="std_dev" stat={production.stdDev} />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Link
              href={inspectConvertHref(
                data.path,
                data.sph_calculations,
                data.sph_applied,
              )}
              className="btn btn-secondary"
            >
              Open in Converter
            </Link>
            <Link
              href={inspectDiffHref(data.path)}
              className="text-[12px] text-[var(--accent-2)] hover:underline"
            >
              Diff against a reference
            </Link>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function FilePeek({
  rootAttrs,
  topLevelKeys,
  rootAttrsTotal,
  topLevelKeysTotal,
  peekTruncated,
  mixtureCount,
  ok,
}: {
  rootAttrs: HandoffRootAttr[];
  topLevelKeys: TopLevelEntry[];
  rootAttrsTotal: number;
  topLevelKeysTotal: number;
  peekTruncated: boolean;
  mixtureCount: number;
  ok: boolean;
}) {
  // For non-handoff HDF5 files the headline summary numbers go to
  // zero, but the peek still has signal - lead with a short note that
  // names this state so the user isn't left thinking "OK, FAIL,
  // zero mixtures, now what".
  const isNotHandoff = !ok && mixtureCount === 0;
  return (
    <details className="mt-5 text-[13px]" open={isNotHandoff}>
      <summary className="cursor-pointer text-[var(--fg-2)] hover:text-[var(--fg-0)] select-none">
        What&apos;s in this file?
      </summary>
      {isNotHandoff ? (
        <p className="mt-2 text-[12px] text-[var(--fg-3)] leading-relaxed">
          This HDF5 doesn&apos;t look like an MGXS handoff. The
          attributes and top-level groups below are usually enough to
          identify it (an OpenMC tally export, an ADF sidecar — a small
          companion HDF5 carrying ADF/DF or SPH factors — a low-order
          driver, …).
        </p>
      ) : null}
      {peekTruncated ? (
        <p className="mt-2 text-[12px] text-amber-300">
          Showing a capped slice of this file; the full counts are
          listed below each section.
        </p>
      ) : null}
      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {rootAttrs.length > 0 ? (
          <div>
            <PeekSectionHeader
              label="Root attributes"
              shown={rootAttrs.length}
              total={rootAttrsTotal}
            />
            {/* Stack name on top of value so very long attribute names
                never push the value column off-screen. */}
            <ul className="font-mono text-[12px] space-y-2">
              {rootAttrs.map((attr) => (
                <li key={attr.name}>
                  <div className="text-[var(--fg-3)] break-all">
                    {attr.name}
                  </div>
                  <div className="text-[var(--fg-1)] break-all">
                    {formatAttrValue(attr.value)}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {topLevelKeys.length > 0 ? (
          <div>
            <PeekSectionHeader
              label="Top-level entries"
              shown={topLevelKeys.length}
              total={topLevelKeysTotal}
            />
            <ul className="font-mono text-[12px] space-y-1">
              {topLevelKeys.map((entry) => (
                <li
                  key={`${entry.kind}:${entry.name}`}
                  className="flex items-baseline gap-2"
                >
                  <span className="inline-flex items-center justify-center min-w-[44px] h-4 px-1 rounded border border-[var(--edge)] bg-white/[0.03] text-[10px] font-semibold uppercase tracking-wider text-[var(--fg-2)]">
                    {entry.kind === "group" ? "GROUP" : "DSET"}
                  </span>
                  <span className="text-[var(--fg-1)] truncate">
                    {entry.name}
                    {entry.kind === "group" ? "/" : ""}
                  </span>
                  {entry.kind === "dataset" && entry.shape ? (
                    <span className="text-[var(--fg-3)]">
                      {entry.shape.join("×")}
                      {entry.dtype ? ` ${entry.dtype}` : ""}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function PeekSectionHeader({
  label,
  shown,
  total,
}: {
  label: string;
  shown: number;
  total: number;
}) {
  const truncated = shown < total;
  return (
    <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)] mb-1">
      {label}{" "}
      <span className="tab-num">
        {truncated ? `(showing ${shown} of ${total})` : `(${total})`}
      </span>
    </div>
  );
}

function formatAttrValue(value: HandoffAttrValue): string {
  if (value === null) return "null";
  if (Array.isArray(value)) {
    return `[${value.map((v) => formatAttrValue(v)).join(", ")}]`;
  }
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    // Use scientific notation for very large / very small numbers so
    // the column doesn't blow out on energy bounds.
    const abs = Math.abs(value);
    if (abs !== 0 && (abs >= 1e6 || abs < 1e-3)) {
      return value.toExponential(4);
    }
    return String(value);
  }
  return String(value);
}

function ReadableHdf5Badge({ isMgxsHandoff }: { isMgxsHandoff: boolean }) {
  return isMgxsHandoff ? (
    <span className="rounded border border-emerald-300/25 bg-emerald-300/[0.06] px-2 py-1 text-[11px] font-semibold text-emerald-200">
      READABLE HDF5 · MGXS HANDOFF
    </span>
  ) : (
    <span className="rounded border border-sky-300/25 bg-sky-300/[0.06] px-2 py-1 text-[11px] font-semibold text-sky-100">
      READABLE HDF5 · NOT AN MGXS HANDOFF
    </span>
  );
}

function ReadinessStat({
  label,
  stat,
  children,
}: {
  label: string;
  stat: InspectProductionStat;
  children?: ReactNode;
}) {
  return (
    <div className="min-w-[150px] flex-1 rounded border border-[var(--edge)] bg-black/15 p-2">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--fg-3)]">
        {label}
      </div>
      <div
        className={
          "mt-1 text-[12px] font-semibold " +
          (stat.tone === "pass" ? "text-emerald-200" : "text-amber-200")
        }
      >
        {children ?? stat.value}
      </div>
      <div className="mt-1 text-[10px] leading-4 text-[var(--fg-3)]">
        {stat.detail}
      </div>
    </div>
  );
}

function MeshBadge({
  match,
  hint,
}: {
  match: HandoffInspection["mesh_match"];
  hint: InspectProductionStat;
}) {
  if (!match) {
    return (
      <span
        className="px-2 py-0.5 rounded-md border border-amber-400/25 bg-amber-400/[0.06] text-amber-300 text-[12px]"
        title={hint.detail}
      >
        no mesh match
      </span>
    );
  }
  return (
    <span
      className="px-2 py-0.5 rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-emerald-200 text-[12px]"
      title={
        match.description ? `${match.description} — ${hint.detail}` : hint.detail
      }
    >
      {match.short ?? match.name ?? match.id}
    </span>
  );
}

function Stat({
  label,
  value,
  tone,
  detail,
}: {
  label: string;
  value: string | number;
  tone?: InspectProductionStat["tone"];
  detail?: string;
}) {
  const valueClass =
    tone === "pass"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-300"
        : "";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-semibold ${valueClass}`.trim()}>
        {value}
      </div>
      {detail ? (
        <div className="mt-0.5 text-[11px] leading-4 text-[var(--fg-3)]">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-[var(--edge)] pb-2">
      <span className="text-[var(--fg-3)]">{label}</span>
      <span className="font-mono text-right">{value}</span>
    </div>
  );
}
