import {
  decisionTileClass,
  gateBadgeClass,
  type GateStatus,
} from "./ConvertReportShared";

export function GateBadge({ status }: { status: GateStatus }) {
  return (
    <span
      className={
        "rounded-md border px-2 py-0.5 text-[11px] uppercase tracking-wider " +
        gateBadgeClass(status)
      }
    >
      {status}
    </span>
  );
}

export function DecisionTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "pass" | "warn" | "fail" | "accent" | "neutral";
}) {
  return (
    <div className={"rounded-md border px-3 py-2 " + decisionTileClass(tone)}>
      <div className="text-[10px] uppercase tracking-[0.14em] opacity-70">
        {label}
      </div>
      <div className="mt-1 font-mono text-[13px]">{value}</div>
    </div>
  );
}

export function IssueList({
  title,
  items,
  tone,
}: {
  title: string;
  items: readonly string[];
  tone: "rose" | "amber";
}) {
  if (items.length === 0) return null;
  const color = tone === "rose" ? "text-rose-300" : "text-amber-300";
  return (
    <div className="mt-4">
      <div className={`text-sm font-semibold ${color}`}>{title}</div>
      <ul className="mt-1 space-y-1 text-sm text-[var(--fg-1)]">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function Meta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]">
        {label}
      </dt>
      <dd
        className={
          "mt-0.5 truncate text-[var(--fg-1)] " + (mono ? "font-mono" : "")
        }
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}
