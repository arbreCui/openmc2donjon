import { describe, expect, it } from "vitest";
import {
  analyzeDonjonAsciiPreview,
  expectedArtifactBlockCoverage,
} from "./asciiPreview";

describe("DONJON ASCII preview analysis", () => {
  it("recognizes MULTICOMPO signatures and key blocks", () => {
    const analysis = analyzeDonjonAsciiPreview(`
-> 1 12 3 3 <-
SIGNATURE
L_MULTICOMPO
-> 2 12 1 40 <-
STATE-VECTOR
-> 2 12 10 7 <-
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
    expect(analysis.blockTree.map((block) => block.name)).toEqual([
      "SIGNATURE",
      "STATE-VECTOR",
      "MIXTURES",
    ]);
    expect(analysis.blockTree[1]).toMatchObject({
      level: 2,
      type: 1,
      count: 40,
    });
    expect(analysis.keyBlocks.map((block) => [block.id, block.status])).toEqual([
      ["signature", "present"],
      ["state-vector", "present"],
      ["energy", "present"],
      ["total-xs", "present"],
      ["scatter", "present"],
      ["adf", "optional"],
      ["sph", "optional"],
    ]);
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
    expect(analysis.keyBlocks.find((block) => block.id === "signature")).toMatchObject({
      status: "missing",
    });
    expect(analysis.keyBlocks.find((block) => block.id === "scatter")).toMatchObject({
      status: "missing",
    });
    expect(analysis.notes.join(" ")).toContain("No L_MULTICOMPO");
    expect(analysis.notes.join(" ")).toContain("sparse-scatter");
  });

  it("summarizes optional equivalence blocks and partial scattering", () => {
    const analysis = analyzeDonjonAsciiPreview(`
SIGNATURE
L_MULTICOMPO
STATE-VECTOR
ENERGY
NTOT0
SCAT00
ADF
NSPH
`);
    expect(analysis.keyBlocks.find((block) => block.id === "scatter")).toMatchObject({
      status: "partial",
    });
    expect(analysis.keyBlocks.find((block) => block.id === "adf")).toMatchObject({
      status: "present",
    });
    expect(analysis.keyBlocks.find((block) => block.id === "sph")).toMatchObject({
      status: "present",
    });
  });

  it("blames the file, not the preview slice, when a complete preview lacks ENERGY", () => {
    const text = "SIGNATURE\nL_MACROLIB\nSTATE-VECTOR\nNTOT0\n";

    const complete = analyzeDonjonAsciiPreview(text, { truncated: false });
    const energy = complete.keyBlocks.find((block) => block.id === "energy");
    expect(energy?.status).toBe("missing");
    expect(energy?.detail).toBe("ENERGY is absent from this file.");
    expect(energy?.detail).not.toContain("preview slice");
    expect(complete.notes.join(" ")).toContain(
      "ENERGY block is absent from this file.",
    );

    const truncated = analyzeDonjonAsciiPreview(text, { truncated: true });
    expect(
      truncated.keyBlocks.find((block) => block.id === "energy")?.detail,
    ).toContain("preview slice");
  });

  it("ignores LCM control markers while building the block tree", () => {
    const analysis = analyzeDonjonAsciiPreview(`
-> 1 12 0 0 <-
CPO
-> 2 12 10 2 <-
MIXTURES
-> 3 0 0 -1 <- 00000001
-> 4 12 10 1 <-
CALCULATIONS
-> -4 0 0 0 <-
`);
    expect(analysis.blockTree.map((block) => block.name)).toEqual([
      "CPO",
      "MIXTURES",
      "CALCULATIONS",
    ]);
    expect(analysis.blockTree.some((block) => block.count < 0)).toBe(false);
  });

  it("cross-checks expected MULTICOMPO anatomy blocks visible in the preview", () => {
    const coverage = expectedArtifactBlockCoverage(
      `
SIGNATURE
L_MULTICOMPO
GLOBAL
STATE-VECTOR
MIXTURES
CALCULATIONS
TREE
ISOTOPESLIST
NTOT0
STRD
SCAT00
L_LIBRARY
ENERGY
ADF
NSPH
`,
      "multicompo",
      {
        path: "/x.h5",
        ok: true,
        energy_groups: 7,
        legendre_order: 0,
        issues: [],
        warnings: [],
        adf_faces: ["left"],
        adf_mixtures: 1,
        sph_calculations: 1,
      },
    );
    expect(coverage.map((section) => [section.id, section.presentCount])).toEqual([
      ["header", 3],
      ["map", 3],
      ["xs", 4],
      ["equivalence", 4],
    ]);
  });

  it("does not require absent optional equivalence blocks in preview coverage", () => {
    const coverage = expectedArtifactBlockCoverage(
      `
SIGNATURE
L_MACROLIB
STATE-VECTOR
ENERGY
VOLUME
GROUP
FLUX-INTG
NTOT0
DIFF
SIGS00
SCAT00
NJJS00
IJJS00
`,
      "macrolib",
      {
        path: "/x.h5",
        ok: true,
        energy_groups: 7,
        legendre_order: 0,
        issues: [],
        warnings: [],
        adf_faces: [],
        adf_mixtures: 0,
        sph_calculations: 0,
      },
    );
    const equivalence = coverage.find((section) => section.id === "equivalence");
    expect(equivalence?.hits.map((hit) => hit.label)).toEqual(["H-FACTOR"]);
    expect(equivalence?.presentCount).toBe(0);
  });
});
