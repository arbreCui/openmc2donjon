import type { ReactNode } from "react";

export function WorkflowPageHeader({
  step,
  eyebrow,
  title,
  description,
  input,
  output,
  actions,
}: {
  step?: string;
  eyebrow: string;
  title: string;
  description: string;
  input?: string;
  output?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 border-b border-[var(--edge)] pb-7">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            {step ? <span className="step-dot">{step}</span> : null}
            <p className="page-kicker">{eyebrow}</p>
          </div>
          <h1 className="page-title text-[clamp(2rem,4vw,3.15rem)]">{title}</h1>
          <p className="page-description">{description}</p>
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
      </div>
      {input || output ? (
        <dl className="mt-6 grid gap-2 text-[12px] sm:grid-cols-2">
          {input ? <FlowFact label="Input" value={input} /> : null}
          {output ? <FlowFact label="Output" value={output} /> : null}
        </dl>
      ) : null}
    </header>
  );
}

export function FormStep({
  number,
  title,
  description,
  children,
  className = "",
}: {
  number: string;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-[var(--edge)] bg-white/[0.018] p-4 ${className}`}>
      <div className="mb-4 flex items-start gap-3">
        <span className="step-dot h-7 w-7 text-[10px]">{number}</span>
        <div>
          <h2 className="text-sm font-bold tracking-tight text-[var(--fg-0)]">
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-[12px] leading-5 text-[var(--fg-3)]">
              {description}
            </p>
          ) : null}
        </div>
      </div>
      {children}
    </section>
  );
}

export function FlowArrow() {
  return (
    <div className="flex h-8 items-center justify-center text-[var(--fg-3)]" aria-hidden="true">
      <span className="h-5 w-px bg-[var(--edge-bright)]" />
      <span className="-ml-[3px] mt-4 h-1.5 w-1.5 rotate-45 border-b border-r border-[var(--edge-bright)]" />
    </div>
  );
}

function FlowFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--edge)] bg-black/15 px-3 py-2.5">
      <dt className="w-12 shrink-0 pt-0.5 text-[9px] font-bold uppercase tracking-[0.14em] text-[var(--fg-3)]">
        {label}
      </dt>
      <dd className="leading-5 text-[var(--fg-1)]">{value}</dd>
    </div>
  );
}
