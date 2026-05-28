import Link from "next/link";

import type {
  ConvertWriterBackend,
  PyGanBackendStatus,
} from "@/lib/api";
import {
  convertWriterBackendOptions,
  type ConvertWriterBackendOption,
} from "@/lib/convertWriterBackend";

export default function WriterBackendSelector({
  value,
  onChange,
  status,
}: {
  value: ConvertWriterBackend;
  onChange: (value: ConvertWriterBackend) => void;
  status: PyGanBackendStatus | null;
}) {
  const options = convertWriterBackendOptions(status);
  return (
    <section className="rounded-xl border border-[var(--edge)] bg-black/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            Writer backend
          </div>
          <h2 className="mt-1 text-sm font-semibold tracking-tight">
            Choose how the DONJON ASCII file is serialized
          </h2>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--fg-2)]">
            The physics tree is built by openmc2donjon in both modes. The
            default writer is the built-in pure Python ASCII LCM writer; PyGan
            is optional and useful when you want the DRAGON/DONJON Python
            bindings to perform the final export.
          </p>
        </div>
        <Link href="/pygan" className="btn btn-secondary shrink-0">
          PyGan status
        </Link>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {options.map((option) => (
          <WriterBackendOptionCard
            key={option.id}
            option={option}
            active={value === option.id}
            onSelect={() => onChange(option.id)}
          />
        ))}
      </div>
    </section>
  );
}

function WriterBackendOptionCard({
  option,
  active,
  onSelect,
}: {
  option: ConvertWriterBackendOption;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={option.disabled}
      aria-pressed={active}
      className={
        "min-w-0 rounded-lg border p-3 text-left transition disabled:cursor-not-allowed " +
        writerBackendCardClass(option, active)
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold tracking-tight">
          {option.title}
        </span>
        <span className="rounded border border-current/25 px-1.5 py-0.5 text-[10px] uppercase tracking-[0.14em]">
          {option.badge}
        </span>
      </div>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
        {option.body}
      </p>
      <p className="mt-2 text-[11px] leading-4 text-[var(--fg-3)]">
        {option.detail}
      </p>
    </button>
  );
}

function writerBackendCardClass(
  option: ConvertWriterBackendOption,
  active: boolean,
): string {
  if (option.disabled) {
    return "border-white/10 bg-white/[0.015] text-[var(--fg-3)] opacity-75";
  }
  if (active) {
    return "border-emerald-300/35 bg-emerald-300/[0.075] text-emerald-100";
  }
  if (option.tone === "available") {
    return "border-cyan-300/20 bg-cyan-300/[0.035] text-cyan-100 hover:border-cyan-300/35";
  }
  return "border-[var(--edge)] bg-white/[0.02] text-[var(--fg-1)] hover:border-[var(--edge-bright)]";
}
