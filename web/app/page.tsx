import Link from "next/link";
import ConverterQuickStart from "@/components/ConverterQuickStart";
import { HOME_FLOW, HOME_HERO } from "@/lib/homeHero";

export default function Home() {
  return (
    <main className="app-page">
      <div className="app-container">
        <section className="grid gap-8 border-b border-[var(--edge)] pb-10 xl:grid-cols-[minmax(0,1fr)_430px] xl:items-center">
          <div className="py-2">
            <p className="page-kicker">{HOME_HERO.kicker}</p>
            <h1 className="page-title">{HOME_HERO.heading}</h1>
            <p className="page-description text-base">{HOME_HERO.paragraph}</p>
            <p className="mt-3 max-w-3xl text-[12px] leading-5 text-[var(--fg-3)]">
              {HOME_HERO.supporting}
            </p>
            <ProductFlow />
          </div>
          <ConverterQuickStart />
        </section>

        <ProductArchitecture />
        <StartingPoints />

        <section className="mt-10 border-t border-[var(--edge)] pt-6">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px]">
            <span className="font-bold text-[var(--fg-1)]">Supporting tools</span>
            <Link href="/commands" className="inline-flex min-h-10 items-center rounded-lg px-2 text-[var(--fg-3)] hover:bg-white/[0.035] hover:text-[var(--accent-2)]">CLI reference</Link>
            <Link href="/pygan" className="inline-flex min-h-10 items-center rounded-lg px-2 text-[var(--fg-3)] hover:bg-white/[0.035] hover:text-[var(--accent-2)]">PyGan writer &amp; validation</Link>
            <Link href="/settings" className="inline-flex min-h-10 items-center rounded-lg px-2 text-[var(--fg-3)] hover:bg-white/[0.035] hover:text-[var(--accent-2)]">Settings</Link>
          </div>
        </section>
      </div>
    </main>
  );
}

function ProductArchitecture() {
  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="page-kicker">Product architecture</p>
          <h2 className="mt-1 text-2xl font-bold tracking-[-0.03em]">
            One Converter boundary, optional workflows around it
          </h2>
        </div>
        <p className="max-w-xl text-[12px] leading-5 text-[var(--fg-3)]">
          Prepare inputs, run equivalence, coordinate components, or calculate
          downstream only when the model requires it. Every formal handoff still
          passes through the same checked Converter.
        </p>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 md:items-start xl:grid-cols-[0.92fr_1.16fr_0.92fr]">
        <div className="md:col-span-2 xl:col-span-1 xl:col-start-2 xl:row-start-1">
          <ConverterArchitectureCard />
        </div>

        <div className="md:col-start-1 md:row-start-2 xl:col-start-1 xl:row-start-1">
          <ArchitectureCard eyebrow="Optional preparation" title="Prepare the reference">
            <ArchitectureLink href="/openmc" label="OpenMC MGXS" body="Export the groups, domains, moments, and uncertainties required by your model." />
            <div className="rounded-xl border border-[var(--edge)] bg-black/10 p-3 text-[10px] leading-4 text-[var(--fg-3)]">
              If a converter-ready HDF5 already exists, start directly with Converter. OpenMC MG mode is not required for native DRAGON SPH.
            </div>
          </ArchitectureCard>
        </div>

        <div className="md:col-start-2 md:row-start-2 xl:col-start-3 xl:row-start-1">
          <ArchitectureCard
            eyebrow="Optional physics & downstream"
            title="SPH when needed; DONJON downstream"
          >
            <div className="rounded-xl border border-[var(--edge)] bg-black/10 p-3">
              <p className="font-mono text-[10px] text-[var(--accent)]">OUTPUT</p>
              <p className="mt-1 text-[12px] font-bold">L_MULTICOMPO or L_MACROLIB</p>
              <p className="mt-1 text-[10px] leading-4 text-[var(--fg-3)]">Checked ASCII/LCM object plus exact Converter receipt.</p>
            </div>
            <ArchitectureLink href="/equivalence" label="Native DRAGON SPH" body="Use Converter reference rates on the project-declared coarse geometry; no ADF or fitted global coefficient." />
            <ArchitectureLink href="/donjon" label="DONJON use and validation" body="Consume the corrected object in a component or full-core model with its own mapping and acceptance criteria." />
          </ArchitectureCard>
        </div>
      </div>

      <Link
        href="/projects"
        className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-sky-200/20 bg-sky-300/[0.035] px-4 py-3 transition hover:border-sky-200/35 hover:bg-sky-300/[0.06]"
      >
        <span>
          <strong className="text-sm text-[var(--fg-0)]">Project coordination</strong>
          <span className="mt-1 block text-[11px] text-[var(--fg-3)] sm:ml-2 sm:mt-0 sm:inline">Optional manifests coordinate repeated component conversions, SPH evidence, and downstream runs.</span>
        </span>
        <span className="text-[12px] font-semibold text-[var(--accent-2)]">Open Projects →</span>
      </Link>
    </section>
  );
}

function StartingPoints() {
  const paths = [
    {
      id: "inspect",
      label: "I only want to examine an HDF5",
      title: "Inspect OpenMC HDF5",
      body: "Open a file read-only. Compatible MGXS handoffs get mixture, spectrum, and scattering visualizations; other HDF5 files still expose their root metadata and structure. Converter is not required.",
      href: "/inspect",
      cta: "Open Inspect",
    },
    {
      id: "openmc",
      label: "I have a recipe or statepoint",
      title: "Prepare OpenMC MGXS",
      body: "Create the HDF5 handoff first, then bring it to Converter.",
      href: "/openmc",
      cta: "Open OpenMC MGXS",
    },
    {
      id: "component",
      label: "I only need one component library",
      title: "Convert one component",
      body: "Choose the mixtures that belong to the component, run the formal gate, and stop with the output plus receipt. A full-core project is not required.",
      href: "/convert?check=1&production=1#convert-component",
      cta: "Open component conversion",
    },
    {
      id: "sph",
      label: "My coarse model needs equivalence",
      title: "Compute and apply SPH",
      body: "Use the fine OpenMC reference, Converter output, and your declared DRAGON/DONJON coarse model. OpenMC MG remains optional.",
      href: "/equivalence",
      cta: "Open SPH",
    },
    {
      id: "project",
      label: "I have several components or runs",
      title: "Coordinate a Project",
      body: "Declare any component set and track each Converter output without imposing one reactor template.",
      href: "/projects",
      cta: "Open Projects",
    },
    {
      id: "consumer",
      label: "My Converter artifact is ready",
      title: "Use it downstream",
      body: "Connect the checked object to a user-defined component or full-core DRAGON/DONJON model, or validate the optional PyGan writer without changing the physics contract.",
      href: "/donjon",
      cta: "Open DONJON",
    },
  ] as const;
  return (
    <section className="mt-10">
      <p className="page-kicker">Classic user jobs</p>
      <h2 className="mt-1 text-2xl font-bold tracking-[-0.03em]">Start from what you actually have</h2>
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {paths.map((path) => (
          <article key={path.id} className="surface flex h-full flex-col p-4">
            <p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[var(--fg-3)]">{path.label}</p>
            <h3 className="mt-2 text-base font-bold tracking-tight">{path.title}</h3>
            <p className="mt-2 flex-1 text-[12px] leading-5 text-[var(--fg-2)]">{path.body}</p>
            <Link href={path.href} className="btn btn-quiet mt-3 w-full justify-between px-2">{path.cta} <span aria-hidden="true">→</span></Link>
          </article>
        ))}
      </div>
    </section>
  );
}

function ProductFlow() {
  const handoffStages = HOME_FLOW.slice(0, 3);
  const optionalStage = HOME_FLOW[3];

  return (
    <section aria-labelledby="home-product-flow-title" className="mt-6 max-w-[54rem]">
      <h2 id="home-product-flow-title" className="sr-only">Product flow</h2>
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_1.25rem_minmax(0,0.86fr)_1.25rem_minmax(0,1.15fr)] sm:items-center">
        {handoffStages.map((stage, index) => (
          <div key={stage.label} className="contents">
            {index > 0 ? <StageArrow /> : null}
            <FlowStage
              label={stage.label}
              qualifier={stage.qualifier}
              tone={stage.label === "Converter" ? "required" : index === 2 ? "output" : "neutral"}
            />
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
        <span aria-hidden="true" className="hidden h-px flex-1 bg-gradient-to-r from-transparent via-[var(--edge-bright)] to-[var(--edge-bright)] sm:block" />
        <span className="text-center text-[10px] font-bold uppercase tracking-[0.11em] text-[var(--fg-3)]">
          Optional workflows · only when required
        </span>
        <StageArrow />
        <FlowStage
          label={optionalStage.label}
          qualifier={optionalStage.qualifier}
          tone="optional"
          className="sm:min-w-[17rem]"
        />
      </div>
    </section>
  );
}

function ConverterArchitectureCard() {
  return (
    <article className="rounded-2xl border border-emerald-200/35 bg-emerald-300/[0.075] p-5 shadow-[var(--shadow-md)]">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-200/80">
          Product core
        </p>
        <span className="rounded-full border border-emerald-200/25 bg-emerald-300/10 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.1em] text-emerald-100">
          required
        </span>
      </div>
      <h3 className="mt-2 text-xl font-bold tracking-tight">Converter</h3>
      <p className="mt-2 text-[12px] leading-5 text-[var(--fg-2)]">
        Validate one MGXS handoff, select the object contract and writer, then
        produce the DRAGON/DONJON object with a hash-linked receipt.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-2 text-center text-[10px] md:grid-cols-4">
        <CoreStep label="Validate" />
        <CoreStep label="Choose writer" />
        <CoreStep label="Write object" />
        <CoreStep label="Receipt" />
      </div>

      <div className="mt-4 rounded-xl border border-emerald-200/15 bg-black/10 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] font-bold text-[var(--fg-1)]">Converter writers</p>
          <Link href="/pygan" className="text-[10px] font-semibold text-[var(--accent-2)] hover:underline">
            PyGan details →
          </Link>
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <ConverterWriter
            badge="built in"
            title="ASCII"
            body="Portable L_MULTICOMPO or L_MACROLIB handoff without a PyGan dependency."
          />
          <ConverterWriter
            badge="optional"
            title="PyGan / LCM"
            body="Native LCM writing and validation when PyGan is installed in the environment."
          />
        </div>
        <p className="mt-3 text-[10px] leading-4 text-[var(--fg-3)]">
          Both writers follow the same checked physics contract; the backend only changes how the object is encoded.
        </p>
      </div>

      <Link href="/convert" className="btn btn-primary mt-5 w-full justify-center">
        Open Converter <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

function FlowStage({
  label,
  qualifier,
  tone,
  className = "",
}: {
  label: string;
  qualifier: string;
  tone: "neutral" | "required" | "output" | "optional";
  className?: string;
}) {
  const toneClass = {
    neutral: "border-[var(--edge)] bg-white/[0.025]",
    required: "border-emerald-200/40 bg-emerald-300/10 shadow-[0_10px_28px_rgba(47,201,133,0.08)]",
    output: "border-sky-200/25 bg-sky-300/[0.04]",
    optional: "border-dashed border-[var(--edge-bright)] bg-white/[0.018]",
  }[tone];

  return (
    <span
      className={`flex min-h-[58px] flex-col justify-center rounded-xl border px-3 py-2 ${toneClass} ${className}`}
    >
      <span className="block text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--fg-1)]">{label}</span>
      <span className={`mt-1 block text-[10px] leading-4 tracking-[0.02em] ${tone === "required" ? "text-emerald-100" : "text-[var(--fg-3)]"}`}>
        {qualifier}
      </span>
    </span>
  );
}

function StageArrow() {
  return (
    <span aria-hidden="true" className="flex h-5 items-center justify-center text-[12px] text-[var(--fg-3)]">
      <span className="rotate-90 sm:rotate-0">→</span>
    </span>
  );
}

function ArchitectureCard({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <article className="rounded-2xl border border-[var(--edge)] bg-[var(--surface)] p-5">
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--fg-3)]">{eyebrow}</p>
      <h3 className="mt-2 text-lg font-bold tracking-tight">{title}</h3>
      <div className="mt-4 grid gap-2">{children}</div>
    </article>
  );
}

function ArchitectureLink({ href, label, body }: { href: string; label: string; body: string }) {
  return (
    <Link href={href} className="rounded-xl border border-[var(--edge)] bg-black/10 p-3 transition hover:border-emerald-200/25 hover:bg-white/[0.035]">
      <span className="text-[12px] font-bold text-[var(--fg-0)]">{label}</span>
      <span className="mt-1 block text-[10px] leading-4 text-[var(--fg-3)]">{body}</span>
    </Link>
  );
}

function CoreStep({ label }: { label: string }) {
  return <span className="rounded-lg border border-emerald-200/20 bg-black/10 px-2 py-2 font-semibold text-emerald-100">{label}</span>;
}

function ConverterWriter({ badge, title, body }: { badge: string; title: string; body: string }) {
  return (
    <div className="rounded-lg border border-emerald-200/15 bg-emerald-300/[0.045] p-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-bold text-[var(--fg-0)]">{title}</p>
        <span className="rounded-full border border-emerald-200/20 px-1.5 py-0.5 font-mono text-[9px] uppercase text-emerald-100/80">
          {badge}
        </span>
      </div>
      <p className="mt-1 text-[10px] leading-4 text-[var(--fg-3)]">{body}</p>
    </div>
  );
}
