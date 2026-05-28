import type { ConvertFormat } from "@/lib/api";
import {
  convertModeReference,
  type ConvertModeReferenceItem,
} from "@/lib/convertModeReference";

export default function ConvertModeReferenceStrip({
  format,
}: {
  format: ConvertFormat;
}) {
  const items = convertModeReference(format);
  return (
    <section className="rounded-lg border border-[var(--edge)] bg-black/10 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">
            What each action means
          </h2>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            The converter is deliberately linear: check without writing, write
            the ASCII file, then review and package it.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          user flow
        </span>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-3">
        {items.map((item) => (
          <ConvertModeCard key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}

function ConvertModeCard({ item }: { item: ConvertModeReferenceItem }) {
  return (
    <article
      className={
        "rounded-md border px-3 py-2 " +
        convertModeReferenceClass(item.emphasis)
      }
    >
      <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
        {item.label}
      </span>
      <h3 className="mt-2 text-[12px] font-semibold tracking-tight">
        {item.title}
      </h3>
      <p className="mt-1 text-[11px] leading-4 text-[var(--fg-2)]">
        {item.body}
      </p>
    </article>
  );
}

function convertModeReferenceClass(
  emphasis: ConvertModeReferenceItem["emphasis"],
): string {
  if (emphasis === "safe") {
    return "border-cyan-300/20 bg-cyan-300/[0.045] text-cyan-100";
  }
  if (emphasis === "write") {
    return "border-emerald-300/20 bg-emerald-300/[0.045] text-emerald-100";
  }
  return "border-amber-300/20 bg-amber-300/[0.045] text-amber-100";
}
