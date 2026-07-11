import type { BuilderValues } from "./commandBuilder";
import { donjonDeckFilename, donjonGuideHref } from "./donjonGuide";

export interface BundlePrefillStatus {
  prefilled: boolean;
  title: string;
  body: string;
  chips: string[];
  manifestPath?: string;
  validateHref?: string;
  donjonHref?: string;
}

const ARTIFACT_FIELDS = [
  ["mgxs", "MGXS HDF5"],
  ["mcompo", "MULTICOMPO"],
  ["macrolib", "MACROLIB"],
  ["run_summary", "conversion summary"],
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
  const manifestPath = bundleManifestPath(values.output_dir);
  const donjonHref = bundleDonjonGuideHref(values, manifestPath);
  if (fromConverter) {
    return {
      prefilled: true,
      title: "Prefilled from a converter result",
      body:
        "The MGXS source, DONJON ASCII output, and any conversion summary are already in the form. Review the bundle directory, copy the CLI, then run it locally to create the bundle.",
      chips: [...(hasOutputDir ? ["bundle directory"] : []), ...chips],
      manifestPath,
      validateHref: manifestPath ? validateBundleBuilderHref(manifestPath) : undefined,
      donjonHref,
    };
  }
  if (hasOutputDir || chips.length > 0) {
    return {
      prefilled: true,
      title: "Bundle builder has prefilled fields",
      body:
        "Some artifact paths came from the URL. Fill any remaining files you want in the bundle.",
      chips: [...(hasOutputDir ? ["bundle directory"] : []), ...chips],
      manifestPath,
      validateHref: manifestPath ? validateBundleBuilderHref(manifestPath) : undefined,
      donjonHref,
    };
  }
  return {
    prefilled: false,
    title: "Bundle artifacts after conversion",
    body:
      "Use this builder after the direct converter writes the DONJON ASCII output. The convert result can prefill MGXS, ASCII, and bundle paths for you.",
    chips: [],
  };
}

function hasValue(value: string | boolean | undefined): boolean {
  return typeof value === "string" && value.trim() !== "";
}

function bundleManifestPath(outputDir: string | boolean | undefined): string | undefined {
  if (!hasValue(outputDir)) return undefined;
  const dir = String(outputDir).trim();
  const normalized = dir === "/" ? dir : dir.replace(/\/+$/, "");
  return `${normalized}/manifest.json`;
}

function validateBundleBuilderHref(manifestPath: string): string {
  const params = new URLSearchParams({
    command: "validate-bundle",
    manifest: manifestPath,
  });
  return `/builder?${params.toString()}`;
}

function bundleDonjonGuideHref(
  values: BuilderValues,
  manifestPath: string | undefined,
): string | undefined {
  const macrolib = stringValue(values.macrolib);
  const mcompo = stringValue(values.mcompo);
  const asciiPath = macrolib ?? mcompo;
  if (!asciiPath) return undefined;
  return donjonGuideHref({
    asciiPath,
    format: macrolib ? "macrolib" : "multicompo",
    manifestPath,
    deckFilename: donjonDeckFilename(
      asciiPath,
      macrolib ? "macrolib" : "multicompo",
      "solve",
    ),
  });
}

function stringValue(value: string | boolean | undefined): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}
