import type { ConvertResponse } from "./api";

/**
 * Backend-aware headline for the post-write delivery station ("Deliver to
 * DONJON" card). The card's own button row carries the actions, so this
 * module only supplies the copy; DONJON is the default-branch primary.
 */
export interface ConvertPostWriteFocus {
  badge: string;
  title: string;
  body: string;
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
        "This output was serialized through PyGan. Before delivery, run the " +
        "writer comparison to regenerate the same LCM tree with both backends " +
        "and compare their semantic payloads.",
    };
  }
  return {
    badge: "default production route",
    title: "Review the ASCII file, then prepare the DONJON input card",
    body:
      "This is the normal converter route. The built-in ASCII writer created " +
      "the DONJON-facing output; preview the LCM text, then prepare the " +
      "downstream DONJON input card.",
  };
}
