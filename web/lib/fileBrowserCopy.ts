/**
 * Wording helpers for the file-browser modal.
 *
 * Callers supply a short ``fileTypeLabel`` noun phrase ("HDF5",
 * "input file", "output directory"). These helpers append the
 * file/directory noun without doubling the word when the label already
 * ends with it — "input file" must not render as "Browse for input
 * file file" or "3 non-input file files hidden". Unit-tested without
 * React, same pattern as ``fileBrowserPath.ts``.
 */

const SINGULAR_NOUNS: Record<string, string> = {
  files: "file",
  directories: "directory",
  entries: "entry",
};

/**
 * ``"input file" + "file"`` → ``"input file"``; ``"HDF5" + "file"`` →
 * ``"HDF5 file"``; ``"input file" + "files"`` → ``"input files"``;
 * ``"directory" + "directory"`` → ``"directory"``.
 */
export function labelWithNoun(fileTypeLabel: string, noun: string): string {
  const label = fileTypeLabel.trim();
  const singular = SINGULAR_NOUNS[noun] ?? noun;
  const lower = label.toLowerCase();
  let base = label;
  if (lower === singular) {
    base = "";
  } else if (lower.endsWith(` ${singular}`)) {
    base = label.slice(0, label.length - singular.length - 1).trimEnd();
  }
  return base ? `${base} ${noun}` : noun;
}

/** Dialog title / accessible name for the browse modal. */
export function browseDialogTitle(
  fileTypeLabel: string,
  selectMode: "file" | "directory",
): string {
  const noun = selectMode === "directory" ? "directory" : "file";
  return `Browse for ${labelWithNoun(fileTypeLabel, noun)}`;
}

/** Footer line counting entries hidden by the extension filter. */
export function hiddenEntriesNote(
  hiddenCount: number,
  fileTypeLabel: string,
  selectMode: "file" | "directory",
): string {
  const [singular, plural] =
    selectMode === "directory" ? ["entry", "entries"] : ["file", "files"];
  const phrase = labelWithNoun(
    fileTypeLabel,
    hiddenCount === 1 ? singular : plural,
  );
  return `${hiddenCount} non-${phrase} hidden.`;
}
