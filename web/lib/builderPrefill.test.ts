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
  });

  it("recognizes partial bundle prefill", () => {
    const status = bundlePrefillStatus({
      output_dir: "/runs/case/bundle",
      check_summary: "/runs/case/check_summary.json",
    });

    expect(status.prefilled).toBe(true);
    expect(status.title).toBe("Bundle builder has prefilled fields");
    expect(status.chips).toEqual(["bundle directory", "check summary"]);
  });

  it("keeps empty bundle builders in explanatory mode", () => {
    const status = bundlePrefillStatus({});

    expect(status.prefilled).toBe(false);
    expect(status.title).toBe("Bundle artifacts after conversion");
    expect(status.chips).toEqual([]);
  });
});
