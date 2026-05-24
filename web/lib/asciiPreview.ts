export type DonjonAsciiFormat = "MULTICOMPO" | "MACROLIB" | "unknown";

export interface BlockHit {
  id: string;
  label: string;
  present: boolean;
}

export interface AsciiPreviewAnalysis {
  format: DonjonAsciiFormat;
  signature: string | null;
  likelyDonjonAscii: boolean;
  blockHits: BlockHit[];
  notes: string[];
}

const MULTICOMPO_SIGNATURE = "L_MULTICOMPO";
const MACROLIB_SIGNATURE = "L_MACROLIB";

export function analyzeDonjonAsciiPreview(text: string): AsciiPreviewAnalysis {
  const lineSet = new Set(
    text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean),
  );
  const signature = signatureFromText(text);
  const format = formatFromSignature(signature);
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
    notes: analysisNotes({ signature, likelyDonjonAscii, blockHits }),
  };
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
