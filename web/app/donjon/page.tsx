"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CopyCliButton } from "@/components/commands/CopyCliButton";
import {
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  donjonObjectLabel,
  donjonShortName,
  inferDonjonFormat,
  placeholderAsciiPath,
  type DonjonGuideFormat,
} from "@/lib/donjonGuide";

export default function DonjonPage() {
  return (
    <Suspense fallback={<DonjonLoading />}>
      <DonjonPageContent />
    </Suspense>
  );
}

function DonjonLoading() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <section className="glass rounded-xl p-5 text-sm text-[var(--fg-2)]">
          Loading DONJON handoff guide…
        </section>
      </div>
    </main>
  );
}

function DonjonPageContent() {
  const searchParams = useSearchParams();
  const queryAscii = searchParams.get("ascii") ?? "";
  const queryFormat = searchParams.get("format");
  const queryManifest = searchParams.get("manifest") ?? "";
  const [asciiPath, setAsciiPath] = useState(queryAscii);
  const [format, setFormat] = useState<DonjonGuideFormat>(
    inferDonjonFormat(queryAscii, queryFormat),
  );
  const [manifestPath, setManifestPath] = useState(queryManifest);

  const objectLabel = donjonObjectLabel(format);
  const shortName = donjonShortName(format);
  const ingestSnippet = useMemo(
    () => donjonIngestSnippet(asciiPath, format),
    [asciiPath, format],
  );
  const dumpSnippet = useMemo(
    () => donjonIngestOnlySnippet(asciiPath, format),
    [asciiPath, format],
  );
  const selfHref = donjonGuideHref({
    asciiPath,
    format,
    manifestPath,
  });

  return (
    <main className="min-h-[calc(100vh-3.5rem)] px-6 py-12">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8">
          <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--fg-3)]">
            DONJON consumption
          </div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight">
            <span className="grad-text">Use the ASCII handoff in DONJON</span>
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            This page does not run DONJON. It turns the converter output path into
            the small deck fragments that DONJON users need: load the ASCII object,
            build or reuse a macrolib, then attach the case-specific geometry,
            tracking, and solver.
          </p>
        </header>

        <section className="glass rounded-xl p-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_220px]">
            <label className="block">
              <span className="text-sm font-semibold tracking-tight">
                ASCII handoff path
              </span>
              <input
                value={asciiPath}
                onChange={(event) => setAsciiPath(event.target.value)}
                placeholder={placeholderAsciiPath(format)}
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)]"
              />
            </label>
            <label className="block">
              <span className="text-sm font-semibold tracking-tight">Format</span>
              <select
                value={format}
                onChange={(event) =>
                  setFormat(event.target.value as DonjonGuideFormat)
                }
                className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 text-sm text-[var(--fg-0)]"
              >
                <option value="multicompo">MULTICOMPO</option>
                <option value="macrolib">MACROLIB</option>
              </select>
            </label>
          </div>
          <label className="mt-3 block">
            <span className="text-sm font-semibold tracking-tight">
              Bundle manifest (optional)
            </span>
            <input
              value={manifestPath}
              onChange={(event) => setManifestPath(event.target.value)}
              placeholder="bundle/manifest.json"
              className="mt-2 w-full rounded-md border border-[var(--edge)] bg-black/20 px-3 py-2 font-mono text-sm text-[var(--fg-0)]"
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <CopyCliButton value={selfHref} label="Copy page link" />
            <Link href="/convert" className="btn btn-secondary">
              Back to convert
            </Link>
            {manifestPath.trim() ? (
              <Link
                href={`/builder?command=validate-bundle&manifest=${encodeURIComponent(
                  manifestPath.trim(),
                )}`}
                className="btn btn-secondary"
              >
                Validate bundle
              </Link>
            ) : null}
          </div>
        </section>

        <section className="mt-5 grid gap-4 lg:grid-cols-3">
          <GuidanceCard
            eyebrow="object"
            title={objectLabel}
            body={
              format === "multicompo"
                ? "Use this when the converter wrote mapped domain-wise mixtures. DONJON typically reads it as CPO, then NCR extracts a MACROLIB for the geometry mixture map."
                : "Use this when the converter wrote a direct one-state macrolib. DONJON can assign the ASCII object directly to MACRO."
            }
          />
          <GuidanceCard
            eyebrow="mapping"
            title={
              format === "multicompo" ? "NCR builds MACRO" : "MACRO is direct"
            }
            body={
              format === "multicompo"
                ? "Your GEOM MIX numbers must correspond to the mixture indices you select in the NCR MIX lines."
                : "Your GEOM MIX numbers refer directly to the mixtures stored in the L_MACROLIB object."
            }
          />
          <GuidanceCard
            eyebrow="solver"
            title="Geometry stays case-specific"
            body="The generated skeleton deliberately keeps geometry and tracking minimal. Replace those blocks with the diffusion, SPN, or SN deck for the real case."
          />
        </section>

        <section className="mt-5 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <SnippetCard
            title={`${shortName} ingest smoke`}
            description="Use this tiny deck first when you only want to confirm that DONJON can read the ASCII file."
            code={dumpSnippet}
          />
          <SnippetCard
            title="Low-order solve skeleton"
            description="Use this as a starting point for a real DONJON deck; replace geometry, tracking, and solver details."
            code={ingestSnippet}
          />
        </section>

        <section className="mt-5 rounded-xl border border-[var(--edge)] bg-white/[0.02] p-4">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            production reminder
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            The converter does not define the core model by itself
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-[var(--fg-2)]">
            OpenMC supplies the homogenized cross sections. DONJON still needs
            the deterministic geometry, mixture assignment, tracking options,
            boundary conditions, and solver choice. For SPH workflows, keep the
            OpenMC reference flux fixed and let the SPH loop update factors
            around this same low-order DONJON deck.
          </p>
        </section>
      </div>
    </main>
  );
}

function GuidanceCard({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <article className="rounded-lg border border-[var(--edge)] bg-black/15 p-4">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {eyebrow}
      </div>
      <h2 className="mt-1 text-sm font-semibold tracking-tight">{title}</h2>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">{body}</p>
    </article>
  );
}

function SnippetCard({
  title,
  description,
  code,
}: {
  title: string;
  description: string;
  code: string;
}) {
  return (
    <article className="rounded-xl border border-[var(--edge)] bg-black/15 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
            {description}
          </p>
        </div>
        <CopyCliButton value={code} label="Copy deck" compact />
      </div>
      <pre className="mt-3 max-h-[460px] overflow-auto rounded-lg border border-[var(--edge)] bg-black/30 p-3 text-[12px] leading-5 text-[var(--fg-1)]">
        {code}
      </pre>
    </article>
  );
}
