import type { ConvertResponse } from "./api";
import { convertObjectDescription, convertObjectLabel } from "./convertNextSteps";
import { fileStatusIsFile, type FileStatusState } from "./fileStatus";

export type ConvertAsciiReadinessTone = "ready" | "write" | "warn" | "blocked";

export interface ConvertAsciiReadiness {
  tone: ConvertAsciiReadinessTone;
  label: string;
  title: string;
  body: string;
  next: string;
  objectLabel: string;
  objectDescription: string;
  previewAvailable: boolean;
}

export function convertAsciiReadiness(
  data: ConvertResponse,
  outputStatus?: FileStatusState,
): ConvertAsciiReadiness {
  const objectLabel = convertObjectLabel(data.format);
  const objectDescription = convertObjectDescription(data.format);
  const outputKnownFile = fileStatusIsFile(outputStatus);
  const outputKnownMissing =
    outputStatus?.kind === "ok" &&
    (!outputStatus.status.exists || outputStatus.status.kind === "missing");

  if (!data.ok) {
    return {
      tone: "blocked",
      label: "blocked",
      title: "No ASCII handoff is ready",
      body:
        "The converter stopped before producing a valid DRAGON/DONJON ASCII artifact.",
      next: "Review the failed checks, fix the input or options, then rerun a dry run.",
      objectLabel,
      objectDescription,
      previewAvailable: false,
    };
  }

  if (data.dry_run) {
    if (data.output_exists || outputKnownFile) {
      return {
        tone: "warn",
        label: "target exists",
        title: "Dry run passed, but the target path already exists",
        body:
          "Dry run did not write a file. Convert can overwrite this target only when the overwrite option is enabled.",
        next: "Confirm the path is the intended artifact, then run Convert with overwrite if replacement is intended.",
        objectLabel,
        objectDescription,
        previewAvailable: false,
      };
    }
    return {
      tone: "write",
      label: "ready to write",
      title: `${objectLabel} will be written by Convert`,
      body:
        "Dry run passed without writing the ASCII file. The preview appears only after Convert creates the artifact.",
      next: "Run Convert to create the DONJON-facing text handoff, then review the preview below.",
      objectLabel,
      objectDescription,
      previewAvailable: false,
    };
  }

  if (data.converted && data.output_exists && !outputKnownMissing) {
    return {
      tone: "ready",
      label: "artifact ready",
      title: `${objectLabel} ASCII is ready for review`,
      body:
        "The converter wrote the ASCII handoff. The preview below checks the signature, visible LCM block tree, and first lines before downstream use.",
      next: "Review the preview, copy the path or CLI record, then bundle the handoff for DONJON-side consumption.",
      objectLabel,
      objectDescription,
      previewAvailable: true,
    };
  }

  if (data.converted && data.output_exists) {
    // The convert response reported a successful write, but the
    // file-status probe positively reports the file missing.
    return {
      tone: "warn",
      label: "verify path",
      title: "ASCII was written this session, but the file-status probe disagrees",
      body:
        "Convert reported a successful ASCII write, while the file-status probe does not see a file at the target path — check the path.",
      next: "Check the output path, then refresh file status before delivering the handoff.",
      objectLabel,
      objectDescription,
      previewAvailable: false,
    };
  }

  return {
    tone: "warn",
    label: "not confirmed",
    title: "Conversion returned, but the ASCII file is not confirmed",
    body:
      "The response did not confirm a readable output file at the target path, so the preview cannot be trusted yet.",
    next: "Refresh file status, check filesystem permissions, or rerun Convert after confirming the output directory.",
    objectLabel,
    objectDescription,
    previewAvailable: false,
  };
}
