import type { ConvertFormat, ConvertPreflightInput } from "./api";
import { convertArtifactAnatomy } from "./convertArtifactAnatomy";

export type DonjonAsciiFormat = "MULTICOMPO" | "MACROLIB" | "unknown";

export interface BlockHit {
  id: string;
  label: string;
  present: boolean;
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
  blockHits: BlockHit[];
  blockTree: LcmBlockPreview[];
  blockTreeTruncated: boolean;
  notes: string[];
}

const MULTICOMPO_SIGNATURE = "L_MULTICOMPO";
const MACROLIB_SIGNATURE = "L_MACROLIB";
const MAX_BLOCK_TREE_ITEMS = 18;
const BLOCK_HEADER_RE = /^\s*->\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+<-/;

export function analyzeDonjonAsciiPreview(text: string): AsciiPreviewAnalysis {
  const lineSet = normalizedLineSet(text);
  const signature = signatureFromText(text);
  const format = formatFromSignature(signature);
  const allBlocks = parseLcmBlocks(text);
  const blockTree = allBlocks.slice(0, MAX_BLOCK_TREE_ITEMS);
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
    blockHits,
    blockTree,
    blockTreeTruncated: allBlocks.length > blockTree.length,
    notes: analysisNotes({ signature, likelyDonjonAscii, blockHits }),
  };
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
}: {
  signature: string | null;
  likelyDonjonAscii: boolean;
  blockHits: BlockHit[];
}): string[] {
  const notes: string[] = [];
  if (!signature) {
    notes.push("No L_MULTICOMPO / L_MACROLIB signature found in this preview slice.");
  } else if (!likelyDonjonAscii) {
    notes.push(`Found ${signature}, but not a top-level MULTICOMPO/MACROLIB signature.`);
  }
  if (!blockHits.find((hit) => hit.id === "energy")?.present) {
    notes.push("ENERGY block was not visible in this bounded preview slice.");
  }
  if (!blockHits.find((hit) => hit.id === "scatter")?.present) {
    notes.push("Complete NJJS00/IJJS00/SCAT00 sparse-scatter triplet not visible.");
  }
  return notes;
}
