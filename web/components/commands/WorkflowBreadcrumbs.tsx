"use client";

import Link from "next/link";
import { commandWorkflowOccurrences } from "@/lib/commandWorkflowLanes";

/**
 * One-line workflow-position strip shared by /commands/[id] and
 * /builder: for each workflow the command appears in, show the
 * previous and next steps as 1-click hops around the current step.
 */
export function WorkflowBreadcrumbs({
  commandId,
  className = "",
}: {
  commandId: string;
  className?: string;
}) {
  const occurrences = commandWorkflowOccurrences(commandId);
  if (occurrences.length === 0) return null;
  return (
    <div className={"space-y-1.5 " + className}>
      {occurrences.map((occurrence) => (
        <p
          key={`${occurrence.lane.id}-${occurrence.step.id}`}
          className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-[var(--edge)] bg-black/10 px-3 py-1.5 text-[12px] leading-5"
        >
          <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
            {occurrence.lane.title}
          </span>
          {occurrence.previousStep ? (
            <Link
              href={occurrence.previousStep.href}
              className="text-[var(--fg-2)] hover:text-emerald-200"
            >
              ← {occurrence.previousStep.title}
            </Link>
          ) : (
            <span className="text-[var(--fg-3)]">Start</span>
          )}
          <span className="text-[var(--fg-3)]">·</span>
          <span className="font-semibold text-[var(--fg-0)]">
            {String(occurrence.stepIndex + 1).padStart(2, "0")}{" "}
            {occurrence.step.title}
          </span>
          <span className="text-[var(--fg-3)]">·</span>
          {occurrence.nextStep ? (
            <Link
              href={occurrence.nextStep.href}
              className="text-[var(--fg-2)] hover:text-emerald-200"
            >
              {occurrence.nextStep.title} →
            </Link>
          ) : (
            <span className="text-[var(--fg-3)]">End</span>
          )}
        </p>
      ))}
    </div>
  );
}
