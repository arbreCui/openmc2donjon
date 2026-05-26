import { describe, expect, it } from "vitest";
import {
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  donjonObjectLabel,
  findDonjonBundleArtifact,
  inferDonjonFormat,
  normalizeDonjonDeckOptions,
} from "./donjonGuide";

describe("DONJON guide helpers", () => {
  it("builds deep links with ASCII, format, and manifest paths", () => {
    expect(
      donjonGuideHref({
        asciiPath: "/runs/case/out.mcompo.txt",
        format: "multicompo",
        manifestPath: "/runs/case/bundle/manifest.json",
      }),
    ).toBe(
      "/donjon?ascii=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&manifest=%2Fruns%2Fcase%2Fbundle%2Fmanifest.json",
    );
  });

  it("infers MACROLIB format from path unless explicit format wins", () => {
    expect(inferDonjonFormat("/runs/out.macrolib.txt")).toBe("macrolib");
    expect(inferDonjonFormat("/runs/out.mcompo.txt")).toBe("multicompo");
    expect(inferDonjonFormat("/runs/out.macrolib.txt", "multicompo")).toBe(
      "multicompo",
    );
  });

  it("generates MULTICOMPO snippets through CPO and NCR", () => {
    const snippet = donjonIngestSnippet("/runs/case/out.mcompo.txt", "multicompo");
    expect(donjonObjectLabel("multicompo")).toBe("L_MULTICOMPO");
    expect(snippet).toContain("SEQ_ASCII CPO_ASC");
    expect(snippet).toContain("MACRO := NCR: CPO");
    expect(snippet).toContain("COMPO CPO CPO");
    expect(donjonIngestOnlySnippet("/runs/case/out.mcompo.txt", "multicompo")).toContain(
      "UTL: CPO :: DUMP",
    );
  });

  it("generates MACROLIB snippets as direct MACRO assignment", () => {
    const snippet = donjonIngestSnippet("/runs/case/out.macrolib.txt", "macrolib");
    expect(donjonObjectLabel("macrolib")).toBe("L_MACROLIB");
    expect(snippet).toContain("SEQ_ASCII MACRO_ASC");
    expect(snippet).toContain("MACRO := MACRO_ASC");
    expect(snippet).not.toContain("NCR:");
  });

  it("generates configurable MULTICOMPO deck skeletons", () => {
    const snippet = donjonIngestSnippet("/runs/case/out.mcompo.txt", "multicompo", {
      mixtureCount: 4,
      geometry: "car3d",
      solver: "spn",
      spnOrder: 3,
      xMinus: "REFL",
      xPlus: "VOID",
      yMinus: "REFL",
      yPlus: "VOID",
      zMinus: "VOID",
      zPlus: "VOID",
    });

    expect(snippet).toContain("MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 4");
    expect(snippet).toContain("  MIX 4 USE ENDMIX");
    expect(snippet).toContain("GEOM := GEO: :: CAR3D 1 1 1");
    expect(snippet).toContain("Z- VOID Z+ VOID");
    expect(snippet).toContain("TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1 SPN 3 SCAT 1 ;");
  });

  it("normalizes deck builder options before rendering", () => {
    expect(
      normalizeDonjonDeckOptions({
        mixtureCount: 0,
        solver: "spn",
        spnOrder: 4,
      }),
    ).toMatchObject({
      mixtureCount: 1,
      geometry: "car2d",
      solver: "spn",
      spnOrder: 3,
      xMinus: "REFL",
      xPlus: "VOID",
    });
    expect(normalizeDonjonDeckOptions({ mixtureCount: 1200 }).mixtureCount).toBe(
      999,
    );
  });

  it("finds a MULTICOMPO ASCII artifact from a bundle manifest", () => {
    const artifact = findDonjonBundleArtifact([
      {
        label: "mgxs",
        path: "/runs/case/handoff.h5",
        ok: true,
      },
      {
        label: "mcompo",
        path: "/runs/case/bundle/out.mcompo.txt",
        bundled_path: "out.mcompo.txt",
        ok: true,
      },
      {
        label: "conversion-summary",
        path: "/runs/case/bundle/convert_summary.json",
        ok: true,
      },
    ]);

    expect(artifact).toMatchObject({
      label: "mcompo",
      asciiPath: "/runs/case/bundle/out.mcompo.txt",
      format: "multicompo",
      bundledPath: "out.mcompo.txt",
      ok: true,
    });
  });

  it("finds a MACROLIB ASCII artifact by path suffix", () => {
    const artifact = findDonjonBundleArtifact([
      {
        label: "ascii-output",
        path: "/runs/case/out.macrolib.txt",
        ok: false,
        messages: ["sha256 mismatch"],
      },
    ]);

    expect(artifact).toMatchObject({
      label: "ascii-output",
      asciiPath: "/runs/case/out.macrolib.txt",
      format: "macrolib",
      ok: false,
      messages: ["sha256 mismatch"],
    });
  });

  it("returns null when a manifest has no DONJON ASCII artifact", () => {
    expect(
      findDonjonBundleArtifact([
        { label: "mgxs", path: "/runs/case/handoff.h5" },
        { label: "summary", path: "/runs/case/summary.json" },
      ]),
    ).toBeNull();
  });
});
