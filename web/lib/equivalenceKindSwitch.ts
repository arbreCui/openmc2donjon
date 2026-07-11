import {
  EquivalenceCommandOptions,
  EquivalenceKind,
  defaultEquivalenceOptions,
} from "./equivalenceCommand";

/**
 * Options state for an equivalence tab switch: every per-kind field
 * (output filename, modes, clips, summary JSON, force-overwrite) resets
 * to the incoming kind's defaults so the CLI preview cannot keep
 * targeting the previous tool's artifact; only genuinely shared fields
 * (the input MGXS path) carry over.
 *
 * One deliberate carry-over across the make/augment pairing: switching
 * from a make kind to its augment sibling seeds the sidecar source from
 * the make tab's configured output, so the path the user just configured
 * does not need to be hand-copied thirty seconds later.
 */
export function equivalenceOptionsForKindSwitch(
  current: EquivalenceCommandOptions,
  kind: EquivalenceKind,
): EquivalenceCommandOptions {
  const next = { ...defaultEquivalenceOptions(kind), inputH5: current.inputH5 };
  const makeOutput = current.outputPath.trim();
  if (makeOutput !== "") {
    if (current.kind === "adf-sidecar" && kind === "augment-adf") {
      next.adfSource = makeOutput;
    } else if (
      (current.kind === "openmc-sph-sidecar" || current.kind === "sph-sidecar") &&
      kind === "augment-sph"
    ) {
      next.sphSource = makeOutput;
    }
  }
  return next;
}
