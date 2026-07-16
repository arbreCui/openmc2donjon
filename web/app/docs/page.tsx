import Link from "next/link";

import { WorkflowPageHeader } from "@/components/ui/Workflow";

const REPOSITORY_DOCS =
  "https://github.com/arbreCui/openmc2donjon/blob/main/docs";

const STARTING_POINTS = [
  {
    title: "I already have a Converter-ready HDF5",
    body: "Validate the declared handoff, choose the object and writer, then keep the output with its hash-linked receipt.",
    href: "/convert",
    action: "Open Converter",
  },
  {
    title: "I only need to examine an HDF5",
    body: "Inspect root structure and metadata read-only. Compatible MGXS handoffs also expose mixtures, spectra, scattering, and provenance.",
    href: "/inspect",
    action: "Open Inspect",
  },
  {
    title: "I have an OpenMC recipe or statepoint",
    body: "Prepare the declared MGXS handoff first. This optional step stops before Converter writes a DRAGON/DONJON object.",
    href: "/openmc",
    action: "Prepare MGXS",
  },
  {
    title: "I need several components or repeated runs",
    body: "Use a manifest-driven Project to coordinate independent Converter jobs without imposing one reactor template.",
    href: "/projects",
    action: "Open Projects",
  },
] as const;

const RESPONSIBILITY_BOUNDARIES = [
  {
    name: "Converter",
    scope: "Required handoff boundary",
    does: "Checks the declared input contract and mapping, writes L_MULTICOMPO or L_MACROLIB, and records a traceable receipt.",
    doesNot: "Does not turn data integrity into a reactor-physics acceptance claim.",
  },
  {
    name: "Native DRAGON SPH",
    scope: "Optional physical equivalence",
    does: "Uses a frozen fine reference and a declared coarse model to establish the required rate equivalence.",
    doesNot: "Does not permit ADF substitution, an empirical global factor, or an undeclared geometry shortcut.",
  },
  {
    name: "DONJON",
    scope: "Downstream consumer",
    does: "Consumes the checked object in a component or full-core model and applies that model's acceptance criteria.",
    doesNot: "Does not inherit a physics verdict merely because Converter serialization succeeded.",
  },
] as const;

const GUIDES = [
  {
    title: "Quickstart",
    body: "Install, launch, and complete the shortest supported handoff.",
    file: "QUICKSTART.md",
  },
  {
    title: "Converter user guide",
    body: "The formal conversion path, outputs, receipts, and failure handling.",
    file: "CONVERTER_USER_README.md",
  },
  {
    title: "HDF5 input contract",
    body: "The exact boundary between a raw OpenMC artifact and a Converter-ready handoff.",
    file: "HDF5_INPUT_CONTRACT.md",
  },
  {
    title: "OpenMC export workflow",
    body: "Optional preparation from OpenMC when a handoff does not already exist.",
    file: "OPENMC_EXPORT_WORKFLOW.md",
  },
  {
    title: "Product model",
    body: "How Converter, OpenMC MGXS, SPH, Project, DONJON, Inspect, and PyGan relate.",
    file: "PRODUCT_MODEL.md",
  },
  {
    title: "Release gates",
    body: "Engineering checks required before a version is treated as releasable.",
    file: "RELEASE_GATES.md",
  },
] as const;

export default function DocumentationPage() {
  return (
    <main className="app-page">
      <div className="app-container max-w-6xl">
        <WorkflowPageHeader
          step="Docs"
          eyebrow="Product documentation"
          title="Understand the handoff before you run it"
          description="Start from the artifact you actually have, keep Converter's engineering guarantees separate from physics acceptance, and use the detailed contract guides when you need exact schema or command behavior."
          input="Your current artifact, model boundary, and intended downstream consumer"
          output="The correct entry point, contract, and evidence path"
          actions={
            <>
              <Link href="/convert" className="btn btn-primary">
                Open Converter
              </Link>
              <Link href="/commands" className="btn btn-secondary">
                CLI reference
              </Link>
            </>
          }
        />

        <section aria-labelledby="docs-start-title">
          <p className="page-kicker">Start here</p>
          <h2 id="docs-start-title" className="mt-1 text-2xl font-bold tracking-[-0.03em]">
            Choose by what you have now
          </h2>
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {STARTING_POINTS.map((item) => (
              <article key={item.href} className="surface flex h-full flex-col p-4">
                <h3 className="text-base font-bold tracking-tight">{item.title}</h3>
                <p className="mt-2 flex-1 text-[12px] leading-5 text-[var(--fg-2)]">
                  {item.body}
                </p>
                <Link href={item.href} className="btn btn-secondary mt-4 self-start">
                  {item.action} <span aria-hidden="true">→</span>
                </Link>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-10" aria-labelledby="docs-boundary-title">
          <p className="page-kicker">Responsibility boundary</p>
          <h2 id="docs-boundary-title" className="mt-1 text-2xl font-bold tracking-[-0.03em]">
            A successful conversion is not a physics verdict
          </h2>
          <div className="mt-5 grid gap-3 lg:grid-cols-3">
            {RESPONSIBILITY_BOUNDARIES.map((item) => (
              <article key={item.name} className="surface p-4">
                <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-[var(--accent)]">
                  {item.scope}
                </p>
                <h3 className="mt-2 text-base font-bold">{item.name}</h3>
                <p className="mt-3 text-[12px] leading-5 text-[var(--fg-1)]">
                  {item.does}
                </p>
                <p className="mt-3 border-t border-[var(--edge)] pt-3 text-[11px] leading-5 text-[var(--fg-3)]">
                  {item.doesNot}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-10" aria-labelledby="docs-guides-title">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="page-kicker">Detailed guides</p>
              <h2 id="docs-guides-title" className="mt-1 text-2xl font-bold tracking-[-0.03em]">
                Read the exact contract
              </h2>
            </div>
            <a
              href="https://github.com/arbreCui/openmc2donjon/tree/main/docs"
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary"
            >
              Browse all documentation ↗
            </a>
          </div>
          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {GUIDES.map((guide) => (
              <a
                key={guide.file}
                href={`${REPOSITORY_DOCS}/${guide.file}`}
                target="_blank"
                rel="noreferrer"
                className="surface block p-4 transition hover:border-emerald-200/30 hover:bg-white/[0.035]"
              >
                <span className="text-sm font-bold text-[var(--fg-0)]">{guide.title}</span>
                <span className="mt-2 block text-[12px] leading-5 text-[var(--fg-2)]">
                  {guide.body}
                </span>
                <span className="mt-3 block font-mono text-[10px] text-[var(--accent-2)]">
                  {guide.file} ↗
                </span>
              </a>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
