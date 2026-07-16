import { describe, expect, it } from "vitest";
import {
  browserInitialPath,
  buildCompareCli,
  optionalNumberError,
  pyganWorkflowHrefs,
  PYGAN_ATOL_DEFAULT,
  PYGAN_RTOL_DEFAULT,
  toleranceError,
  toleranceValue,
} from "./pyganCompare";

const BASE = {
  inputH5: "/runs/handoff.h5",
  format: "multicompo" as const,
  rootName: "CPO",
  comment: "",
  mixtures: "",
  burnup: "",
  hFactorDefault: "",
  rtol: "1e-6",
  atol: "1e-8",
  summaryJson: "",
  keepDir: "",
};

describe("toleranceError", () => {
  it("accepts empty (default) and numeric text", () => {
    expect(toleranceError("")).toBeNull();
    expect(toleranceError("  ")).toBeNull();
    expect(toleranceError("1e-6")).toBeNull();
    expect(toleranceError(" 0.5 ")).toBeNull();
  });

  it("rejects non-numeric text so the web run cannot silently diverge from the CLI", () => {
    expect(toleranceError("1e-6x")).not.toBeNull();
    expect(toleranceError("abc")).not.toBeNull();
  });
});

describe("toleranceValue", () => {
  it("treats empty as the default instead of Number('') === 0", () => {
    expect(toleranceValue("", PYGAN_RTOL_DEFAULT)).toBe(PYGAN_RTOL_DEFAULT);
    expect(toleranceValue("  ", PYGAN_ATOL_DEFAULT)).toBe(PYGAN_ATOL_DEFAULT);
  });

  it("parses valid numeric text", () => {
    expect(toleranceValue(" 1e-4 ", PYGAN_RTOL_DEFAULT)).toBe(1e-4);
  });
});

describe("buildCompareCli tolerances", () => {
  it("omits default tolerances", () => {
    expect(buildCompareCli(BASE)).toBe(
      "openmc2donjon compare-writers /runs/handoff.h5 --format multicompo",
    );
  });

  it("treats numerically-equal spellings of the default as the default", () => {
    const cli = buildCompareCli({ ...BASE, rtol: "1.0e-6", atol: "0.00000001" });
    expect(cli).not.toContain("--rtol");
    expect(cli).not.toContain("--atol");
  });

  it("embeds non-default numeric tolerances verbatim", () => {
    const cli = buildCompareCli({ ...BASE, rtol: "1e-4", atol: "1e-9" });
    expect(cli).toContain("--rtol 1e-4");
    expect(cli).toContain("--atol 1e-9");
  });

  it("never embeds a non-numeric tolerance the web run would reject", () => {
    const cli = buildCompareCli({ ...BASE, rtol: "1e-6x", atol: "abc" });
    expect(cli).not.toContain("1e-6x");
    expect(cli).not.toContain("abc");
    // The form blocks Run compare for the same inputs.
    expect(toleranceError("1e-6x")).not.toBeNull();
    expect(toleranceError("abc")).not.toBeNull();
  });
});

describe("Converter and Project context", () => {
  it("keeps the exact state-changing writer options in the comparison CLI", () => {
    const cli = buildCompareCli({
      ...BASE,
      rootName: "LIB",
      comment: "state A",
      mixtures: "fuel, reflector",
      burnup: "12.5",
      hFactorDefault: "1.25",
    });
    expect(cli).toContain("--root-name LIB");
    expect(cli).toContain("--comment 'state A'");
    expect(cli).toContain("--burnup 12.5");
    expect(cli).toContain("--h-factor-default 1.25");
    expect(cli).toContain("--mixture fuel --mixture reflector");
    expect(optionalNumberError("not-a-number", "Burnup")).not.toBeNull();
  });

  it("returns a comparison result to Project, Converter, Bundle, and DONJON", () => {
    const hrefs = pyganWorkflowHrefs({
      projectRoot: "/runs/a",
      componentId: "fuel",
      inputH5: "/runs/a/components/fuel.h5",
      outputPath: "/runs/a/outputs/fuel.mcompo.txt",
      receiptPath: "/runs/a/outputs/fuel.mcompo.txt.convert.json",
      format: "multicompo",
      rootName: "LIB",
      comment: "fuel state",
      mixtures: "M1,M2",
      burnup: "0",
      hFactorDefault: "",
    });
    expect(hrefs.project).toContain("component=fuel");
    expect(hrefs.converter).toContain("writer_backend=pygan");
    expect(hrefs.converter).toContain("root_name=LIB");
    expect(hrefs.bundle).toContain("run_summary=");
    expect(hrefs.donjon).toContain("ascii=%2Fruns%2Fa%2Foutputs%2Ffuel.mcompo.txt");
  });
});

describe("browserInitialPath", () => {
  it("starts from the field's directory when the field holds a file path", () => {
    expect(
      browserInitialPath("input", "/mock/home/openmc-runs/c5g7/handoff.h5", "", "", ""),
    ).toBe("/mock/home/openmc-runs/c5g7");
    expect(
      browserInitialPath("summary", "", "/runs/c5g7/writer_compare.json", "", ""),
    ).toBe("/runs/c5g7");
  });

  it("opens the keep target on its parent directory", () => {
    expect(browserInitialPath("keep", "", "", "/runs/c5g7/writer_compare", "")).toBe(
      "/runs/c5g7",
    );
  });

  it("falls back to the backend-resolved home instead of the mock tree root", () => {
    expect(browserInitialPath("input", "", "", "", "")).toBe("~");
    expect(browserInitialPath(null, "", "", "", "")).toBe("~");
  });

  it("uses the saved prefix directory when the field is empty", () => {
    expect(browserInitialPath("input", "", "", "", "/shared/runs/")).toBe("/shared/runs/");
    expect(browserInitialPath("input", "", "", "", "/shared/runs/handoff.h5")).toBe(
      "/shared/runs",
    );
  });
});
