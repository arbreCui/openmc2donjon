export type DonjonGuideFormat = "multicompo" | "macrolib";

export interface DonjonGuideLinkInput {
  asciiPath?: string | null;
  format?: string | null;
  manifestPath?: string | null;
}

export interface DonjonBundleArtifactLike {
  label: string;
  path: string;
  bundled_path?: string | null;
  ok?: boolean;
  messages?: string[];
}

export interface DonjonBundleArtifact {
  label: string;
  asciiPath: string;
  format: DonjonGuideFormat;
  bundledPath: string | null;
  ok: boolean | null;
  messages: string[];
}

export function donjonGuideHref(input: DonjonGuideLinkInput): string {
  const params = new URLSearchParams();
  if (input.asciiPath?.trim()) params.set("ascii", input.asciiPath.trim());
  const format = inferDonjonFormat(input.asciiPath ?? "", input.format ?? undefined);
  params.set("format", format);
  if (input.manifestPath?.trim()) params.set("manifest", input.manifestPath.trim());
  const query = params.toString();
  return query ? `/donjon?${query}` : "/donjon";
}

export function inferDonjonFormat(
  asciiPath: string,
  explicit?: string | null,
): DonjonGuideFormat {
  if (explicit === "macrolib" || explicit === "multicompo") return explicit;
  const lowered = asciiPath.toLowerCase();
  if (lowered.includes("macrolib") || lowered.endsWith(".macrolib.txt")) {
    return "macrolib";
  }
  return "multicompo";
}

export function donjonObjectLabel(format: DonjonGuideFormat): string {
  return format === "macrolib" ? "L_MACROLIB" : "L_MULTICOMPO";
}

export function donjonShortName(format: DonjonGuideFormat): string {
  return format === "macrolib" ? "MACROLIB" : "MULTICOMPO";
}

export function donjonIngestSnippet(
  asciiPath: string,
  format: DonjonGuideFormat,
): string {
  const path = asciiPath.trim() || placeholderAsciiPath(format);
  if (format === "macrolib") {
    return [
      "MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;",
      "LINKED_LIST MACRO GEOM TRACK SYS FLUX ;",
      "REAL keff ;",
      `SEQ_ASCII MACRO_ASC :: FILE '${path}' ;`,
      "",
      "MACRO := MACRO_ASC ;",
      "",
      "* Replace this geometry / tracking block with your low-order model.",
      "GEOM := GEO: :: CAR2D 1 1",
      "  EDIT 0 X- REFL X+ VOID Y- REFL Y+ VOID",
      "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 ;",
      "TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1 ;",
      "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
      "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
      "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
      "ECHO 'OPENMC2DONJON MACROLIB K-EFFECTIVE' keff ;",
      "END: ;",
    ].join("\n");
  }
  return [
    "MODULE GEO: NCR: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;",
    "LINKED_LIST CPO MACRO GEOM TRACK SYS FLUX ;",
    "REAL keff ;",
    `SEQ_ASCII CPO_ASC :: FILE '${path}' ;`,
    "",
    "CPO := CPO_ASC ;",
    "MACRO := NCR: CPO :: EDIT 1 MACRO NMIX <number_of_mixtures>",
    "  COMPO CPO CPO",
    "  MIX 1 USE ENDMIX",
    "  MIX 2 USE ENDMIX",
    "  * ...repeat MIX lines for the mixture indices used by GEOM...",
    ";",
    "",
    "* Replace this geometry / tracking block with your low-order model.",
    "GEOM := GEO: :: CAR2D 1 1",
    "  EDIT 0 X- REFL X+ VOID Y- REFL Y+ VOID",
    "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 ;",
    "TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1 ;",
    "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
    "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
    "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
    "ECHO 'OPENMC2DONJON MULTICOMPO K-EFFECTIVE' keff ;",
    "END: ;",
  ].join("\n");
}

export function donjonIngestOnlySnippet(
  asciiPath: string,
  format: DonjonGuideFormat,
): string {
  const path = asciiPath.trim() || placeholderAsciiPath(format);
  if (format === "macrolib") {
    return [
      "MODULE UTL: END: ABORT: ;",
      "LINKED_LIST MACRO ;",
      `SEQ_ASCII MACRO_ASC :: FILE '${path}' ;`,
      "MACRO := MACRO_ASC ;",
      "UTL: MACRO :: DUMP ;",
      "END: ;",
    ].join("\n");
  }
  return [
    "MODULE UTL: END: ABORT: ;",
    "LINKED_LIST CPO ;",
    `SEQ_ASCII CPO_ASC :: FILE '${path}' ;`,
    "CPO := CPO_ASC ;",
    "UTL: CPO :: DUMP ;",
    "END: ;",
  ].join("\n");
}

export function placeholderAsciiPath(format: DonjonGuideFormat): string {
  return format === "macrolib" ? "out.macrolib.txt" : "out.mcompo.txt";
}

export function findDonjonBundleArtifact(
  artifacts: readonly DonjonBundleArtifactLike[],
): DonjonBundleArtifact | null {
  const candidates = artifacts
    .map((artifact, index) => {
      const match = classifyDonjonArtifact(artifact);
      if (match === null) return null;
      return {
        artifact,
        format: match.format,
        score: match.score + (artifact.ok === false ? 0 : 2) - index * 0.001,
      };
    })
    .filter((candidate) => candidate !== null);

  if (!candidates.length) return null;
  const best = candidates.reduce((left, right) =>
    right.score > left.score ? right : left,
  );
  return {
    label: best.artifact.label,
    asciiPath: best.artifact.path,
    format: best.format,
    bundledPath: best.artifact.bundled_path ?? null,
    ok: typeof best.artifact.ok === "boolean" ? best.artifact.ok : null,
    messages: Array.isArray(best.artifact.messages)
      ? best.artifact.messages
      : [],
  };
}

function classifyDonjonArtifact(
  artifact: DonjonBundleArtifactLike,
): { format: DonjonGuideFormat; score: number } | null {
  const label = artifact.label.toLowerCase();
  const path = artifact.path.toLowerCase();
  const bundled = (artifact.bundled_path ?? "").toLowerCase();
  const haystack = `${label} ${path} ${bundled}`;

  if (label === "macrolib" || label === "macro") {
    return { format: "macrolib", score: 100 };
  }
  if (label === "mcompo" || label === "multicompo" || label === "compo") {
    return { format: "multicompo", score: 100 };
  }
  if (
    path.endsWith(".macrolib.txt") ||
    bundled.endsWith(".macrolib.txt") ||
    haystack.includes("macrolib")
  ) {
    return { format: "macrolib", score: 70 };
  }
  if (
    path.endsWith(".mcompo.txt") ||
    bundled.endsWith(".mcompo.txt") ||
    path.endsWith(".compo.txt") ||
    bundled.endsWith(".compo.txt") ||
    haystack.includes("multicompo") ||
    haystack.includes("mcompo")
  ) {
    return { format: "multicompo", score: 70 };
  }
  return null;
}
