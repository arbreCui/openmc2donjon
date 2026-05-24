import { describe, expect, it } from "vitest";
import {
  defaultConvertOutputPath,
  outputPathInDirectory,
  pickConvertBrowserStart,
} from "./convertPaths";

describe("defaultConvertOutputPath", () => {
  it("derives a MULTICOMPO output next to the input HDF5", () => {
    expect(defaultConvertOutputPath("/runs/case/mgxs_library.h5", "multicompo"))
      .toBe("/runs/case/mgxs_library.mcompo.txt");
  });

  it("derives a MACROLIB output next to the input HDF5", () => {
    expect(defaultConvertOutputPath("/runs/case/mgxs_library.hdf5", "macrolib"))
      .toBe("/runs/case/mgxs_library.macrolib.txt");
  });

  it("falls back to a stable output filename when no input is selected", () => {
    expect(defaultConvertOutputPath("", "multicompo")).toBe("out.mcompo.txt");
  });
});

describe("pickConvertBrowserStart", () => {
  it("opens the parent directory for a file-like path", () => {
    expect(pickConvertBrowserStart("/runs/case/mgxs_library.h5")).toBe("/runs/case/");
  });

  it("opens the path itself for a directory-like path", () => {
    expect(pickConvertBrowserStart("/runs/case/")).toBe("/runs/case/");
  });

  it("falls back to home for an empty path", () => {
    expect(pickConvertBrowserStart("")).toBe("~");
  });
});

describe("outputPathInDirectory", () => {
  it("keeps the current output filename when selecting a new directory", () => {
    expect(
      outputPathInDirectory({
        directory: "/tmp/out",
        currentOutput: "/old/case/custom.mcompo.txt",
        inputPath: "/old/case/mgxs_library.h5",
        format: "multicompo",
      }),
    ).toBe("/tmp/out/custom.mcompo.txt");
  });

  it("uses the derived input-based filename when the current output is empty", () => {
    expect(
      outputPathInDirectory({
        directory: "/tmp/out/",
        currentOutput: "",
        inputPath: "/old/case/mgxs_library.h5",
        format: "macrolib",
      }),
    ).toBe("/tmp/out/mgxs_library.macrolib.txt");
  });

  it("handles the filesystem root without a double slash", () => {
    expect(
      outputPathInDirectory({
        directory: "/",
        currentOutput: "case.mcompo.txt",
        inputPath: "",
        format: "multicompo",
      }),
    ).toBe("/case.mcompo.txt");
  });
});
