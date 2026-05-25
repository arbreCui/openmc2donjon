import type { ConvertFormat } from "./api";

export interface ConvertModeReferenceItem {
  id: "dry-run" | "convert" | "review";
  label: string;
  title: string;
  body: string;
  emphasis: "safe" | "write" | "deliver";
}

export function convertModeReference(
  format: ConvertFormat,
): readonly ConvertModeReferenceItem[] {
  const object = format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
  return [
    {
      id: "dry-run",
      label: "No-write",
      title: "Dry run checks the handoff",
      body:
        "Validates the HDF5 contract, output path, and selected production " +
        "physics checks. It never creates or replaces an ASCII file.",
      emphasis: "safe",
    },
    {
      id: "convert",
      label: "Write",
      title: `Convert writes ${object}`,
      body:
        "Runs the same checks, then writes the DONJON-facing ASCII library at " +
        "the output path when the checks are acceptable.",
      emphasis: "write",
    },
    {
      id: "review",
      label: "Deliver",
      title: "Preview and bundle after writing",
      body:
        "Once the ASCII file exists, preview the LCM blocks and open the " +
        "bundle builder to package the source HDF5, output, summaries, and logs.",
      emphasis: "deliver",
    },
  ] as const;
}
