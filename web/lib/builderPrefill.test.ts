import { describe, expect, it } from "vitest";
import { bundlePrefillStatus } from "./builderPrefill";

describe("bundlePrefillStatus", () => {
  it("recognizes converter-result bundle links", () => {
    const status = bundlePrefillStatus({
      output_dir: "/runs/case/bundle",
      mgxs: "/runs/case/mgxs_library.h5",
      mcompo: "/runs/case/out.mcompo.txt",
    });

    expect(status.prefilled).toBe(true);
    expect(status.title).toBe("Prefilled from a converter result");
    expect(status.chips).toEqual([
      "bundle directory",
      "MGXS HDF5",
      "MULTICOMPO",
    ]);
    expect(status.manifestPath).toBe("/runs/case/bundle/manifest.json");
    expect(status.validateHref).toBe(
      "/builder?command=validate-bundle&manifest=%2Fruns%2Fcase%2Fbundle%2Fmanifest.json",
    );
    expect(status.donjonHref).toBe(
      "/donjon?ascii=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&manifest=%2Fruns%2Fcase%2Fbundle%2Fmanifest.json&deck=out_donjon_solve.x2m",
    );
  });

  it("recognizes partial bundle prefill", () => {
    const status = bundlePrefillStatus({
      output_dir: "/runs/case/bundle",
      check_summary: "/runs/case/check_summary.json",
    });

    expect(status.prefilled).toBe(true);
    expect(status.title).toBe("Bundle builder has prefilled fields");
    expect(status.chips).toEqual(["bundle directory", "check summary"]);
    expect(status.manifestPath).toBe("/runs/case/bundle/manifest.json");
    expect(status.donjonHref).toBeUndefined();
  });

  it("keeps empty bundle builders in explanatory mode", () => {
    const status = bundlePrefillStatus({});

    expect(status.prefilled).toBe(false);
    expect(status.title).toBe("Bundle artifacts after conversion");
    expect(status.chips).toEqual([]);
    expect(status.manifestPath).toBeUndefined();
    expect(status.validateHref).toBeUndefined();
    expect(status.donjonHref).toBeUndefined();
  });
});
