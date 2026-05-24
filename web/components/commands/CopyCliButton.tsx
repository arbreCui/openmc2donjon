"use client";

import { useState } from "react";

export function CopyCliButton({ value, compact = false }: { value: string; compact?: boolean }) {
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
      className={compact ? "btn btn-secondary px-2 py-1 text-[11px]" : "btn btn-secondary"}
      aria-label="Copy CLI command"
    >
      {copied ? "Copied" : "Copy CLI"}
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
