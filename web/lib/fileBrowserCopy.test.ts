import { describe, expect, it } from "vitest";
import {
  browseDialogTitle,
  hiddenEntriesNote,
  labelWithNoun,
} from "./fileBrowserCopy";

describe("fileBrowserCopy", () => {
  it("does not double the noun when the label already ends with it", () => {
    // Regression: /builder passed "input file" and the dialog rendered
    // "Browse for input file file".
    expect(browseDialogTitle("input file", "file")).toBe("Browse for input file");
    expect(browseDialogTitle("directory", "directory")).toBe("Browse for directory");
    expect(browseDialogTitle("output directory", "directory")).toBe(
      "Browse for output directory",
    );
  });

  it("appends the noun for short type labels", () => {
    expect(browseDialogTitle("HDF5", "file")).toBe("Browse for HDF5 file");
    expect(browseDialogTitle("JSON", "file")).toBe("Browse for JSON file");
  });

  it("pluralizes without doubling in the hidden-count footer", () => {
    // Regression: "3 non-input file files hidden".
    expect(hiddenEntriesNote(3, "input file", "file")).toBe(
      "3 non-input files hidden.",
    );
    expect(hiddenEntriesNote(1, "input file", "file")).toBe(
      "1 non-input file hidden.",
    );
    expect(hiddenEntriesNote(2, "HDF5", "file")).toBe("2 non-HDF5 files hidden.");
    expect(hiddenEntriesNote(2, "directory", "directory")).toBe(
      "2 non-directory entries hidden.",
    );
  });

  it("builds plural phrases for the recent/empty-state labels", () => {
    expect(labelWithNoun("input file", "files")).toBe("input files");
    expect(labelWithNoun("HDF5", "files")).toBe("HDF5 files");
    expect(labelWithNoun("output directory", "directories")).toBe(
      "output directories",
    );
  });
});
