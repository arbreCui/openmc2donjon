import type { ConvertPreflightInput, ConvertResponse } from "./api";

export interface ConvertNextStep {
  id: string;
  label: string;
  title: string;
  body: string;
  href?: string;
  status: "ready" | "blocked" | "reference";
}

export function convertObjectLabel(format: ConvertResponse["format"]): string {
  return format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
}

export function convertObjectDescription(format: ConvertResponse["format"]): string {
  if (format === "macrolib") {
    return "Direct one-state macrolib handoff for deterministic solver consumption.";
  }
  return "Mapped multicompo handoff for domain-wise mixtures and equivalence metadata.";
}

export function convertNextSteps(
  data: ConvertResponse,
  input: ConvertPreflightInput | null,
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
          "The converter did not reach an acceptable handoff state. Review issues and warnings, then rerun dry-run before writing output.",
        status: "blocked",
      },
      {
        id: "inspect",
        label: "Inspect",
        title: "Open the input HDF5",
        body: "Use the inspector to look at mixture layout, mesh identity, ADF/SPH coverage, and std_dev visibility.",
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
        title: "Run Convert when the gates look right",
        body:
          "Dry-run did not write a file. Press Convert to create the ASCII handoff at the selected output path.",
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

  return [
    {
      id: "preview",
      label: "Preview",
      title: data.output_exists ? "Review the ASCII handoff" : "Output existence was not confirmed",
      body: data.output_exists
        ? "Scan the generated LCM ASCII signature, visible block tree, and first lines before handing it downstream."
        : "The converter reported success, but the web endpoint could not confirm the output file exists.",
      href: data.output_exists ? "#ascii-output-preview" : undefined,
      status: data.output_exists ? "ready" : "blocked",
    },
    {
      id: "donjon",
      label: objectLabel,
      title: `Use ${objectLabel} in DONJON`,
      body: `${objectDescription} Output path: ${data.output_path}`,
      status: "ready",
    },
    {
      id: "bundle",
      label: "Bundle",
      title: "Package the production record",
      body:
        "Use the bundle builder to collect the input HDF5, ASCII output, summaries, and logs into a manifest-backed handoff.",
      href: `/builder?command=bundle&input=${encodeURIComponent(data.input_path)}`,
      status: "reference",
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
