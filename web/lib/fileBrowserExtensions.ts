/**
 * Extension filtering for the file-browser modal.
 *
 * Lives outside the component so the matching rules can be unit-tested
 * without spinning up React (same pattern as ``fileBrowserPath.ts``).
 */

/**
 * Compile a list of extensions into a single case-insensitive regex
 * matching any of them at end-of-name. Leading dots are stripped first
 * so both caller spellings (``"h5"`` and ``".h5"``) match
 * ``reference.h5`` — the builder specs historically passed dotted
 * extensions and every file was silently hidden. The remainder is
 * escaped so multi-part extensions like ``"mcompo.txt"`` keep their
 * literal dot.
 */
export function buildExtensionRegex(extensions: readonly string[]): RegExp {
  const normalized = extensions
    .map((ext) => ext.replace(/^\.+/, ""))
    .filter((ext) => ext !== "");
  if (normalized.length === 0) return /^$/;
  const escaped = normalized.map((ext) =>
    ext.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
  );
  return new RegExp(`\\.(${escaped.join("|")})$`, "i");
}
