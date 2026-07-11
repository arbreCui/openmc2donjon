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
 */
export function equivalenceOptionsForKindSwitch(
  current: EquivalenceCommandOptions,
  kind: EquivalenceKind,
): EquivalenceCommandOptions {
  return { ...defaultEquivalenceOptions(kind), inputH5: current.inputH5 };
}
