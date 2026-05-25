import { describe, expect, it } from "vitest";
import {
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  donjonObjectLabel,
  inferDonjonFormat,
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
});
