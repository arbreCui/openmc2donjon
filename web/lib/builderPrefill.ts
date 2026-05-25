import type { BuilderValues } from "./commandBuilder";

export interface BundlePrefillStatus {
  prefilled: boolean;
  title: string;
  body: string;
  chips: string[];
}

const ARTIFACT_FIELDS = [
  ["mgxs", "MGXS HDF5"],
  ["mcompo", "MULTICOMPO"],
  ["macrolib", "MACROLIB"],
  ["run_summary", "run summary"],
  ["check_summary", "check summary"],
  ["inspect_summary", "inspect summary"],
  ["doctor_summary", "doctor summary"],
  ["diff_summary", "diff summary"],
  ["extra", "extra artifacts"],
] as const;

export function bundlePrefillStatus(values: BuilderValues): BundlePrefillStatus {
  const chips = ARTIFACT_FIELDS.flatMap(([field, label]) =>
    hasValue(values[field]) ? [label] : [],
  );
  const hasOutputDir = hasValue(values.output_dir);
  const hasAscii = hasValue(values.mcompo) || hasValue(values.macrolib);
  const fromConverter = hasValue(values.mgxs) && hasAscii;
  if (fromConverter) {
    return {
      prefilled: true,
      title: "Prefilled from a converter result",
      body:
        "The MGXS source and DONJON ASCII handoff are already in the form. Review the bundle directory, copy the CLI, then run it locally to create the delivery record.",
      chips: ["bundle directory", ...chips],
    };
  }
  if (hasOutputDir || chips.length > 0) {
    return {
      prefilled: true,
      title: "Bundle builder has prefilled fields",
      body:
        "Some artifact paths came from the URL. Fill any remaining files you want in the manifest-backed delivery bundle.",
      chips: [...(hasOutputDir ? ["bundle directory"] : []), ...chips],
    };
  }
  return {
    prefilled: false,
    title: "Bundle artifacts after conversion",
    body:
      "Use this builder after the direct converter writes an ASCII handoff. The convert result can prefill MGXS, ASCII, and bundle paths for you.",
    chips: [],
  };
}

function hasValue(value: string | boolean | undefined): boolean {
  return typeof value === "string" && value.trim() !== "";
}
