import Link from "next/link";

import type { ConvertIntentCopy } from "@/lib/convertIntent";

export default function ConvertIntentBanner({ intent }: { intent: ConvertIntentCopy }) {
  return (
    <section className={"mb-5 rounded-xl border p-4 " + intentBannerClass(intent.tone)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
            {intent.eyebrow}
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {intent.title}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            {intent.body}
          </p>
        </div>
        {intent.commandHref && intent.commandLabel ? (
          <Link href={intent.commandHref} className="btn btn-secondary shrink-0">
            {intent.commandLabel}
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function intentBannerClass(tone: ConvertIntentCopy["tone"]): string {
  if (tone === "accent") return "border-cyan-300/25 bg-cyan-300/[0.05]";
  if (tone === "production") {
    return "border-emerald-300/25 bg-emerald-300/[0.05]";
  }
  if (tone === "sph") return "border-amber-300/25 bg-amber-300/[0.05]";
  return "border-[var(--edge)] bg-white/[0.02]";
}
