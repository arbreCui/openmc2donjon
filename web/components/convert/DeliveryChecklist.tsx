"use client";

import Link from "next/link";
import type { ConvertPreflightInput, ConvertResponse } from "@/lib/api";
import {
  ConvertDeliveryItem,
  ConvertDeliveryStatus,
  convertDeliveryChecklist,
} from "@/lib/convertDeliveryChecklist";

export default function DeliveryChecklist({
  data,
  input,
  onConvert,
}: {
  data: ConvertResponse;
  input: ConvertPreflightInput | null;
  onConvert?: () => void;
}) {
  const items = convertDeliveryChecklist(data, input);
  const completed = items.filter((item) => item.status === "done").length;
  const ready = items.filter((item) => item.status === "ready").length;
  return (
    <section className="mt-4 rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">
            Delivery checklist
          </h3>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            Production handoff status from HDF5 QA through ASCII preview and
            bundle packaging.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 font-mono text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          {completed}/{items.length} done · {ready} ready
        </span>
      </div>
      <div className="mt-3 grid gap-2 lg:grid-cols-5">
        {items.map((item) => (
          <ChecklistCard key={item.id} item={item} onConvert={onConvert} />
        ))}
      </div>
    </section>
  );
}

function ChecklistCard({
  item,
  onConvert,
}: {
  item: ConvertDeliveryItem;
  onConvert?: () => void;
}) {
  return (
    <article className={"rounded-md border px-3 py-2 " + cardClass(item.status)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
          {item.label}
        </span>
        <span className="text-[10px] uppercase tracking-[0.14em] opacity-80">
          {statusLabel(item.status)}
        </span>
      </div>
      <h4 className="mt-2 text-sm font-semibold tracking-tight">{item.title}</h4>
      <p className="mt-1 text-[12px] leading-5 text-[var(--fg-2)]">
        {item.body}
      </p>
      <ChecklistAction item={item} onConvert={onConvert} />
    </article>
  );
}

function ChecklistAction({
  item,
  onConvert,
}: {
  item: ConvertDeliveryItem;
  onConvert?: () => void;
}) {
  if (item.action === "convert" && onConvert) {
    return (
      <button
        type="button"
        onClick={onConvert}
        className="mt-2 text-[12px] text-[var(--accent-2)] hover:underline"
      >
        Convert now
      </button>
    );
  }
  if (!item.href) return null;
  const label = item.href.startsWith("#") ? "Jump" : "Open";
  if (item.href.startsWith("#")) {
    return (
      <a
        href={item.href}
        className="mt-2 inline-flex text-[12px] text-[var(--accent-2)] hover:underline"
      >
        {label}
      </a>
    );
  }
  return (
    <Link
      href={item.href}
      className="mt-2 inline-flex text-[12px] text-[var(--accent-2)] hover:underline"
    >
      {label}
    </Link>
  );
}

function cardClass(status: ConvertDeliveryStatus): string {
  if (status === "done") {
    return "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-100";
  }
  if (status === "ready") {
    return "border-cyan-300/25 bg-cyan-300/[0.06] text-cyan-100";
  }
  if (status === "blocked") {
    return "border-rose-400/25 bg-rose-400/[0.06] text-rose-100";
  }
  if (status === "skipped") {
    return "border-amber-400/25 bg-amber-400/[0.06] text-amber-100";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-2)]";
}

function statusLabel(status: ConvertDeliveryStatus): string {
  if (status === "done") return "done";
  if (status === "ready") return "ready";
  if (status === "blocked") return "blocked";
  if (status === "skipped") return "skipped";
  return "pending";
}
