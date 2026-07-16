import { Suspense } from "react";
import ProjectWorkspace from "@/components/ProjectWorkspace";
import { WorkflowPageHeader } from "@/components/ui/Workflow";

export default function ProjectsPage() {
  return (
    <main className="app-page">
      <div className="app-container max-w-6xl">
        <WorkflowPageHeader
          step="Projects"
          eyebrow="Optional orchestration"
          title="Coordinate repeated Converter handoffs"
          description="Use a project manifest when several components, SPH evidence sets, or downstream runs must be tracked together. A project coordinates Converter jobs; it does not redefine Converter physics."
          input="Any project-declared component set"
          output="Tracked Converter objects, receipts, and consumer runs"
        />
        <section className="mb-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <ProjectPrinciple title="Any component count" body="One component or many; names and paths come from the manifest." />
          <ProjectPrinciple title="Explicit physics contracts" body="Direct MGXS and strict physical-SPH components can coexist when declared." />
          <ProjectPrinciple title="Full-core domains" body="Use independent positions, or exact symmetry orbits pooled during fine transport. Post-hoc cross-section averaging is not an accepted shortcut." />
          <ProjectPrinciple title="Template, not product default" body="IRENA is one built-in example, never the universal project shape." />
        </section>
        <Suspense fallback={<div className="surface p-5 text-sm text-[var(--fg-2)]">Loading project workspace…</div>}>
          <ProjectWorkspace />
        </Suspense>
      </div>
    </main>
  );
}

function ProjectPrinciple({ title, body }: { title: string; body: string }) {
  return (
    <article className="surface p-4">
      <h2 className="text-sm font-bold">{title}</h2>
      <p className="mt-2 text-[11px] leading-5 text-[var(--fg-3)]">{body}</p>
    </article>
  );
}
