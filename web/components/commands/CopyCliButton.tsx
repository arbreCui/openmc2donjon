"use client";

import { useState } from "react";

export function CopyCliButton({
  value,
  compact = false,
  label = "Copy CLI",
  copiedLabel = "Copied",
  ariaLabel,
}: {
  value: string;
  compact?: boolean;
  label?: string;
  copiedLabel?: string;
  ariaLabel?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await copyText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
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
      {copied ? copiedLabel : label}
    </button>
  );
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back to a temporary textarea when the browser denies the
      // async clipboard API on a local/dev origin.
    }
  }
  const element = document.createElement("textarea");
  element.value = value;
  element.setAttribute("readonly", "true");
  element.style.position = "fixed";
  element.style.opacity = "0";
  document.body.appendChild(element);
  element.select();
  document.execCommand("copy");
  document.body.removeChild(element);
}
