import { describe, expect, it } from "vitest";
import {
  convertBundleManifestPath,
  convertBundleHref,
  convertNextSteps,
  convertObjectDescription,
  convertObjectLabel,
  convertValidateBundleHref,
} from "./convertNextSteps";
import type { ConvertPreflightInput, ConvertResponse } from "./api";

function response(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: true,
    converted: false,
    format: "multicompo",
    input_path: "/runs/case/mgxs_library.h5",
    output_path: "/runs/case/out.mcompo.txt",
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
    });
    expect(
      convertBundleHref(converted),
    ).toBe(
      "/builder?command=bundle&output_dir=%2Fruns%2Fcase%2Fbundle&mgxs=%2Fruns%2Fcase%2Fmgxs_library.h5&mcompo=%2Fruns%2Fcase%2Fout.mcompo.txt",
    );
    expect(convertBundleManifestPath(converted)).toBe(
      "/runs/case/bundle/manifest.json",
    );
    expect(convertValidateBundleHref(converted)).toBe(
      "/builder?command=validate-bundle&manifest=%2Fruns%2Fcase%2Fbundle%2Fmanifest.json",
    );
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

  it("points converted output toward preview, DONJON, bundle, and source inspect", () => {
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
    expect(steps.map((step) => step.id)).toEqual([
      "preview",
      "donjon",
      "bundle",
      "inspect",
    ]);
    expect(steps[0].href).toBe("#ascii-output-preview");
    expect(steps[1].title).toContain("L_MULTICOMPO");
    expect(steps[2].href).toContain("/builder?command=bundle");
    expect(steps[2].href).toContain("mgxs=");
    expect(steps[2].href).toContain("mcompo=");
    expect(steps[3].title).toContain("SPH/ADF");
  });

  it("blocks downstream handoff guidance when conversion fails", () => {
    const steps = convertNextSteps(response({ ok: false, preflight_ok: false }), null);
    expect(steps.map((step) => step.id)).toEqual(["fix", "inspect"]);
    expect(steps[0].status).toBe("blocked");
  });
});
