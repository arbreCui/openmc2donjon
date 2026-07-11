import { describe, expect, it } from "vitest";
import { containingDirectory, outputPathInDirectory } from "./outputBrowse";

describe("outputPathInDirectory", () => {
  it("keeps the current filename inside the picked directory", () => {
    expect(outputPathInDirectory("/runs/case", "/old/dir/adf.h5", "x.h5")).toBe(
      "/runs/case/adf.h5",
    );
  });

  it("falls back to the default filename when the field is empty", () => {
    expect(outputPathInDirectory("/runs/case/", "", "face_flux.h5")).toBe(
      "/runs/case/face_flux.h5",
    );
  });

  it("handles the filesystem root", () => {
    expect(outputPathInDirectory("/", "", "out.csv")).toBe("/out.csv");
  });
});

describe("containingDirectory", () => {
  it("strips the filename segment", () => {
    expect(containingDirectory("/runs/case/file.h5")).toBe("/runs/case");
  });

  it("keeps explicit directories", () => {
    expect(containingDirectory("/runs/case/")).toBe("/runs/case/");
  });

  it("falls back to home for bare or empty values", () => {
    expect(containingDirectory("file.h5")).toBe("~");
    expect(containingDirectory("")).toBe("~");
    expect(containingDirectory("~")).toBe("~");
  });
});
