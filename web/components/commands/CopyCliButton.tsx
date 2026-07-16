"use client";

import { useState } from "react";
import { copyText } from "@/lib/copyText";

export function CopyCliButton({
  value,
  compact = false,
  variant = "secondary",
  label = "Copy CLI",
  copiedLabel = "Copied",
  failedLabel = "Copy failed",
  ariaLabel,
  disabled = false,
}: {
  value: string;
  compact?: boolean;
  variant?: "primary" | "secondary";
  label?: string;
  copiedLabel?: string;
  failedLabel?: string;
  ariaLabel?: string;
  disabled?: boolean;
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
        compact
          ? `btn btn-${variant} px-2 py-1 text-[11px]`
          : `btn btn-${variant}`
      }
      aria-label={ariaLabel ?? label}
      disabled={disabled}
    >
      {feedback === "copied"
        ? copiedLabel
        : feedback === "failed"
          ? failedLabel
          : label}
    </button>
  );
}
