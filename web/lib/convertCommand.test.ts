import { describe, expect, it } from "vitest";
import {
  buildConvertCliPreview,
  convertAdvancedPayload,
  parseMixtures,
} from "./convertCommand";

describe("convert command helpers", () => {
  it("parses comma and newline separated mixture names", () => {
    expect(parseMixtures("M1_UO2, M2_MOD\nM3_MOX")).toEqual([
      "M1_UO2",
      "M2_MOD",
      "M3_MOX",
    ]);
    expect(parseMixtures(" \n ")).toBeNull();
  });

  it("normalizes advanced payload values for the convert endpoint", () => {
    expect(
      convertAdvancedPayload({
        rootName: "",
        comment: "  production handoff  ",
        burnup: "12.5",
        hFactorDefault: "",
        mixturesText: "ASM_01",
      }),
    ).toEqual({
      root_name: "CPO",
      comment: "production handoff",
      burnup: 12.5,
      h_factor_default: null,
      mixtures: ["ASM_01"],
    });
  });

  it("rejects non-finite numeric advanced payload values", () => {
    expect(() =>
      convertAdvancedPayload({
        rootName: "CPO",
        comment: "",
        burnup: "Infinity",
        hFactorDefault: "",
        mixturesText: "",
      }),
    ).toThrow("numeric convert option");
  });

  it("builds the same CLI shape exposed by the backend response", () => {
    const cli = buildConvertCliPreview({
      inputPath: "/tmp/mgxs handoff.h5",
      outputPath: "/tmp/out.mcompo.txt",
      format: "multicompo",
      writerBackend: "pygan",
      dryRun: true,
      overwrite: true,
      check: true,
      production: true,
      warnUnknownEnergyMesh: true,
      requireKnownEnergyMesh: true,
      rootName: "CORE",
      comment: "C5G7 direct",
      burnup: "0",
      hFactorDefault: "200",
      mixturesText: "M1_UO2,M2_MOD",
    });

    expect(cli).toContain("'/tmp/mgxs handoff.h5'");
    expect(cli).toContain("--writer-backend pygan");
    expect(cli).toContain("--root-name CORE");
    expect(cli).toContain("--dry-run --overwrite");
    expect(cli).toContain("--comment 'C5G7 direct'");
    expect(cli).toContain("--burnup 0");
    expect(cli).toContain("--h-factor-default 200");
    expect(cli).toContain("--mixture M1_UO2 --mixture M2_MOD");
    expect(cli).toContain("--check --production");
    expect(cli).toContain("--require-known-energy-mesh");
  });

  it("omits MULTICOMPO-only root-name overrides for MACROLIB", () => {
    expect(
      buildConvertCliPreview({
        inputPath: "/tmp/mgxs.h5",
        outputPath: "/tmp/out.macrolib.txt",
        format: "macrolib",
        writerBackend: "ascii",
        dryRun: false,
        overwrite: false,
        check: false,
        production: false,
        warnUnknownEnergyMesh: true,
        requireKnownEnergyMesh: false,
        rootName: "CORE",
        comment: "",
        burnup: "",
        hFactorDefault: "",
        mixturesText: "",
      }),
    ).not.toContain("--root-name");
  });
});
