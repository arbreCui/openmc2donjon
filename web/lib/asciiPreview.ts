import type { ConvertFormat, ConvertPreflightInput } from "./api";
import { convertArtifactAnatomy } from "./convertArtifactAnatomy";

export type DonjonAsciiFormat = "MULTICOMPO" | "MACROLIB" | "unknown";

export interface BlockHit {
  id: string;
  label: string;
  present: boolean;
}

export type KeyBlockStatus = "present" | "partial" | "missing" | "optional";

export interface KeyBlockSummary {
  id: string;
  label: string;
  status: KeyBlockStatus;
  detail: string;
}

export interface ExpectedBlockCoverage {
  id: string;
  title: string;
  presentCount: number;
  totalCount: number;
  hits: BlockHit[];
}

export interface LcmBlockPreview {
  id: string;
  level: number;
  type: number;
  count: number;
  name: string;
}

export interface AsciiPreviewAnalysis {
  format: DonjonAsciiFormat;
  signature: string | null;
  likelyDonjonAscii: boolean;
  keyBlocks: KeyBlockSummary[];
  blockHits: BlockHit[];
  blockTree: LcmBlockPreview[];
  blockTreeTruncated: boolean;
  notes: string[];
}

const MULTICOMPO_SIGNATURE = "L_MULTICOMPO";
const MACROLIB_SIGNATURE = "L_MACROLIB";
const MAX_BLOCK_TREE_ITEMS = 18;
const BLOCK_HEADER_RE = /^\s*->\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+<-/;

export function analyzeDonjonAsciiPreview(
  text: string,
  options?: { truncated?: boolean },
): AsciiPreviewAnalysis {
  const truncated = options?.truncated ?? true;
  const lineSet = normalizedLineSet(text);
  const signature = signatureFromText(text);
  const format = formatFromSignature(signature);
  const allBlocks = parseLcmBlocks(text);
  const blockTree = allBlocks.slice(0, MAX_BLOCK_TREE_ITEMS);
  const keyBlocks = keyBlockSummary({ lineSet, signature, format, truncated });
  const blockHits = [
    blockHit("signature", "SIGNATURE", lineSet.has("SIGNATURE")),
    blockHit("state", "STATE-VECTOR", lineSet.has("STATE-VECTOR")),
    blockHit("mixtures", "MIXTURES", lineSet.has("MIXTURES")),
    blockHit(
      "macro-xs",
      "macro XS",
      ["NTOT0", "NUSIGF", "CHI", "H-FACTOR", "OVERV"].some((name) =>
        lineSet.has(name),
      ),
    ),
    blockHit(
      "scatter",
      "scatter sparse",
      ["NJJS00", "IJJS00", "SCAT00"].every((name) => lineSet.has(name)),
    ),
    blockHit("energy", "ENERGY", lineSet.has("ENERGY")),
  ];
  const likelyDonjonAscii =
    signature === MULTICOMPO_SIGNATURE || signature === MACROLIB_SIGNATURE;
  return {
    format,
    signature,
    likelyDonjonAscii,
    keyBlocks,
    blockHits,
    blockTree,
    blockTreeTruncated: allBlocks.length > blockTree.length,
    notes: analysisNotes({ signature, likelyDonjonAscii, blockHits, truncated }),
  };
}

function keyBlockSummary({
  lineSet,
  signature,
  format,
  truncated,
}: {
  lineSet: ReadonlySet<string>;
  signature: string | null;
  format: DonjonAsciiFormat;
  truncated: boolean;
}): KeyBlockSummary[] {
  const scatBlocks = matchingLines(lineSet, /^SCAT\d+$/);
  const njjsBlocks = matchingLines(lineSet, /^NJJS\d+$/);
  const ijjsBlocks = matchingLines(lineSet, /^IJJS\d+$/);
  const scatterTripletVisible =
    scatBlocks.length > 0 && njjsBlocks.length > 0 && ijjsBlocks.length > 0;
  const scatterPartiallyVisible =
    scatBlocks.length > 0 || njjsBlocks.length > 0 || ijjsBlocks.length > 0;
  const adfBlocks = ["ADF", "HADF"].filter((name) => lineSet.has(name));
  const hasSph = lineSet.has("NSPH");

  return [
    {
      id: "signature",
      label: "Signature",
      status:
        signature === MULTICOMPO_SIGNATURE || signature === MACROLIB_SIGNATURE
          ? "present"
          : "missing",
      detail:
        signature === MULTICOMPO_SIGNATURE || signature === MACROLIB_SIGNATURE
          ? `${signature} (${format})`
          : "Top-level L_MULTICOMPO / L_MACROLIB was not visible.",
    },
    {
      id: "state-vector",
      label: "State vector",
      status: lineSet.has("STATE-VECTOR") ? "present" : "missing",
      detail: lineSet.has("STATE-VECTOR")
        ? "Library dimensions and DONJON metadata are visible."
        : "STATE-VECTOR was not visible in this preview slice.",
    },
    {
      id: "energy",
      label: "Energy grid",
      status: lineSet.has("ENERGY") ? "present" : "missing",
      detail: lineSet.has("ENERGY")
        ? "ENERGY boundaries are visible for group interpretation."
        : truncated
          ? "ENERGY was not visible in this preview slice."
          : "ENERGY is absent from this file.",
    },
    {
      id: "total-xs",
      label: "Total XS",
      status: lineSet.has("NTOT0") ? "present" : "missing",
      detail: lineSet.has("NTOT0")
        ? "NTOT0 total macroscopic cross section is visible."
        : "NTOT0 was not visible in this preview slice.",
    },
    {
      id: "scatter",
      label: "Scattering",
      status: scatterTripletVisible
        ? "present"
        : scatterPartiallyVisible
          ? "partial"
          : "missing",
      detail: scatterTripletVisible
        ? `Sparse triplet visible: ${summarizeBlockNames([
            ...njjsBlocks,
            ...ijjsBlocks,
            ...scatBlocks,
          ])}.`
        : scatterPartiallyVisible
          ? "Only part of NJJSxx / IJJSxx / SCATxx is visible."
          : "Sparse scattering triplet was not visible.",
    },
    {
      id: "adf",
      label: "ADF / DF",
      status: adfBlocks.length > 0 ? "present" : "optional",
      detail: adfBlocks.length > 0
        ? `${adfBlocks.join(" + ")} equivalence factor block visible.`
        : "No ADF/HADF block visible; this may be a direct or SPH-only handoff.",
    },
    {
      id: "sph",
      label: "SPH",
      status: hasSph ? "present" : "optional",
      detail: hasSph
        ? "NSPH equivalence factors are visible."
        : "No NSPH block visible; this may be direct or ADF-only.",
    },
  ];
}

export function expectedArtifactBlockCoverage(
  text: string,
  format: ConvertFormat,
  input: ConvertPreflightInput | null,
): ExpectedBlockCoverage[] {
  const lineSet = normalizedLineSet(text);
  return convertArtifactAnatomy(format, input).sections.map((section) => {
    const hits = expectedBlocksForCoverage(section.blocks, input).map((block) =>
      blockHit(block, block, expectedBlockIsVisible(block, lineSet)),
    );
    return {
      id: section.id,
      title: section.title,
      presentCount: hits.filter((hit) => hit.present).length,
      totalCount: hits.length,
      hits,
    };
  });
}

function expectedBlocksForCoverage(
  blocks: readonly string[],
  input: ConvertPreflightInput | null,
): string[] {
  const adfExpected = input == null || (input.adf_faces?.length ?? 0) > 0;
  const sphExpected = input == null || (input.sph_calculations ?? 0) > 0;
  return blocks.filter((block) => {
    if (block === "ADF/HADF") return adfExpected;
    if (block === "NSPH") return sphExpected;
    return true;
  });
}

function expectedBlockIsVisible(block: string, lineSet: ReadonlySet<string>): boolean {
  if (block === "ADF/HADF") return lineSet.has("ADF") || lineSet.has("HADF");
  if (block.endsWith("xx")) {
    const prefix = block.slice(0, -2);
    return [...lineSet].some((line) => new RegExp(`^${prefix}\\d+$`).test(line));
  }
  return lineSet.has(block);
}

function matchingLines(lineSet: ReadonlySet<string>, pattern: RegExp): string[] {
  return [...lineSet].filter((line) => pattern.test(line)).sort();
}

function summarizeBlockNames(names: readonly string[]): string {
  const unique = [...new Set(names)].sort();
  if (unique.length <= 4) return unique.join(", ");
  return `${unique.slice(0, 4).join(", ")} + ${unique.length - 4} more`;
}

function parseLcmBlocks(text: string): LcmBlockPreview[] {
  const lines = text.split(/\r?\n/);
  const blocks: LcmBlockPreview[] = [];
  for (let index = 0; index < lines.length - 1; index += 1) {
    const match = lines[index].match(BLOCK_HEADER_RE);
    if (!match) continue;
    const [, levelText, , typeText, countText] = match;
    const level = Number(levelText);
    const type = Number(typeText);
    const count = Number(countText);
    if (level <= 0 || count < 0 || type === 99) continue;
    const name = lines[index + 1]?.trim();
    if (!name || BLOCK_HEADER_RE.test(name)) continue;
    blocks.push({
      id: `${index}:${level}:${type}:${count}:${name}`,
      level,
      type,
      count,
      name,
    });
  }
  return blocks;
}

function signatureFromText(text: string): string | null {
  const preferred = text.match(/\bL_(?:MULTICOMPO|MACROLIB)\b/);
  if (preferred) return preferred[0];
  const fallback = text.match(/\bL_LIBRARY\b/);
  return fallback?.[0] ?? null;
}

function formatFromSignature(signature: string | null): DonjonAsciiFormat {
  if (signature === MULTICOMPO_SIGNATURE) return "MULTICOMPO";
  if (signature === MACROLIB_SIGNATURE) return "MACROLIB";
  return "unknown";
}

function blockHit(id: string, label: string, present: boolean): BlockHit {
  return { id, label, present };
}

function normalizedLineSet(text: string): Set<string> {
  return new Set(
    text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean),
  );
}

function analysisNotes({
  signature,
  likelyDonjonAscii,
  blockHits,
  truncated,
}: {
  signature: string | null;
  likelyDonjonAscii: boolean;
  blockHits: BlockHit[];
  truncated: boolean;
}): string[] {
  const notes: string[] = [];
  if (!signature) {
    notes.push("No L_MULTICOMPO / L_MACROLIB signature found in this preview slice.");
  } else if (!likelyDonjonAscii) {
    notes.push(`Found ${signature}, but not a top-level MULTICOMPO/MACROLIB signature.`);
  }
  if (!blockHits.find((hit) => hit.id === "energy")?.present) {
    notes.push(
      truncated
        ? "ENERGY block was not visible in this bounded preview slice."
        : "ENERGY block is absent from this file.",
    );
  }
  if (!blockHits.find((hit) => hit.id === "scatter")?.present) {
    notes.push("Complete NJJS00/IJJS00/SCAT00 sparse-scatter triplet not visible.");
  }
  return notes;
}
