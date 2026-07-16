"use client";

import Link from "next/link";
import { useState } from "react";
import { converterQuickStartHref } from "@/lib/converterQuickStart";

export default function ConverterQuickStart() {
  const [inputPath, setInputPath] = useState("");
  const href = converterQuickStartHref(inputPath);

  return (
    <section
      aria-labelledby="quick-convert-title"
      className="w-full max-w-[48rem] rounded-2xl border border-emerald-200/30 bg-emerald-300/[0.055] p-5 shadow-[var(--shadow-md)] sm:p-6 xl:max-w-none"
    >
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-200/80">
        Direct Converter
      </p>
      <h2 id="quick-convert-title" className="mt-1 text-xl font-bold tracking-tight">
        Start with a Converter-ready MGXS handoff
      </h2>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
        This is the common path when the OpenMC export step is already done.
        Enter its openmc2donjon handoff path now or browse on the next page;
        Converter validates the schema before it writes anything.
      </p>

      <label className="mt-5 block">
        <span className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--fg-2)]">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-300/15 font-mono text-[10px] text-emerald-100">1</span>
          Converter-ready MGXS handoff (.h5)
        </span>
        <input
          value={inputPath}
          onChange={(event) => setInputPath(event.target.value)}
          placeholder="/path/to/mgxs_library.h5"
          className="mt-2 w-full rounded-lg border border-[var(--edge)] bg-black/20 px-3 py-2.5 font-mono text-sm text-[var(--fg-0)]"
        />
      </label>

      <Link href={href} className="btn btn-primary mt-5 w-full justify-center">
        {inputPath.trim() ? "Continue to Converter" : "Open Converter"}
        <span aria-hidden="true">→</span>
      </Link>

      <ul className="mt-4 grid gap-1.5 text-[10px] leading-4 text-[var(--fg-3)] sm:grid-cols-3">
        <QuickFact>Inspect and validate</QuickFact>
        <QuickFact>Choose the output object and writer</QuickFact>
        <QuickFact>Keep a hash-linked receipt</QuickFact>
      </ul>
      <p className="mt-4 border-t border-[var(--edge)] pt-4 text-[11px] text-[var(--fg-3)]">
        No converter-ready handoff yet?{" "}
        <Link href="/openmc" className="font-semibold text-[var(--accent-2)] hover:underline">
          Prepare one from OpenMC
        </Link>
      </p>
    </section>
  );
}

function QuickFact({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-300/65" />
      <span>{children}</span>
    </li>
  );
}
