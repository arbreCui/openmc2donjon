import { describe, expect, it } from "vitest";
import {
  convertBundleManifestPath,
  convertBundleHref,
  convertDonjonGuideHref,
  convertNextSteps,
  convertObjectDescription,
  convertObjectLabel,
  convertValidateBundleHref,
  convertWriterCompareHref,
  isCopyCliDestination,
} from "./convertNextSteps";
import type { ConvertPreflightInput, ConvertResponse } from "./api";

function response(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: true,
    converted: false,
    format: "multicompo",
    writer_backend: "ascii",
    input_path: "/runs/case/mgxs_library.h5",
    output_path: "/runs/case/out.mcompo.txt",
    summary_path: null,
    summary_written: false,
    output_exists: false,
    output_size: null,
    preflight_ok: true,
    preflight: null,
    cli_command: [],
    cli_command_text: "openmc2donjon /runs/case/mgxs_library.h5",
    ...overrides,
  };
}

describe("convert next steps", () => {
  it("labels DONJON object kind by output format", () => {
    expect(convertObjectLabel("multicompo")).toBe("L_MULTICOMPO");
    expect(convertObjectLabel("macrolib")).toBe("L_MACROLIB");
    expect(convertObjectDescription("multicompo")).toContain("Mapped");
    expect(convertObjectDescription("macrolib")).toContain("one-state");
  });

  it("builds bundle builder deep links with handoff paths prefilled", () => {
    const converted = response({
      dry_run: false,
      converted: true,
      output_exists: true,
      summary_path: "/runs/case/convert_summary.json",
      summary_written: true,
    });
    expect(
      convertBundleHref(converted),
    ).toBe(
      "/builder?command=bundle&output_dir=%2Fruns%2Fcase%2Fbundle&mgxs=%2Fruns%2Fcase%2Fmgxs_library.h5&mcompo=%2Fruns%2Fcase%2Fout.mcompo.txt&run_summary=%2Fruns%2Fcase%2Fconvert_summary.json",
    );
    expect(convertBundleManifestPath(converted)).toBe(
      "/runs/case/bundle/manifest.json",
    );
    expect(convertValidateBundleHref(converted)).toBe(
      "/builder?command=validate-bundle&manifest=%2Fruns%2Fcase%2Fbundle%2Fmanifest.json",
    );
    // manifest= is gated on the probe confirming the manifest exists;
    // without confirmation the guide works from the ASCII path directly.
    expect(convertDonjonGuideHref(converted)).toBe(
      "/donjon?ascii=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&deck=out_donjon_solve.x2m",
    );
    expect(
      convertDonjonGuideHref(converted, { manifestConfirmed: true }),
    ).toBe(
      "/donjon?ascii=%2Fruns%2Fcase%2Fout.mcompo.txt&format=multicompo&manifest=%2Fruns%2Fcase%2Fbundle%2Fmanifest.json&deck=out_donjon_solve.x2m",
    );
    expect(
      convertDonjonGuideHref(
        response({
          dry_run: false,
          converted: true,
          output_exists: true,
          preflight: {
            schema: "openmc2donjon.mgxs-input-preflight.v1",
            decision: "passed",
            output_issue: null,
            inputs: [
              {
                path: "/runs/case/mgxs_library.h5",
                ok: true,
                energy_groups: 7,
                legendre_order: 1,
                mixtures: 9,
                issues: [],
                warnings: [],
              },
            ],
          },
        }),
      ),
    ).toContain("&nmix=9");
    expect(
      convertBundleHref(
        response({
          format: "macrolib",
          output_path: "/runs/case/out.macrolib.txt",
        }),
      ),
    ).toContain("macrolib=%2Fruns%2Fcase%2Fout.macrolib.txt");
  });

  it("keeps dry-run next steps focused on writing and source review", () => {
    const steps = convertNextSteps(response(), null);
    expect(steps.map((step) => step.id)).toEqual(["write", "inspect", "object"]);
    expect(steps[0].body).toContain("did not write");
    expect(steps[1].href).toBe(
      "/inspect?path=%2Fruns%2Fcase%2Fmgxs_library.h5",
    );
  });

  it("points converted output toward preview, bundle, DONJON, and source inspect", () => {
    const steps = convertNextSteps(
      response({
        dry_run: false,
        converted: true,
        output_exists: true,
        output_size: 1234,
      }),
      {
        path: "/runs/case/mgxs_library.h5",
        ok: true,
        energy_groups: 7,
        legendre_order: 1,
        sph_calculations: 2,
        issues: [],
        warnings: [],
      } as ConvertPreflightInput,
    );
    // Canonical data-flow order: preview -> bundle -> DONJON, with the
    // prefilled bundle builder promoted to a ready step.
    expect(steps.map((step) => step.id)).toEqual([
      "preview",
      "bundle",
      "donjon",
      "inspect",
    ]);
    expect(steps[0].href).toBe("#ascii-output-preview");
    expect(steps[1].href).toContain("/builder?command=bundle");
    expect(steps[1].href).toContain("mgxs=");
    expect(steps[1].href).toContain("mcompo=");
    expect(steps[1].status).toBe("ready");
    expect(steps[2].title).toContain("L_MULTICOMPO");
    expect(steps[2].href).toContain("/donjon?");
    expect(steps[3].title).toContain("SPH/ADF");
  });

  it("adds a PyGan writer comparison step only for converted PyGan output", () => {
    const converted = response({
      dry_run: false,
      converted: true,
      output_exists: true,
      writer_backend: "pygan",
    });
    const steps = convertNextSteps(converted, null);

    // Writer validation is recommended before packaging and delivery.
    expect(steps.map((step) => step.id)).toEqual([
      "preview",
      "compare-writers",
      "bundle",
      "donjon",
      "inspect",
    ]);
    expect(steps[1].href).toBe(
      "/pygan?input_h5=%2Fruns%2Fcase%2Fmgxs_library.h5&format=multicompo&summary_json=%2Fruns%2Fcase%2Fwriter_compare.json&keep_dir=%2Fruns%2Fcase%2Fwriter_compare",
    );
    // /pygan never reads a "tab" query param; the link must not carry one.
    expect(steps[1].href).not.toContain("tab=");
    expect(convertWriterCompareHref(converted)).toBe(steps[1].href);
    expect(
      convertWriterCompareHref(
        response({
          dry_run: false,
          converted: true,
          output_exists: true,
          writer_backend: "pygan",
          output_path: "out.mcompo.txt",
        }),
      ),
    ).toContain("summary_json=writer_compare.json&keep_dir=writer_compare");
    expect(
      convertNextSteps(
        response({
          dry_run: false,
          converted: true,
          output_exists: true,
          writer_backend: "ascii",
        }),
        null,
      ).some((step) => step.id === "compare-writers"),
    ).toBe(false);
  });

  it("blocks downstream handoff guidance when conversion fails", () => {
    const steps = convertNextSteps(response({ ok: false, preflight_ok: false }), null);
    expect(steps.map((step) => step.id)).toEqual(["fix", "inspect"]);
    expect(steps[0].status).toBe("blocked");
  });

  it("marks copy-CLI destinations for the execute-to-copy boundary chip", () => {
    expect(isCopyCliDestination("/builder?command=bundle")).toBe(true);
    expect(isCopyCliDestination("/equivalence?kind=adf-sidecar")).toBe(true);
    expect(isCopyCliDestination("/donjon?ascii=%2Fout.txt")).toBe(true);
    expect(isCopyCliDestination("/donjon")).toBe(true);
    expect(isCopyCliDestination("/pygan?input_h5=x")).toBe(false);
    expect(isCopyCliDestination("/inspect?path=x")).toBe(false);
    expect(isCopyCliDestination("#ascii-output-preview")).toBe(false);
  });
});
