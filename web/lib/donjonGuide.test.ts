import { describe, expect, it } from "vitest";
import {
  deckNumberParam,
  donjonBundleAsciiMismatch,
  donjonDeckOptionsFromSearchParams,
  donjonDeckFilename,
  donjonDeckChecklist,
  donjonDefaultsArtifact,
  donjonGuideFacts,
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
      "nmix=1200&geometry=hexagon&solver=sn&spn=4&sn=5&side=-2&height=0&xm=BAD&xp=REFL",
    );
    expect(donjonDeckOptionsFromSearchParams(params)).toMatchObject({
      mixtureCount: 999,
      geometry: "car2d",
      solver: "diffusion",
      spnOrder: 3,
      snOrder: 8,
      hexSide: 1,
      hexHeight: 10,
      xMinus: "REFL",
      xPlus: "REFL",
    });
  });

  it("round-trips hex SNT deck options through guide links", () => {
    const href = donjonGuideHref({
      asciiPath: "/runs/case/out.mcompo.txt",
      format: "multicompo",
      deckOptions: {
        mixtureCount: 91,
        geometry: "hex",
        solver: "snt",
        snOrder: 4,
        hexSide: 10.1036,
      },
    });
    expect(href).toBe(
      "/donjon?ascii=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&nmix=91&geometry=hex&solver=snt&sn=4&side=10.1036",
    );
    const params = new URLSearchParams(href.split("?")[1]);
    expect(donjonDeckOptionsFromSearchParams(params)).toMatchObject({
      mixtureCount: 91,
      geometry: "hex",
      solver: "snt",
      snOrder: 4,
      hexSide: 10.1036,
      hexHeight: 10,
    });
  });

  it("coerces the SNT solver back to diffusion without hex geometry", () => {
    expect(
      normalizeDonjonDeckOptions({ geometry: "car2d", solver: "snt" }),
    ).toMatchObject({ geometry: "car2d", solver: "diffusion" });
    const params = new URLSearchParams("geometry=car3d&solver=snt");
    expect(donjonDeckOptionsFromSearchParams(params)).toMatchObject({
      geometry: "car3d",
      solver: "diffusion",
    });
    expect(
      normalizeDonjonDeckOptions({ geometry: "hex", solver: "snt" }),
    ).toMatchObject({ geometry: "hex", solver: "snt" });
  });

  it("states the consumption facts once per format in the compact strip", () => {
    const multicompo = donjonGuideFacts("multicompo");
    expect(multicompo.map((fact) => fact.id)).toEqual([
      "object",
      "mapping",
      "geometry",
    ]);
    expect(multicompo[0].body).toContain("L_MULTICOMPO");
    expect(multicompo[0].body).toContain("NCR extracts a MACROLIB");
    expect(multicompo[1].body).toContain("NCR MIX lines");

    const macrolib = donjonGuideFacts("macrolib");
    expect(macrolib.map((fact) => fact.id)).toEqual([
      "object",
      "mapping",
      "geometry",
    ]);
    expect(macrolib[0].body).toContain("L_MACROLIB");
    expect(macrolib[0].body).toContain("directly to MACRO");
    expect(macrolib[1].body).toContain("refer directly to the mixtures");

    // The geometry caveat merges the former solver guidance card and the
    // production-reminder section into one sentence, shared by both formats.
    expect(multicompo[2].body).toBe(macrolib[2].body);
    expect(multicompo[2].body).toContain("OpenMC supplies the homogenized");
    expect(multicompo[2].body).toContain("boundary conditions, and solver");
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
      "ascii-72",
      "smoke-first",
    ]);
    expect(items[0]).toMatchObject({ tone: "ready" });
    expect(items[1].body).toContain("NMIX 9");
    expect(items[2].body).toContain("assign all 9 mixture regions");
    expect(items[3].title).toContain("SPN5");
    expect(items[3].body).toContain("Z+ REFL");
    // The SEQ_ASCII 72-character limit applies to every geometry, not
    // just hex decks.
    expect(items[4].body).toContain("72 characters");
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

  it("adds the hex-specific warnings to the deck checklist", () => {
    const items = donjonDeckChecklist("/runs/case/out.mcompo.txt", "multicompo", {
      mixtureCount: 91,
      geometry: "hex",
      solver: "snt",
      snOrder: 8,
    });

    expect(items.map((item) => item.id)).toEqual([
      "ascii-path",
      "ncr-mixtures",
      "geometry-map",
      "boundary-solver",
      "ascii-72",
      "hex-boundary-void",
      "smoke-first",
    ]);
    expect(items[1].body).toContain("mixture_names");
    expect(items[2].title).toContain("HEXZ");
    expect(items[2].body).toContain("MIX 1..91");
    expect(items[3].title).toContain("SN8");
    // The boundary card is a short pointer; the full boundary rule
    // lives only in the dedicated hex-boundary-void card.
    expect(items[3].body).toContain("outer-boundary card");
    const ascii72 = items.find((item) => item.id === "ascii-72");
    expect(ascii72?.body).toContain("72 characters");
    expect(ascii72?.body).toContain("short absolute path");
    const boundaryVoid = items.find((item) => item.id === "hex-boundary-void");
    expect(boundaryVoid?.body).toContain("silently leak");
    expect(boundaryVoid?.body).toContain("only VOID is validated");
    expect(boundaryVoid?.body).toContain("cannot be validated in SNT");
  });

  it("keeps Cartesian deck skeletons byte-identical to the pre-hex output", () => {
    expect(donjonIngestSnippet("/runs/case/out.mcompo.txt", "multicompo")).toBe(
      [
        "MODULE GEO: NCR: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;",
        "LINKED_LIST CPO MACRO GEOM TRACK SYS FLUX ;",
        "REAL keff ;",
        "SEQ_ASCII CPO_ASC :: FILE '/runs/case/out.mcompo.txt' ;",
        "",
        "CPO := CPO_ASC ;",
        "MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 1",
        "  COMPO CPO CPO",
        "  MIX 1 USE ENDMIX",
        ";",
        "",
        "* Replace this geometry / tracking block with your low-order model.",
        "* The one-cell GEOM below is only an ingest smoke model.",
        "GEOM := GEO: :: CAR2D 1 1",
        "  EDIT 0 X- REFL X+ VOID Y- REFL Y+ VOID",
        "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 ;",
        "TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1 ;",
        "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
        "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
        "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
        "ECHO 'OPENMC2DONJON MULTICOMPO DIFFUSION K-EFFECTIVE' keff ;",
        "END: ;",
      ].join("\n"),
    );

    expect(
      donjonIngestSnippet("/runs/case/out.mcompo.txt", "multicompo", {
        mixtureCount: 4,
        geometry: "car3d",
        solver: "spn",
        spnOrder: 5,
        zPlus: "REFL",
      }),
    ).toBe(
      [
        "MODULE GEO: NCR: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;",
        "LINKED_LIST CPO MACRO GEOM TRACK SYS FLUX ;",
        "REAL keff ;",
        "SEQ_ASCII CPO_ASC :: FILE '/runs/case/out.mcompo.txt' ;",
        "",
        "CPO := CPO_ASC ;",
        "MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 4",
        "  COMPO CPO CPO",
        "  MIX 1 USE ENDMIX",
        "  MIX 2 USE ENDMIX",
        "  MIX 3 USE ENDMIX",
        "  MIX 4 USE ENDMIX",
        ";",
        "",
        "* Replace this geometry / tracking block with your low-order model.",
        "* The one-cell GEOM below references MIX 1 only; expand it to map all 4 mixtures.",
        "GEOM := GEO: :: CAR3D 1 1 1",
        "  EDIT 0 X- REFL X+ VOID Y- REFL Y+ VOID Z- REFL Z+ REFL",
        "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 MESHZ 0.0 1.0 ;",
        "TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1 SPN 5 SCAT 1 ;",
        "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
        "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
        "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
        "ECHO 'OPENMC2DONJON MULTICOMPO SPN5 K-EFFECTIVE' keff ;",
        "END: ;",
      ].join("\n"),
    );

    expect(
      donjonIngestSnippet("/runs/case/out.macrolib.txt", "macrolib", {
        mixtureCount: 2,
      }),
    ).toBe(
      [
        "MODULE GEO: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;",
        "LINKED_LIST MACRO GEOM TRACK SYS FLUX ;",
        "REAL keff ;",
        "SEQ_ASCII MACRO_ASC :: FILE '/runs/case/out.macrolib.txt' ;",
        "",
        "MACRO := MACRO_ASC ;",
        "",
        "* Replace this geometry / tracking block with your low-order model.",
        "* The one-cell GEOM below references MIX 1 only; expand it to map all 2 mixtures.",
        "GEOM := GEO: :: CAR2D 1 1",
        "  EDIT 0 X- REFL X+ VOID Y- REFL Y+ VOID",
        "  MIX 1 MESHX 0.0 1.0 MESHY 0.0 1.0 ;",
        "TRACK := TRIVAT: GEOM :: EDIT 1 DUAL 1 1 ;",
        "SYS := TRIVAA: MACRO TRACK :: EDIT 0 ;",
        "FLUX := FLUD: SYS TRACK :: EDIT 1 ADI 4 ACCE 5 3 EXTE 200 1.E-6 ;",
        "GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;",
        "ECHO 'OPENMC2DONJON MACROLIB DIFFUSION K-EFFECTIVE' keff ;",
        "END: ;",
      ].join("\n"),
    );

    expect(donjonIngestOnlySnippet("/runs/case/out.mcompo.txt", "multicompo")).toBe(
      [
        "MODULE UTL: END: ABORT: ;",
        "LINKED_LIST CPO ;",
        "SEQ_ASCII CPO_ASC :: FILE '/runs/case/out.mcompo.txt' ;",
        "CPO := CPO_ASC ;",
        "UTL: CPO :: DUMP ;",
        "END: ;",
      ].join("\n"),
    );
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

  it("generates the benchmark-shaped hex SNT deck", () => {
    const snippet = donjonIngestSnippet("/runs/case/out.mcompo.txt", "multicompo", {
      mixtureCount: 12,
      geometry: "hex",
      solver: "snt",
      snOrder: 8,
      hexSide: 10.1036,
      hexHeight: 10,
    });

    expect(snippet).toBe(
      [
        "MODULE GEO: NCR: SNT: ASM: FLU: GREP: END: ABORT: ;",
        "LINKED_LIST CPO MACRO GEOM TRACK SYSTEM FLUX ;",
        "REAL keff ;",
        "SEQ_ASCII CPO_ASC :: FILE '/runs/case/out.mcompo.txt' ;",
        "",
        "CPO := CPO_ASC ;",
        "MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 12",
        "  COMPO CPO CPO",
        "  MIX 1 USE ENDMIX",
        "  MIX 2 USE ENDMIX",
        "  MIX 3 USE ENDMIX",
        "  MIX 4 USE ENDMIX",
        "  MIX 5 USE ENDMIX",
        "  MIX 6 USE ENDMIX",
        "  MIX 7 USE ENDMIX",
        "  MIX 8 USE ENDMIX",
        "  MIX 9 USE ENDMIX",
        "  MIX 10 USE ENDMIX",
        "  MIX 11 USE ENDMIX",
        "  MIX 12 USE ENDMIX",
        ";",
        "",
        "* Replace this geometry / tracking block with your low-order model.",
        "* The HEXZ GEOM below assigns MIX 1..12, one mixture per hex position.",
        "* The MIX order must match the multicompo mixture order (the",
        "* mixture_names dataset of the handoff HDF5).",
        "* SIDE is the hexagon edge length in cm.",
        "GEOM := GEO: :: HEXZ 12 1 EDIT 0",
        "  Z- REFL Z+ REFL  HBC COMPLETE VOID",
        "  SIDE 10.1036  SPLITL 2",
        "  MESHZ 0.0 10.0",
        "  MIX",
        "  1 2 3 4 5 6 7 8 9 10",
        "  11 12",
        ";",
        "* SCAT is the scattering anisotropy order + 1 (P1 handoff -> SCAT 2).",
        "TRACK := SNT: GEOM :: EDIT 0 DIAM 1 SN 8 SCAT 2 ;",
        "SYSTEM := ASM: MACRO TRACK :: ARM ;",
        "FLUX := FLU: SYSTEM MACRO TRACK :: EDIT 1 TYPE K EXTE 500 1E-05 ;",
        "GREP: FLUX :: GETVAL 'K-EFFECTIVE' 1 >>keff<< ;",
        "ECHO 'OPENMC2DONJON MULTICOMPO SN8 K-EFFECTIVE' keff ;",
        "END: ;",
      ].join("\n"),
    );
    // SNT/FLU: read K-EFFECTIVE without the trailing space used by FLUD:.
    expect(snippet).toContain("GETVAL 'K-EFFECTIVE' 1");
    expect(snippet).not.toContain("GETVAL 'K-EFFECTIVE ' 1");
  });

  it("generates hex TRIVAC diffusion decks with MCFD 1 and unsplit hexes", () => {
    const snippet = donjonIngestSnippet("/runs/case/out.mcompo.txt", "multicompo", {
      mixtureCount: 7,
      geometry: "hex",
      solver: "diffusion",
    });

    expect(snippet).toContain("MODULE GEO: NCR: TRIVAT: TRIVAA: FLUD: GREP: END: ABORT: ;");
    expect(snippet).toContain("GEOM := GEO: :: HEXZ 7 1 EDIT 0");
    expect(snippet).toContain("  Z- REFL Z+ REFL  HBC COMPLETE VOID");
    expect(snippet).toContain("  SIDE 1.0");
    expect(snippet).toContain("  MESHZ 0.0 10.0");
    expect(snippet).toContain("TRACK := TRIVAT: GEOM :: EDIT 1 MAXR 20000 MCFD 1 ;");
    expect(snippet).toContain("FLUX := FLUD: SYS TRACK :: EDIT 1 ACCE 3 3 EXTE 1000 1E-05 ADI 6 ;");
    expect(snippet).toContain("GREP: FLUX :: GETVAL 'K-EFFECTIVE ' 1 >>keff<< ;");
    // TRIVAC MCFD requires unsplit hexes: no SPLITL outside the SNT route.
    expect(snippet).not.toContain("SPLITL");
    expect(snippet).not.toContain("DUAL 1 1");
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
    const artifacts = [
      {
        label: "mcompo",
        path: "/runs/case/bundle/out.mcompo.txt",
      },
    ];
    const summaryArtifact = donjonDefaultsArtifact({
      ascii_path: "/runs/case/out.mcompo.txt",
    });

    expect(donjonBundleAsciiMismatch(artifacts, summaryArtifact)).toEqual({
      artifactPaths: ["/runs/case/bundle/out.mcompo.txt"],
      summaryPath: "/runs/case/out.mcompo.txt",
    });
    expect(donjonBundleAsciiMismatch(artifacts, null)).toBeNull();
    expect(
      donjonBundleAsciiMismatch(
        [{ label: "mgxs", path: "/runs/case/handoff.h5" }],
        summaryArtifact,
      ),
    ).toBeNull();
  });

  it("does not flag a mismatch when the summary output is any bundled ASCII artifact", () => {
    // Dual-format bundle: the best-scoring artifact differs from the
    // summary output, but the summary output IS the other bundled
    // artifact - not a mismatch.
    const artifacts = [
      {
        label: "macrolib",
        path: "/runs/case/bundle/out.macrolib.txt",
        bundled_path: "out.macrolib.txt",
        ok: true,
      },
      {
        label: "mcompo",
        path: "/runs/case/bundle/out.mcompo.txt",
        bundled_path: "out.mcompo.txt",
        ok: true,
      },
    ];
    const summaryArtifact = donjonDefaultsArtifact({
      ascii_path: "/runs/case/bundle/out.mcompo.txt",
    });

    expect(donjonBundleAsciiMismatch(artifacts, summaryArtifact)).toBeNull();
    expect(
      donjonBundleAsciiMismatch(
        artifacts,
        donjonDefaultsArtifact({ ascii_path: "/runs/case/elsewhere.mcompo.txt" }),
      ),
    ).toEqual({
      artifactPaths: [
        "/runs/case/bundle/out.macrolib.txt",
        "/runs/case/bundle/out.mcompo.txt",
      ],
      summaryPath: "/runs/case/elsewhere.mcompo.txt",
    });
  });

  it("parses raw deck number inputs without coercing empty to zero", () => {
    expect(deckNumberParam("12")).toBe(12);
    expect(deckNumberParam("10.1036")).toBe(10.1036);
    expect(deckNumberParam("")).toBeUndefined();
    expect(deckNumberParam("  ")).toBeUndefined();
    expect(deckNumberParam(null)).toBeUndefined();
    expect(deckNumberParam("abc")).toBeUndefined();
    // Cleared "Mixtures to extract" field: no value reaches the
    // normalizer, so checklist and deck both use the default of 1.
    expect(
      normalizeDonjonDeckOptions({ mixtureCount: deckNumberParam("") })
        .mixtureCount,
    ).toBe(1);
  });
});
