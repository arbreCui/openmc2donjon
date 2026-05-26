import type { ConvertResponse } from "./api";
import {
  convertBundleHref,
  convertDonjonGuideHref,
  convertWriterCompareHref,
} from "./convertNextSteps";

export interface ConvertPostWriteFocus {
  badge: string;
  title: string;
  body: string;
  primaryLabel: string;
  primaryHref: string;
  secondaryLabel: string;
  secondaryHref: string;
}

export function convertPostWriteFocus(
  data: ConvertResponse,
): ConvertPostWriteFocus | null {
  if (!(data.converted && data.output_exists)) return null;
  if (data.writer_backend === "pygan") {
    return {
      badge: "optional backend evidence",
      title: "Validate the PyGan writer against the default ASCII writer",
      body:
        "This handoff was serialized through PyGan. Before delivery, run the " +
        "writer comparison to regenerate the same LCM tree with both backends " +
        "and compare their semantic payloads.",
      primaryLabel: "Validate PyGan comparison",
      primaryHref: convertWriterCompareHref(data),
      secondaryLabel: "Bundle handoff",
      secondaryHref: convertBundleHref(data),
    };
  }
  return {
    badge: "default production path",
    title: "Review the ASCII file, bundle it, then open the DONJON guide",
    body:
      "This is the normal converter route. The built-in ASCII writer created " +
      "the DONJON-facing handoff; preview the LCM text, package the evidence, " +
      "then prepare the downstream DONJON input card.",
    primaryLabel: "Bundle handoff",
    primaryHref: convertBundleHref(data),
    secondaryLabel: "Open DONJON guide",
    secondaryHref: convertDonjonGuideHref(data),
  };
}
