import type { ConvertPreflightInput, ConvertResponse } from "./api";
import {
  convertBundleHref,
  convertDonjonGuideHref,
  type ConvertDownstreamDestination,
} from "./convertNextSteps";

export type ConvertDeliveryStatus =
  | "done"
  | "ready"
  | "blocked"
  | "pending"
  | "skipped";

export interface ConvertDeliveryItem {
  id: "hdf5" | "gates" | "ascii" | "preview" | "bundle" | "donjon";
  label: string;
  title: string;
  body: string;
  status: ConvertDeliveryStatus;
  href?: string;
  action?: "convert";
}

export function convertDeliveryChecklist(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
  options?: { downstream?: ConvertDownstreamDestination | null },
): ConvertDeliveryItem[] {
  return [
    hdf5Item(data, input),
    gatesItem(data, input),
    asciiItem(data),
    previewItem(data),
    bundleItem(data),
    donjonItem(data, options?.downstream),
  ];
}

function hdf5Item(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): ConvertDeliveryItem {
  if (!input) {
    return {
      id: "hdf5",
      label: "HDF5",
      title: "Source inspection not run",
      body:
        "Open the HDF5 inspector or rerun with preflight to capture mixture and mesh evidence.",
      status: data.ok ? "ready" : "pending",
      href: `/inspect?path=${encodeURIComponent(data.input_path)}`,
    };
  }
  return {
    id: "hdf5",
    label: "HDF5",
    title: input.ok ? "Source HDF5 accepted" : "Source HDF5 has issues",
    body: input.ok
      ? `${input.mixtures ?? "?"} mixtures, ${input.energy_groups ?? "?"} groups, mesh ${input.energy_mesh_name ?? input.energy_mesh_id ?? "unknown"}.`
      : `${input.issues.length} issue(s) must be resolved before this handoff is production-ready.`,
    status: input.ok ? "done" : "blocked",
    href: `/inspect?path=${encodeURIComponent(data.input_path)}`,
  };
}

function gatesItem(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
): ConvertDeliveryItem {
  if (!data.preflight) {
    return {
      id: "gates",
      label: "Checks",
      title: "Production checks not run",
      body:
        "Enable Preflight (--check) and Production checks (--production) to record the Converter input-contract decision. Downstream SPH or project physics acceptance is a separate gate.",
      status: data.ok ? "skipped" : "pending",
    };
  }
  const warnings = input?.warnings.length ?? 0;
  return {
    id: "gates",
    label: "Checks",
    title: data.preflight_ok
      ? warnings > 0
        ? "Validation passed with warnings"
        : "Validation passed"
      : "Validation failed",
    body: data.preflight_ok
      ? `${data.preflight.decision}; ${warnings} warning(s) recorded for audit review.`
      : "Resolve failed validation or production checks before writing or packaging.",
    status: data.preflight_ok ? "done" : "blocked",
  };
}

function asciiItem(data: ConvertResponse): ConvertDeliveryItem {
  if (!data.ok) {
    return {
      id: "ascii",
      label: "ASCII",
      title: "No ASCII output",
      body: "The converter stopped before a valid output could be produced.",
      status: "blocked",
    };
  }
  if (data.dry_run) {
    return {
      id: "ascii",
      label: "ASCII",
      title: "Ready to write ASCII",
      body:
        "Dry run did not write a file. Run Convert to create the DONJON-facing artifact.",
      status: "ready",
      action: "convert",
    };
  }
  return {
    id: "ascii",
    label: "ASCII",
    title: data.output_exists ? "ASCII artifact written" : "ASCII artifact not confirmed",
    body: data.output_exists
      ? `${objectName(data)} exists at ${data.output_path}.`
      : "Conversion returned success, but the output file could not be confirmed.",
    status: data.output_exists ? "done" : "blocked",
  };
}

function previewItem(data: ConvertResponse): ConvertDeliveryItem {
  if (data.converted && data.output_exists) {
    return {
      id: "preview",
      label: "Preview",
      title: "ASCII preview available",
      body: "Review the signature, visible LCM block tree, and first lines below.",
      status: "ready",
      href: "#ascii-output-preview",
    };
  }
  return {
    id: "preview",
    label: "Preview",
    title: "Preview waits for output",
    body: "The text preview appears after a confirmed ASCII file exists.",
    status: data.ok ? "pending" : "blocked",
  };
}

function bundleItem(data: ConvertResponse): ConvertDeliveryItem {
  if (data.converted && data.output_exists) {
    return {
      id: "bundle",
      label: "Bundle",
      title: "Bundle builder is prefilled",
      body:
        "Package the MGXS HDF5, ASCII output, summaries, and logs into the manifest-backed bundle.",
      status: "ready",
      href: convertBundleHref(data),
    };
  }
  return {
    id: "bundle",
    label: "Bundle",
    title: "Bundle after conversion",
    body: "Packaging is useful once the ASCII output exists and has been reviewed.",
    status: data.ok ? "pending" : "blocked",
  };
}

function donjonItem(
  data: ConvertResponse,
  downstream?: ConvertDownstreamDestination | null,
): ConvertDeliveryItem {
  if (data.converted && data.output_exists) {
    return {
      id: "donjon",
      label: downstream ? "Project" : "DONJON",
      title: downstream?.title ?? "DONJON deck setup is available",
      body:
        downstream?.body ??
        "Open the DONJON guide to build a deck skeleton or ingest smoke for this ASCII output. This action does not claim downstream SPH or model-physics acceptance.",
      status: "ready",
      href: downstream?.href ?? convertDonjonGuideHref(data),
    };
  }
  return {
    id: "donjon",
    label: "DONJON",
    title: "DONJON consumes the ASCII",
    body: "The DONJON guide takes over once a confirmed ASCII output exists.",
    status: data.ok ? "pending" : "blocked",
  };
}

function objectName(data: ConvertResponse): string {
  return data.format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
}
