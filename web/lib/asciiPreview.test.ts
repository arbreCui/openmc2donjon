import { describe, expect, it } from "vitest";
import { analyzeDonjonAsciiPreview } from "./asciiPreview";

describe("DONJON ASCII preview analysis", () => {
  it("recognizes MULTICOMPO signatures and key blocks", () => {
    const analysis = analyzeDonjonAsciiPreview(`
SIGNATURE
L_MULTICOMPO
STATE-VECTOR
MIXTURES
NTOT0
NUSIGF
NJJS00
IJJS00
SCAT00
ENERGY
`);
    expect(analysis).toMatchObject({
      format: "MULTICOMPO",
      signature: "L_MULTICOMPO",
      likelyDonjonAscii: true,
    });
    expect(analysis.blockHits.filter((hit) => hit.present)).toHaveLength(6);
    expect(analysis.notes).toHaveLength(0);
  });

  it("recognizes MACROLIB signatures", () => {
    const analysis = analyzeDonjonAsciiPreview("SIGNATURE\nL_MACROLIB\nNTOT0\n");
    expect(analysis.format).toBe("MACROLIB");
    expect(analysis.signature).toBe("L_MACROLIB");
    expect(analysis.likelyDonjonAscii).toBe(true);
  });

  it("treats nested L_LIBRARY as not enough for a top-level handoff", () => {
    const analysis = analyzeDonjonAsciiPreview("SIGNATURE\nL_LIBRARY\nSTATE-VECTOR\n");
    expect(analysis.format).toBe("unknown");
    expect(analysis.signature).toBe("L_LIBRARY");
    expect(analysis.likelyDonjonAscii).toBe(false);
    expect(analysis.notes.join(" ")).toContain("not a top-level");
  });

  it("reports missing signature and sparse scatter triplet", () => {
    const analysis = analyzeDonjonAsciiPreview("NTOT0\nNUSIGF\n");
    expect(analysis.signature).toBeNull();
    expect(analysis.likelyDonjonAscii).toBe(false);
    expect(analysis.notes.join(" ")).toContain("No L_MULTICOMPO");
    expect(analysis.notes.join(" ")).toContain("sparse-scatter");
  });
});
