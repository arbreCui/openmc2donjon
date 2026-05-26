import { describe, expect, it } from "vitest";
import {
  donjonBundleAsciiMismatch,
  donjonDeckOptionsFromSearchParams,
  donjonDeckFilename,
  donjonDeckChecklist,
  donjonDefaultsArtifact,
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  donjonObjectLabel,
  donjonRunCommand,
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

  it("round-trips DONJON deck options through guide links", () => {
    const href = donjonGuideHref({
      asciiPath: "/runs/case/out.mcompo.txt",
      format: "multicompo",
      deckFilename: "case_donjon_solve.x2m",
      deckOptions: {
        mixtureCount: 4,
        geometry: "car3d",
        solver: "spn",
        spnOrder: 5,
        xMinus: "VOID",
        zPlus: "REFL",
      },
    });
    expect(href).toBe(
      "/donjon?ascii=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&deck=case_donjon_solve.x2m&nmix=4&geometry=car3d&solver=spn&spn=5&xm=VOID&zp=REFL",
    );
    const params = new URLSearchParams(href.split("?")[1]);
    expect(donjonDeckOptionsFromSearchParams(params)).toMatchObject({
      mixtureCount: 4,
      geometry: "car3d",
      solver: "spn",
      spnOrder: 5,
      xMinus: "VOID",
      xPlus: "VOID",
      zPlus: "REFL",
    });
  });

  it("normalizes invalid DONJON deck URL parameters", () => {
    const params = new URLSearchParams(
      "nmix=1200&geometry=hex&solver=sn&spn=4&xm=BAD&xp=REFL",
    );
    expect(donjonDeckOptionsFromSearchParams(params)).toMatchObject({
      mixtureCount: 999,
      geometry: "car2d",
      solver: "diffusion",
      spnOrder: 3,
      xMinus: "REFL",
      xPlus: "REFL",
    });
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

  it("suggests safe DONJON deck filenames from ASCII output paths", () => {
    expect(
      donjonDeckFilename("/runs/case/out.mcompo.txt", "multicompo", "ingest"),
    ).toBe("out_donjon_ingest.x2m");
    expect(
      donjonDeckFilename("/runs/case/OpenMC case.macrolib.txt", "macrolib"),
    ).toBe("OpenMC_case_donjon_solve.x2m");
    expect(donjonDeckFilename("", "multicompo")).toBe(
      "openmc2donjon_multicompo_donjon_solve.x2m",
    );
  });

  it("generates a shell-safe DONJON run command for downloaded decks", () => {
    expect(donjonRunCommand("out_donjon_solve.x2m")).toBe(
      "rdonjon out_donjon_solve.x2m",
    );
    expect(donjonRunCommand("case with spaces.x2m")).toBe(
      "rdonjon 'case with spaces.x2m'",
    );
    expect(donjonRunCommand("case's deck.x2m")).toBe(
      "rdonjon 'case'\\''s deck.x2m'",
    );
  });

  it("summarizes production handoff checklist items for MULTICOMPO decks", () => {
    const items = donjonDeckChecklist("/runs/case/out.mcompo.txt", "multicompo", {
      mixtureCount: 9,
      geometry: "car3d",
      solver: "spn",
      spnOrder: 5,
      zPlus: "REFL",
    });

    expect(items.map((item) => item.id)).toEqual([
      "ascii-path",
      "ncr-mixtures",
      "geometry-map",
      "boundary-solver",
      "smoke-first",
    ]);
    expect(items[0]).toMatchObject({ tone: "ready" });
    expect(items[1].body).toContain("NMIX 9");
    expect(items[2].body).toContain("assign all 9 mixture regions");
    expect(items[3].title).toContain("SPN5");
    expect(items[3].body).toContain("Z+ REFL");
  });

  it("marks missing ASCII path and MACROLIB direct assignment in the checklist", () => {
    const items = donjonDeckChecklist("", "macrolib", {
      mixtureCount: 3,
      geometry: "car2d",
      solver: "diffusion",
    });

    expect(items[0]).toMatchObject({
      id: "ascii-path",
      title: "Set the ASCII path",
      tone: "review",
    });
    expect(items[1]).toMatchObject({
      id: "macrolib-direct",
      tone: "ready",
    });
    expect(items[1].body).toContain("without NCR");
    expect(items[3].title).toContain("diffusion");
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

  it("creates a DONJON output candidate from convert summary defaults", () => {
    expect(
      donjonDefaultsArtifact({
        format: "multicompo",
        ascii_path: "/runs/case/out.mcompo.txt",
        mixture_count: 9,
      }),
    ).toMatchObject({
      label: "convert-summary",
      asciiPath: "/runs/case/out.mcompo.txt",
      format: "multicompo",
      bundledPath: null,
    });

    expect(donjonDefaultsArtifact({ ascii_path: "" })).toBeNull();
  });

  it("detects artifact paths that differ from convert summary output", () => {
    const artifact = findDonjonBundleArtifact([
      {
        label: "mcompo",
        path: "/runs/case/bundle/out.mcompo.txt",
      },
    ]);
    const summaryArtifact = donjonDefaultsArtifact({
      ascii_path: "/runs/case/out.mcompo.txt",
    });

    expect(donjonBundleAsciiMismatch(artifact, summaryArtifact)).toEqual({
      artifactPath: "/runs/case/bundle/out.mcompo.txt",
      summaryPath: "/runs/case/out.mcompo.txt",
    });
    expect(donjonBundleAsciiMismatch(summaryArtifact, summaryArtifact)).toBeNull();
  });
});
