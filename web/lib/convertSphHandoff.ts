import type { ConvertPreflightInput, ConvertResponse } from "./api";

export interface ConvertSphHandoffStatus {
  title: string;
  badge: string;
  tone: "ready" | "warn";
  source: string;
  output: string;
  validation: string;
  nextAction: string;
}

export function convertSphHandoffStatus(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): ConvertSphHandoffStatus | null {
  const sph = input?.sph_calculations ?? 0;
  if (sph <= 0) return null;

  const macrolib = data.format === "macrolib";
  const converted = data.converted && data.output_exists;
  return {
    title: "SPH handoff detected",
    badge: macrolib ? "MACROLIB NSPH route" : "Review output format",
    tone: macrolib ? "ready" : "warn",
    source: `${sph} SPH calculation${sph === 1 ? "" : "s"} found in the SPH-augmented HDF5 handoff.`,
    output: macrolib
      ? "L_MACROLIB writes DONJON GROUP/*/NSPH blocks, the currently validated consume route."
      : "L_MULTICOMPO can carry equivalence metadata, but the validated DONJON NSPH consume smoke uses L_MACROLIB.",
    validation: data.preflight_ok
      ? "Dry-run checks passed for the SPH-bearing HDF5 contract."
      : "Resolve preflight issues before treating this as an SPH delivery artifact.",
    nextAction: converted
      ? "Preview the ASCII, then use the DONJON guide or package the bundle."
      : data.dry_run && data.ok
        ? macrolib
          ? "Run Convert to write the NSPH-bearing ASCII output."
          : "Run Convert only if you want the MULTICOMPO archive: its NSPH records ride along as inert metadata that DONJON NCR: does not consume. For DONJON consumption, switch to MACROLIB (DSPH: + MAC:) or pre-apply SPH with apply-sph."
        : "Run a production dry run before writing the final output.",
  };
}

