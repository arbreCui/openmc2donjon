import Link from "next/link";
import type { TaskEntrypoint } from "@/lib/taskEntrypoints";

export default function TaskLauncher({
  title,
  summary,
  entries,
  className = "",
}: {
  title: string;
  summary: string;
  entries: readonly TaskEntrypoint[];
  className?: string;
}) {
  return (
    <section className={"glass rounded-xl p-5 " + className}>
      <div>
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
          {summary}
        </p>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {entries.map((entry) => (
          <Link
            key={entry.id}
            href={entry.href}
            className="group rounded-lg border border-[var(--edge)] bg-white/[0.02] p-4 transition hover:border-[var(--edge-bright)] hover:bg-white/[0.045]"
          >
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
              {entry.eyebrow}
            </div>
            <h3 className="mt-2 text-sm font-semibold tracking-tight text-[var(--fg-0)]">
              {entry.title}
            </h3>
            <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
              {entry.body}
            </p>
            <div className="mt-4 text-[12px] font-medium text-[var(--accent-2)] group-hover:underline">
              {entry.cta}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
