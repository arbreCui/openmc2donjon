import type { ConvertPreflightInput, ConvertResponse } from "./api";
import {
  donjonDeckFilename,
  donjonGuideHref,
} from "./donjonGuide";

export interface ConvertNextStep {
  id: string;
  label: string;
  title: string;
  body: string;
  href?: string;
  status: "ready" | "blocked" | "reference";
}

export interface ConvertDownstreamDestination {
  href: string;
  label: string;
  title: string;
  body: string;
}

export function convertObjectLabel(format: ConvertResponse["format"]): string {
  return format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
}

export function convertObjectDescription(format: ConvertResponse["format"]): string {
  if (format === "macrolib") {
    return "Direct one-state macrolib output for deterministic solver consumption.";
  }
  return "Mapped multicompo output for domain-wise mixtures and equivalence metadata.";
}

/**
 * Destinations that only build and copy a CLI command instead of executing
 * in-app. Buttons and links pointing there carry a small "CLI" marker so the
 * execute-to-copy boundary is announced at the point of click. DONJON is not
 * included because its page can now start the constrained local solver job.
 */
const COPY_CLI_DESTINATIONS = ["/builder", "/equivalence"] as const;

export function isCopyCliDestination(href: string): boolean {
  return COPY_CLI_DESTINATIONS.some(
    (prefix) =>
      href === prefix ||
      href.startsWith(`${prefix}?`) ||
      href.startsWith(`${prefix}/`) ||
      href.startsWith(`${prefix}#`),
  );
}

export function convertBundleHref(data: ConvertResponse): string {
  const params = new URLSearchParams({
    command: "bundle",
    output_dir: convertBundleOutputDir(data),
    mgxs: data.input_path,
  });
  if (data.format === "macrolib") {
    params.set("macrolib", data.output_path);
  } else {
    params.set("mcompo", data.output_path);
  }
  if (data.summary_written && data.summary_path) {
    params.set("run_summary", data.summary_path);
  }
  return `/builder?${params.toString()}`;
}

export function convertValidateBundleHref(data: ConvertResponse): string {
  const params = new URLSearchParams({
    command: "validate-bundle",
    manifest: convertBundleManifestPath(data),
  });
  return `/builder?${params.toString()}`;
}

/**
 * The DONJON guide works from the ASCII path directly; the optional bundle
 * manifest is threaded in only once a probe has confirmed it exists, so a
 * user who skips bundling never lands on a "manifest not found" warning.
 */
export function convertDonjonGuideHref(
  data: ConvertResponse,
  options?: { manifestConfirmed?: boolean },
): string {
  return donjonGuideHref({
    asciiPath: data.output_path,
    format: data.format,
    manifestPath: options?.manifestConfirmed
      ? convertBundleManifestPath(data)
      : null,
    deckFilename: donjonDeckFilename(data.output_path, data.format, "solve"),
  });
}

export function convertWriterCompareHref(data: ConvertResponse): string {
  const params = new URLSearchParams({
    input_h5: data.input_path,
    format: data.format,
    summary_json: siblingPath(data.output_path, "writer_compare.json"),
    keep_dir: siblingPath(data.output_path, "writer_compare"),
    output: data.output_path,
  });
  if (data.summary_path) params.set("receipt", data.summary_path);
  if (data.root_name) params.set("root_name", data.root_name);
  if (data.comment) params.set("comment", data.comment);
  if (data.burnup != null) params.set("burnup", String(data.burnup));
  if (data.h_factor_default != null) {
    params.set("h_factor_default", String(data.h_factor_default));
  }
  for (const mixture of data.mixtures ?? []) params.append("mixture", mixture);
  if (data.project_root) params.set("project", data.project_root);
  if (data.component_id) params.set("component", data.component_id);
  return `/pygan?${params.toString()}`;
}

export function convertBundleManifestPath(data: ConvertResponse): string {
  return `${withoutTrailingSlash(convertBundleOutputDir(data))}/manifest.json`;
}

export function convertBundleOutputDir(data: ConvertResponse): string {
  return siblingBundleDir(data.output_path);
}

function siblingBundleDir(outputPath: string): string {
  return siblingPath(outputPath, "bundle");
}

function siblingDir(outputPath: string): string {
  const trimmed = outputPath.trim();
  const index = trimmed.lastIndexOf("/");
  if (index <= 0) return ".";
  return trimmed.slice(0, index);
}

function siblingPath(outputPath: string, child: string): string {
  const dir = siblingDir(outputPath);
  return dir === "." ? child : `${dir}/${child}`;
}

function withoutTrailingSlash(path: string): string {
  const trimmed = path.trim();
  if (trimmed === "/" || trimmed === "") return trimmed || "bundle";
  return trimmed.replace(/\/+$/, "");
}

export function convertNextSteps(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
  options?: { downstream?: ConvertDownstreamDestination | null },
): ConvertNextStep[] {
  const inspectHref = `/inspect?path=${encodeURIComponent(data.input_path)}`;
  const objectLabel = convertObjectLabel(data.format);
  const objectDescription = convertObjectDescription(data.format);

  if (!data.ok) {
    return [
      {
        id: "fix",
        label: "Fix",
        title: "Resolve failed checks first",
        body:
          "The converter did not reach an acceptable handoff state. Review issues and warnings, then rerun a dry run before writing output.",
        status: "blocked",
      },
      {
        id: "inspect",
        label: "Inspect",
        title: "Open the MGXS HDF5",
        body: "Use the inspector to look at mixture layout, mesh identity, SPH/ADF coverage, and std_dev visibility.",
        href: inspectHref,
        status: "reference",
      },
    ];
  }

  if (data.dry_run) {
    return [
      {
        id: "write",
        label: "Write",
        title: "Run Convert when the checks look right",
        body:
          "Dry run did not write a file. Press Convert to create the ASCII output at the selected output path.",
        status: "ready",
      },
      {
        id: "inspect",
        label: "Inspect",
        title: "Review the source HDF5",
        body:
          "Open the inspected handoff if you need to drill into mixture metadata, spectra, scatter matrices, or production hints.",
        href: inspectHref,
        status: "reference",
      },
      {
        id: "object",
        label: objectLabel,
        title: `${objectLabel} will be generated`,
        body: objectDescription,
        status: "reference",
      },
    ];
  }

  // Canonical data-flow order: preview -> bundle -> DONJON. The bundle's
  // manifest is upstream input to the DONJON guide (donjon_defaults prefill).
  return [
    {
      id: "preview",
      label: "Preview",
      title: data.output_exists ? "Review the ASCII output" : "Output existence was not confirmed",
      body: data.output_exists
        ? "Scan the generated LCM ASCII signature, visible block tree, and first lines before handing it downstream."
        : "The converter reported success, but the web endpoint could not confirm the output file exists.",
      href: data.output_exists ? "#ascii-output-preview" : undefined,
      status: data.output_exists ? "ready" : "blocked",
    },
    ...(data.writer_backend === "pygan"
      ? [
          {
            id: "compare-writers",
            label: "Validate",
            title: "Compare PyGan and ASCII writers",
            body:
              "Build a semantic comparison command that regenerates this output with both writer backends and checks their LCM trees.",
            href: convertWriterCompareHref(data),
            status: "ready" as const,
          },
        ]
      : []),
    {
      id: "bundle",
      label: "Bundle",
      title: "Package the production record",
      body:
        "Use the bundle builder to collect the MGXS HDF5, ASCII output, summaries, and logs into the manifest-backed bundle.",
      href: convertBundleHref(data),
      status: "ready",
    },
    {
      id: "donjon",
      label: options?.downstream ? "Project" : objectLabel,
      title:
        options?.downstream?.title ??
        (data.format === "multicompo"
          ? "Connect this component library to its consumer"
          : `Inspect ${objectLabel} in DONJON`),
      body:
        options?.downstream?.body ??
        (data.format === "multicompo"
          ? `This is one converted component library. The project manifest—not Converter—decides how many such components exist, which domain a consumer imports, and how they are mapped. Output path: ${data.output_path}`
          : `${objectDescription} Output path: ${data.output_path}`),
      href: options?.downstream?.href ?? convertDonjonGuideHref(data),
      status: "ready",
    },
    {
      id: "inspect",
      label: "Inspect",
      title: input?.sph_calculations ? "Inspect SPH/ADF source metadata" : "Inspect source metadata",
      body:
        "Return to the HDF5 inspector when you need mixture-level evidence behind the generated ASCII object.",
      href: inspectHref,
      status: "reference",
    },
  ];
}
