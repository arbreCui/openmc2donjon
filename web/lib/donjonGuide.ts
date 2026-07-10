export type DonjonGuideFormat = "multicompo" | "macrolib";
export type DonjonDeckGeometry = "car2d" | "car3d" | "hex";
export type DonjonDeckSolver = "diffusion" | "spn" | "snt";
export type DonjonDeckBoundary = "REFL" | "VOID";

export interface DonjonDeckOptions {
  mixtureCount: number;
  geometry: DonjonDeckGeometry;
  solver: DonjonDeckSolver;
  spnOrder: number;
  snOrder: number;
  hexSide: number;
  hexHeight: number;
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
  snOrder: 8,
  hexSide: 1.0,
  hexHeight: 10.0,
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

export interface DonjonBundleDefaultsLike {
  format?: string | null;
  ascii_path?: string | null;
  mixture_count?: number | null;
  summary_path?: string | null;
  summary_schema?: string | null;
  ok?: boolean | null;
  converted?: boolean | null;
  dry_run?: boolean | null;
  preflight_ok?: boolean | null;
  preflight_decision?: string | null;
  production_requested?: boolean | null;
}

export interface DonjonAsciiMismatch {
  artifactPath: string;
  summaryPath: string;
}

export type DonjonDeckChecklistTone = "ready" | "review" | "manual";

export interface DonjonDeckChecklistItem {
  id: string;
  title: string;
  body: string;
  tone: DonjonDeckChecklistTone;
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

export function donjonDeckChecklist(
  asciiPath: string,
  format: DonjonGuideFormat,
  options: Partial<DonjonDeckOptions> = {},
): DonjonDeckChecklistItem[] {
  const deck = normalizeDonjonDeckOptions(options);
  const trimmedPath = asciiPath.trim();
  const object = donjonObjectLabel(format);
  const solver =
    deck.solver === "spn"
      ? `SPN${deck.spnOrder}`
      : deck.solver === "snt"
        ? `SN${deck.snOrder}`
        : "diffusion";
  return [
    {
      id: "ascii-path",
      title: trimmedPath ? "ASCII path resolves from DONJON" : "Set the ASCII path",
      body: trimmedPath
        ? `The deck loads ${trimmedPath} as ${object}. Run DONJON from a directory where this path resolves, or make it absolute.`
        : `Enter the ${object} text file written by the converter before using the generated deck.`,
      tone: trimmedPath ? "ready" : "review",
    },
    format === "multicompo"
      ? {
          id: "ncr-mixtures",
          title: `NCR extracts ${deck.mixtureCount} mixture${deck.mixtureCount === 1 ? "" : "s"}`,
          body: `The skeleton uses NMIX ${deck.mixtureCount} and emits one NCR MIX line per extracted mixture. Match this count and MIX order to the exported mixture order (the mixture_names dataset of the handoff HDF5).`,
          tone: "ready",
        }
      : {
          id: "macrolib-direct",
          title: "MACROLIB is assigned directly",
          body: "The deck loads L_MACROLIB into MACRO without NCR. Geometry MIX numbers refer directly to macrolib mixture indices.",
          tone: "ready",
        },
    deck.geometry === "hex"
      ? {
          id: "geometry-map",
          title: "Check the HEXZ mixture map",
          body: `The HEXZ GEOM assigns MIX 1..${deck.mixtureCount}, one mixture per hex position, in multicompo order. Set SIDE to the real hexagon edge length in cm and MESHZ to the axial height before comparing physics.`,
          tone: "manual",
        }
      : {
          id: "geometry-map",
          title: "Replace the one-cell geometry",
          body:
            deck.mixtureCount > 1
              ? `The sample GEOM still maps only MIX 1. Replace it with the real ${deck.geometry.toUpperCase()} mesh and assign all ${deck.mixtureCount} mixture regions.`
              : `The sample GEOM is a one-cell smoke model. Replace it with the real ${deck.geometry.toUpperCase()} geometry before comparing physics.`,
          tone: "manual",
        },
    {
      id: "boundary-solver",
      title: `Confirm boundaries and ${solver} settings`,
      body:
        deck.geometry === "hex"
          ? `Hex boundaries are fixed: Z- REFL Z+ REFL with HBC COMPLETE VOID. Keep the ${solver} options aligned with the OpenMC reference problem.`
          : deck.geometry === "car3d"
            ? `Current boundaries are X- ${deck.xMinus}, X+ ${deck.xPlus}, Y- ${deck.yMinus}, Y+ ${deck.yPlus}, Z- ${deck.zMinus}, Z+ ${deck.zPlus}. Keep them aligned with the OpenMC reference problem.`
            : `Current boundaries are X- ${deck.xMinus}, X+ ${deck.xPlus}, Y- ${deck.yMinus}, Y+ ${deck.yPlus}. Keep them aligned with the OpenMC reference problem.`,
      tone: "review",
    },
    ...(deck.geometry === "hex"
      ? ([
          {
            id: "hex-ascii-72",
            title: "Keep the ASCII path under 72 characters",
            body: "DONJON truncates SEQ_ASCII ... FILE paths at 72 characters. Stage the ASCII handoff on a short absolute path before running the deck.",
            tone: "review",
          },
          {
            id: "hex-boundary-void",
            title: "Only VOID is validated on the hex outer boundary",
            body: "SNT hexagonal HBC COMPLETE REFL and ALBE 1.0 silently leak instead of reflecting; only VOID is validated for full-hex outer boundaries. White-boundary colorset decks cannot be validated in SNT.",
            tone: "review",
          },
        ] satisfies DonjonDeckChecklistItem[])
      : []),
    {
      id: "smoke-first",
      title: "Run the ingest smoke before the physics deck",
      body: "First run the small UTL:DUMP deck to prove the ASCII object is readable, then run the low-order solve skeleton after replacing the geometry block.",
      tone: "manual",
    },
  ];
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
    snOrder: numericParam(params.get("sn")),
    hexSide: numericParam(params.get("side")),
    hexHeight: numericParam(params.get("height")),
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
  const solverLabel =
    deck.solver === "spn"
      ? `SPN${deck.spnOrder}`
      : deck.solver === "snt"
        ? `SN${deck.snOrder}`
        : "DIFFUSION";
  const solverModules =
    deck.solver === "snt" ? "SNT: ASM: FLU:" : "TRIVAT: TRIVAA: FLUD:";
  const systemName = deck.solver === "snt" ? "SYSTEM" : "SYS";
  if (format === "macrolib") {
    return [
      `MODULE GEO: ${solverModules} GREP: END: ABORT: ;`,
      `LINKED_LIST MACRO GEOM TRACK ${systemName} FLUX ;`,
      "REAL keff ;",
      `SEQ_ASCII MACRO_ASC :: FILE '${path}' ;`,
      "",
      "MACRO := MACRO_ASC ;",
      "",
      ...lowOrderSkeletonLines(deck),
      ...solveLines(deck),
      `ECHO 'OPENMC2DONJON MACROLIB ${solverLabel} K-EFFECTIVE' keff ;`,
      "END: ;",
    ].join("\n");
  }
  return [
    `MODULE GEO: NCR: ${solverModules} GREP: END: ABORT: ;`,
    `LINKED_LIST CPO MACRO GEOM TRACK ${systemName} FLUX ;`,
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
    ...solveLines(deck),
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
  const geometry = normalizeGeometry(options.geometry);
  return {
    ...DEFAULT_DONJON_DECK_OPTIONS,
    ...options,
    mixtureCount: normalizeMixtureCount(options.mixtureCount),
    spnOrder: normalizeSpnOrder(options.spnOrder),
    snOrder: normalizeSnOrder(options.snOrder),
    hexSide: normalizeHexLength(
      options.hexSide,
      DEFAULT_DONJON_DECK_OPTIONS.hexSide,
    ),
    hexHeight: normalizeHexLength(
      options.hexHeight,
      DEFAULT_DONJON_DECK_OPTIONS.hexHeight,
    ),
    geometry,
    solver: normalizeSolver(options.solver, geometry),
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
  if (options.geometry === "hex") {
    return [
      "* Replace this geometry / tracking block with your low-order model.",
      `* The HEXZ GEOM below assigns MIX 1..${options.mixtureCount}, one mixture per hex position.`,
      "* The MIX order must match the multicompo mixture order (the",
      "* mixture_names dataset of the handoff HDF5).",
      "* SIDE is the hexagon edge length in cm.",
      ...geometryLines(options),
      ...trackingLines(options),
    ];
  }
  return [
    "* Replace this geometry / tracking block with your low-order model.",
    options.mixtureCount > 1
      ? `* The one-cell GEOM below references MIX 1 only; expand it to map all ${options.mixtureCount} mixtures.`
      : "* The one-cell GEOM below is only an ingest smoke model.",
    ...geometryLines(options),
    ...trackingLines(options),
  ];
}

function geometryLines(options: DonjonDeckOptions): string[] {
  if (options.geometry === "hex") {
    const splitl = options.solver === "snt" ? "  SPLITL 2" : "";
    return [
      `GEOM := GEO: :: HEXZ ${options.mixtureCount} 1 EDIT 0`,
      "  Z- REFL Z+ REFL  HBC COMPLETE VOID",
      `  SIDE ${formatCm(options.hexSide)}${splitl}`,
      `  MESHZ 0.0 ${formatCm(options.hexHeight)}`,
      "  MIX",
      ...hexMixNumberLines(options.mixtureCount),
      ";",
    ];
  }
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

function trackingLines(options: DonjonDeckOptions): string[] {
  if (options.solver === "snt") {
    return [
      "* SCAT is the scattering anisotropy order + 1 (P1 handoff -> SCAT 2).",
      `TRACK := SNT: GEOM :: EDIT 0 DIAM 1 SN ${options.snOrder} SCAT 2 ;`,
    ];
  }
  const spn = options.solver === "spn" ? ` SPN ${options.spnOrder} SCAT 1` : "";
  if (options.geometry === "hex") {
    return [`TRACK := TRIVAT: GEOM :: EDIT 1 MAXR 20000 MCFD 1${spn} ;`];
  }
  return [`TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1${spn} ;`];
}

function solveLines(options: DonjonDeckOptions): string[] {
  if (options.solver === "snt") {
    return [
      "SYSTEM := ASM: MACRO TRACK :: ARM ;",
      "FLUX := FLU: SYSTEM MACRO TRACK :: EDIT 1 TYPE K EXTE 500 1E-05 ;",
      "GREP: FLUX :: GETVAL 'K-EFFECTIVE' 1 >>keff<< ;",
    ];
  }
  if (options.geometry === "hex") {
    return [
      "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
      "FLUX := FLUD: SYS TRACK :: EDIT 1 ACCE 3 3 EXTE 1000 1E-05 ADI 6 ;",
      "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
    ];
  }
  return [
    "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
    "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
    "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
  ];
}

function hexMixNumberLines(mixtureCount: number): string[] {
  const lines: string[] = [];
  for (let start = 1; start <= mixtureCount; start += 10) {
    const numbers: string[] = [];
    for (let i = start; i <= Math.min(start + 9, mixtureCount); i += 1) {
      numbers.push(String(i));
    }
    lines.push(`  ${numbers.join(" ")}`);
  }
  return lines;
}

function formatCm(value: number): string {
  return Number.isInteger(value) ? value.toFixed(1) : String(value);
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

function normalizeSnOrder(value: number | undefined): number {
  if (!Number.isFinite(value)) return DEFAULT_DONJON_DECK_OPTIONS.snOrder;
  const order = Math.floor(Number(value));
  return order === 4 || order === 16 ? order : 8;
}

function normalizeHexLength(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value) || Number(value) <= 0) return fallback;
  return Number(value);
}

function normalizeGeometry(value: DonjonDeckGeometry | undefined): DonjonDeckGeometry {
  return value === "car3d" || value === "hex" ? value : "car2d";
}

function normalizeSolver(
  value: DonjonDeckSolver | undefined,
  geometry: DonjonDeckGeometry,
): DonjonDeckSolver {
  if (value === "snt") return geometry === "hex" ? "snt" : "diffusion";
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
  if (deck.solver === "snt" && deck.snOrder !== defaults.snOrder) {
    params.set("sn", String(deck.snOrder));
  }
  if (deck.geometry === "hex" && deck.hexSide !== defaults.hexSide) {
    params.set("side", String(deck.hexSide));
  }
  if (deck.geometry === "hex" && deck.hexHeight !== defaults.hexHeight) {
    params.set("height", String(deck.hexHeight));
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
  return value === "car3d" || value === "car2d" || value === "hex"
    ? value
    : undefined;
}

function deckSolverParam(value: string | null): DonjonDeckSolver | undefined {
  return value === "spn" || value === "diffusion" || value === "snt"
    ? value
    : undefined;
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

export function donjonDefaultsArtifact(
  defaults: DonjonBundleDefaultsLike | null | undefined,
): DonjonBundleArtifact | null {
  const asciiPath = defaults?.ascii_path?.trim() ?? "";
  if (!asciiPath) return null;
  return {
    label: "convert-summary",
    asciiPath,
    format: inferDonjonFormat(asciiPath, defaults?.format ?? undefined),
    bundledPath: null,
    ok: null,
    messages: [],
  };
}

export function donjonBundleAsciiMismatch(
  artifact: DonjonBundleArtifact | null,
  summaryArtifact: DonjonBundleArtifact | null,
): DonjonAsciiMismatch | null {
  if (!artifact || !summaryArtifact) return null;
  if (artifact.asciiPath === summaryArtifact.asciiPath) return null;
  return {
    artifactPath: artifact.asciiPath,
    summaryPath: summaryArtifact.asciiPath,
  };
}
