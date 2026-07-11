/**
 * Directory-picking helpers for output-path fields (the "Browse dir…"
 * pattern): an output file does not exist yet, so its Browse control
 * selects an existing *directory* and the field keeps (or gains) a
 * filename. Shared by the equivalence and builder pages.
 */

/**
 * Combine a picked directory with the current output filename, falling
 * back to the field's default filename when the field is empty.
 */
export function outputPathInDirectory(
  directory: string,
  currentOutput: string,
  fallbackName: string,
): string {
  const filename = basename(currentOutput) || fallbackName;
  return `${directory.replace(/\/+$/, "")}/${filename}`;
}

/**
 * Directory portion of a path value, for starting the file browser:
 * strips the filename segment; empty values and bare filenames fall
 * back to ``"~"`` (backend-resolved home).
 */
export function containingDirectory(path: string): string {
  const trimmed = path.trim();
  if (trimmed === "") return "~";
  if (trimmed.endsWith("/")) return trimmed;
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return "~";
  return trimmed.slice(0, index);
}

function basename(path: string): string {
  const trimmed = path.trim();
  if (trimmed === "") return "";
  const index = trimmed.lastIndexOf("/");
  return index >= 0 ? trimmed.slice(index + 1) : trimmed;
}
