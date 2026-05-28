export default function BackendModeCard({
  tone,
  title,
  body,
}: {
  tone: "loading" | "error";
  title: string;
  body: string;
}) {
  const cls =
    tone === "error"
      ? "border-rose-300/25 bg-rose-300/[0.06] text-rose-100"
      : "border-cyan-300/20 bg-cyan-300/[0.05] text-cyan-100";
  return (
    <section className={"mb-5 rounded-xl border p-4 " + cls}>
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-80">
        Backend status
      </div>
      <h2 className="mt-1 text-sm font-semibold tracking-tight">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
        {body}
      </p>
    </section>
  );
}
