import { parseMixtures } from "./convertCommand";

export interface MixtureScopeSelection {
  allByDefault: boolean;
  selected: Set<string>;
  selectedCount: number;
}

export function mixtureScopeSelection(
  value: string,
  knownNames: readonly string[],
): MixtureScopeSelection {
  const allByDefault = value.trim() === "";
  const selected = new Set(parseMixtures(value) ?? []);
  return {
    allByDefault,
    selected,
    selectedCount: allByDefault
      ? knownNames.length
      : knownNames.filter((name) => selected.has(name)).length,
  };
}

export function normalizeMixtureScope(
  selectedNames: Iterable<string>,
  knownNames: readonly string[],
): string {
  const selected = Array.from(selectedNames);
  const known = new Set(knownNames);
  const selectsAll =
    knownNames.length > 0 &&
    selected.length === knownNames.length &&
    selected.every((name) => known.has(name));
  return selectsAll ? "" : selected.join("\n");
}

export function toggleMixtureScope(
  value: string,
  name: string,
  knownNames: readonly string[],
): string {
  const scope = mixtureScopeSelection(value, knownNames);
  const next = scope.allByDefault
    ? new Set(knownNames)
    : new Set(scope.selected);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  return normalizeMixtureScope(next, knownNames);
}
