export type DonjonGuideFormat = "multicompo" | "macrolib";
export type DonjonDeckGeometry = "car2d" | "car3d";
export type DonjonDeckSolver = "diffusion" | "spn";
export type DonjonDeckBoundary = "REFL" | "VOID";

export interface DonjonDeckOptions {
  mixtureCount: number;
  geometry: DonjonDeckGeometry;
  solver: DonjonDeckSolver;
  spnOrder: number;
  xMinus: DonjonDeckBoundary;
  xPlus: DonjonDeckBoundary;
  yMinus: DonjonDeckBoundary;
  yPlus: DonjonDeckBoundary;
  zMinus: DonjonDeckBoundary;
  zPlus: DonjonDeckBoundary;
}

export const DEFAULT_DONJON_DECK_OPTIONS: DonjonDeckOptions = {
  mixtureCount: 1,
  geometry: "car2d",
  solver: "diffusion",
  spnOrder: 3,
  xMinus: "REFL",
  xPlus: "VOID",
  yMinus: "REFL",
  yPlus: "VOID",
  zMinus: "REFL",
  zPlus: "VOID",
};

export interface DonjonGuideLinkInput {
  asciiPath?: string | null;
  format?: string | null;
  manifestPath?: string | null;
  deckFilename?: string | null;
  deckOptions?: Partial<DonjonDeckOptions> | null;
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
  if (input.deckFilename?.trim()) params.set("deck", input.deckFilename.trim());
  appendDonjonDeckParams(params, input.deckOptions ?? undefined);
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

export function donjonDeckFilename(
  asciiPath: string,
  format: DonjonGuideFormat,
  purpose: "ingest" | "solve" = "solve",
): string {
  const base = deckBaseName(asciiPath, format);
  return `${base}_donjon_${purpose}.x2m`;
}

export function donjonRunCommand(deckFilename: string): string {
  const filename = deckFilename.trim() || "openmc2donjon_donjon_solve.x2m";
  return `rdonjon ${shellQuote(filename)}`;
}

export interface DonjonDeckSearchParams {
  get(name: string): string | null;
}

export function donjonDeckOptionsFromSearchParams(
  params: DonjonDeckSearchParams,
): DonjonDeckOptions {
  return normalizeDonjonDeckOptions({
    mixtureCount: numericParam(params.get("nmix")),
    geometry: deckGeometryParam(params.get("geometry")),
    solver: deckSolverParam(params.get("solver")),
    spnOrder: numericParam(params.get("spn")),
    xMinus: deckBoundaryParam(params.get("xm")),
    xPlus: deckBoundaryParam(params.get("xp")),
    yMinus: deckBoundaryParam(params.get("ym")),
    yPlus: deckBoundaryParam(params.get("yp")),
    zMinus: deckBoundaryParam(params.get("zm")),
    zPlus: deckBoundaryParam(params.get("zp")),
  });
}

export function donjonIngestSnippet(
  asciiPath: string,
  format: DonjonGuideFormat,
  options: Partial<DonjonDeckOptions> = {},
): string {
  const path = asciiPath.trim() || placeholderAsciiPath(format);
  const deck = normalizeDonjonDeckOptions(options);
  const solverLabel = deck.solver === "spn" ? `SPN${deck.spnOrder}` : "DIFFUSION";
  if (format === "macrolib") {
    return [
      "MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;",
      "LINKED_LIST MACRO GEOM TRACK SYS FLUX ;",
      "REAL keff ;",
      `SEQ_ASCII MACRO_ASC :: FILE '${path}' ;`,
      "",
      "MACRO := MACRO_ASC ;",
      "",
      ...lowOrderSkeletonLines(deck),
      "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
      "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
      "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
      `ECHO 'OPENMC2DONJON MACROLIB ${solverLabel} K-EFFECTIVE' keff ;`,
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
    `MACRO := NCR: CPO :: EDIT 1 MACRO NMIX ${deck.mixtureCount}`,
    "  COMPO CPO CPO",
    ...ncrMixLines(deck.mixtureCount),
    ";",
    "",
    ...lowOrderSkeletonLines(deck),
    "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
    "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
    "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
    `ECHO 'OPENMC2DONJON MULTICOMPO ${solverLabel} K-EFFECTIVE' keff ;`,
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

export function normalizeDonjonDeckOptions(
  options: Partial<DonjonDeckOptions>,
): DonjonDeckOptions {
  return {
    ...DEFAULT_DONJON_DECK_OPTIONS,
    ...options,
    mixtureCount: normalizeMixtureCount(options.mixtureCount),
    spnOrder: normalizeSpnOrder(options.spnOrder),
    geometry: normalizeGeometry(options.geometry),
    solver: normalizeSolver(options.solver),
    xMinus: normalizeBoundary(
      options.xMinus,
      DEFAULT_DONJON_DECK_OPTIONS.xMinus,
    ),
    xPlus: normalizeBoundary(options.xPlus, DEFAULT_DONJON_DECK_OPTIONS.xPlus),
    yMinus: normalizeBoundary(
      options.yMinus,
      DEFAULT_DONJON_DECK_OPTIONS.yMinus,
    ),
    yPlus: normalizeBoundary(options.yPlus, DEFAULT_DONJON_DECK_OPTIONS.yPlus),
    zMinus: normalizeBoundary(
      options.zMinus,
      DEFAULT_DONJON_DECK_OPTIONS.zMinus,
    ),
    zPlus: normalizeBoundary(options.zPlus, DEFAULT_DONJON_DECK_OPTIONS.zPlus),
  };
}

function ncrMixLines(mixtureCount: number): string[] {
  return Array.from(
    { length: mixtureCount },
    (_, index) => `  MIX ${index + 1} USE ENDMIX`,
  );
}

function lowOrderSkeletonLines(options: DonjonDeckOptions): string[] {
  return [
    "* Replace this geometry / tracking block with your low-order model.",
    options.mixtureCount > 1
      ? `* The one-cell GEOM below references MIX 1 only; expand it to map all ${options.mixtureCount} mixtures.`
      : "* The one-cell GEOM below is only an ingest smoke model.",
    ...geometryLines(options),
    trackingLine(options),
  ];
}

function geometryLines(options: DonjonDeckOptions): string[] {
  if (options.geometry === "car3d") {
    return [
      "GEOM := GEO: :: CAR3D 1 1 1",
      `  EDIT 0 X- ${options.xMinus} X+ ${options.xPlus} Y- ${options.yMinus} Y+ ${options.yPlus} Z- ${options.zMinus} Z+ ${options.zPlus}`,
      "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 MESHZ 0.0 1.0 ;",
    ];
  }
  return [
    "GEOM := GEO: :: CAR2D 1 1",
    `  EDIT 0 X- ${options.xMinus} X+ ${options.xPlus} Y- ${options.yMinus} Y+ ${options.yPlus}`,
    "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 ;",
  ];
}

function trackingLine(options: DonjonDeckOptions): string {
  const spn = options.solver === "spn" ? ` SPN ${options.spnOrder} SCAT 1` : "";
  return `TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1${spn} ;`;
}

function normalizeMixtureCount(value: number | undefined): number {
  if (!Number.isFinite(value)) return DEFAULT_DONJON_DECK_OPTIONS.mixtureCount;
  return Math.min(999, Math.max(1, Math.floor(Number(value))));
}

function normalizeSpnOrder(value: number | undefined): number {
  if (!Number.isFinite(value)) return DEFAULT_DONJON_DECK_OPTIONS.spnOrder;
  const order = Math.floor(Number(value));
  return order === 5 ? 5 : 3;
}

function normalizeGeometry(value: DonjonDeckGeometry | undefined): DonjonDeckGeometry {
  return value === "car3d" ? "car3d" : "car2d";
}

function normalizeSolver(value: DonjonDeckSolver | undefined): DonjonDeckSolver {
  return value === "spn" ? "spn" : "diffusion";
}

function normalizeBoundary(
  value: DonjonDeckBoundary | undefined,
  fallback: DonjonDeckBoundary,
): DonjonDeckBoundary {
  if (value === "REFL" || value === "VOID") return value;
  return fallback;
}

function appendDonjonDeckParams(
  params: URLSearchParams,
  options: Partial<DonjonDeckOptions> | undefined,
) {
  if (!options) return;
  const deck = normalizeDonjonDeckOptions(options);
  const defaults = DEFAULT_DONJON_DECK_OPTIONS;
  if (deck.mixtureCount !== defaults.mixtureCount) {
    params.set("nmix", String(deck.mixtureCount));
  }
  if (deck.geometry !== defaults.geometry) params.set("geometry", deck.geometry);
  if (deck.solver !== defaults.solver) params.set("solver", deck.solver);
  if (deck.solver === "spn" && deck.spnOrder !== defaults.spnOrder) {
    params.set("spn", String(deck.spnOrder));
  }
  if (deck.xMinus !== defaults.xMinus) params.set("xm", deck.xMinus);
  if (deck.xPlus !== defaults.xPlus) params.set("xp", deck.xPlus);
  if (deck.yMinus !== defaults.yMinus) params.set("ym", deck.yMinus);
  if (deck.yPlus !== defaults.yPlus) params.set("yp", deck.yPlus);
  if (deck.zMinus !== defaults.zMinus) params.set("zm", deck.zMinus);
  if (deck.zPlus !== defaults.zPlus) params.set("zp", deck.zPlus);
}

function numericParam(value: string | null): number | undefined {
  if (value === null || value.trim() === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function deckGeometryParam(value: string | null): DonjonDeckGeometry | undefined {
  return value === "car3d" || value === "car2d" ? value : undefined;
}

function deckSolverParam(value: string | null): DonjonDeckSolver | undefined {
  return value === "spn" || value === "diffusion" ? value : undefined;
}

function deckBoundaryParam(value: string | null): DonjonDeckBoundary | undefined {
  return value === "REFL" || value === "VOID" ? value : undefined;
}

function deckBaseName(asciiPath: string, format: DonjonGuideFormat): string {
  const fallback = format === "macrolib" ? "openmc2donjon_macrolib" : "openmc2donjon_multicompo";
  const trimmed = asciiPath.trim();
  if (!trimmed) return fallback;
  const leaf = trimmed.split(/[\\/]/).filter(Boolean).at(-1) ?? "";
  const withoutKnownSuffix = leaf
    .replace(/\.txt$/i, "")
    .replace(/\.mcompo$/i, "")
    .replace(/\.macrolib$/i, "")
    .replace(/\.compo$/i, "")
    .replace(/\.mco$/i, "");
  return sanitizeFilename(withoutKnownSuffix) || fallback;
}

function sanitizeFilename(value: string): string {
  return value
    .replace(/[^A-Za-z0-9._-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^[._-]+|[._-]+$/g, "")
    .slice(0, 80);
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\\''")}'`;
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
