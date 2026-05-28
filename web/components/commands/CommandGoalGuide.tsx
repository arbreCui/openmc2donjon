"use client";

import Link from "next/link";
import type { CommandGoal, CommandGoalId } from "@/lib/commandGoals";
import { CommandChip } from "@/components/commands/CommandPrimitives";

export function GoalCommandGuide({
  goals,
  activeGoalId,
  onGoalFilterChange,
}: {
  goals: CommandGoal[];
  activeGoalId: CommandGoalId | "all";
  onGoalFilterChange: (value: CommandGoalId | "all") => void;
}) {
  return (
    <section className="glass rounded-lg p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">
            Choose by user goal
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[var(--fg-2)]">
            Start from what the user is trying to accomplish. Each card shows
            the web entry point plus the CLI commands that support that goal.
          </p>
        </div>
        <span className="rounded border border-[var(--edge)] px-2 py-1 text-[11px] uppercase tracking-wider text-[var(--fg-2)]">
          goal -&gt; command
        </span>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {goals.map((goal) => {
          const isActive = activeGoalId === goal.id;
          return (
            <article
              key={goal.id}
              className={
                "rounded-lg border p-4 transition " +
                (isActive
                  ? "border-emerald-400/35 bg-emerald-400/[0.07]"
                  : "border-[var(--edge)] bg-white/[0.025]")
              }
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                    {goal.eyebrow}
                  </div>
                  <h3 className="mt-2 text-sm font-semibold tracking-tight">
                    {goal.title}
                  </h3>
                </div>
                <GoalStatusPill goal={goal} />
              </div>
              <p className="mt-2 min-h-[3.75rem] text-[12px] leading-5 text-[var(--fg-2)]">
                {goal.body}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {goal.commands.slice(0, 6).map((command) => (
                  <CommandChip key={`${goal.id}-${command.id}`} command={command} />
                ))}
                {goal.commands.length > 6 ? (
                  <span className="rounded border border-[var(--edge)] bg-white/[0.02] px-2 py-0.5 text-[10px] text-[var(--fg-3)]">
                    +{goal.commands.length - 6} more
                  </span>
                ) : null}
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onGoalFilterChange(isActive ? "all" : goal.id)}
                    className="btn btn-secondary"
                    aria-pressed={isActive}
                  >
                    {isActive ? "Clear filter" : "Show commands"}
                  </button>
                  <Link href={goal.href} className="btn btn-primary">
                    {goal.cta}
                  </Link>
                </div>
                <span className="text-[11px] text-[var(--fg-3)] tab-num">
                  {goal.commands.length}/{goal.commandIds.length} commands listed
                </span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function GoalStatusPill({ goal }: { goal: CommandGoal }) {
  const parts = [
    goal.readyCount > 0 ? `${goal.readyCount} ready` : null,
    goal.partialCount > 0 ? `${goal.partialCount} builder` : null,
    goal.plannedCount > 0 ? `${goal.plannedCount} CLI` : null,
  ].filter((part): part is string => part != null);
  return (
    <span className="rounded border border-cyan-300/25 bg-cyan-300/[0.06] px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-cyan-100">
      {parts.length > 0 ? parts.join(" · ") : "catalog"}
    </span>
  );
}
