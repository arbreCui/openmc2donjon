import { describe, expect, it } from "vitest";
import {
  donjonGuideHref,
  donjonIngestOnlySnippet,
  donjonIngestSnippet,
  donjonObjectLabel,
  findDonjonBundleArtifact,
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
