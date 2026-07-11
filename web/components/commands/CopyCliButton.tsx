"use client";

import { useState } from "react";
import { copyText } from "@/lib/copyText";

export function CopyCliButton({
  value,
  compact = false,
  label = "Copy CLI",
  copiedLabel = "Copied",
  failedLabel = "Copy failed",
  ariaLabel,
}: {
  value: string;
  compact?: boolean;
  label?: string;
  copiedLabel?: string;
  failedLabel?: string;
  ariaLabel?: string;
}) {
  const [feedback, setFeedback] = useState<"copied" | "failed" | null>(null);

  async function copy() {
    const copied = await copyText(value);
    setFeedback(copied ? "copied" : "failed");
    window.setTimeout(() => setFeedback(null), 1400);
  }

  return (
    <button
      type="button"
      onClick={copy}
      className={
        compact ? "btn btn-secondary px-2 py-1 text-[11px]" : "btn btn-secondary"
      }
      aria-label={ariaLabel ?? label}
    >
      {feedback === "copied"
        ? copiedLabel
        : feedback === "failed"
          ? failedLabel
          : label}
    </button>
  );
}
