import { describe, expect, it } from "vitest";
import type { ConvertPreflightInput, ConvertResponse } from "./api";
import { convertDeliveryChecklist } from "./convertDeliveryChecklist";

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
    preflight: {
      schema: "openmc2donjon.mgxs-input-preflight.v1",
      decision: "accepted",
      output_issue: null,
      inputs: [],
    },
    cli_command: ["openmc2donjon", "/runs/case/mgxs_library.h5"],
    cli_command_text: "openmc2donjon /runs/case/mgxs_library.h5",
    ...overrides,
  };
}

function input(overrides: Partial<ConvertPreflightInput> = {}): ConvertPreflightInput {
  return {
    path: "/runs/case/mgxs_library.h5",
    ok: true,
    energy_groups: 7,
    legendre_order: 1,
    energy_mesh_id: "casmo_7",
    energy_mesh_name: "CASMO-7",
    mixtures: 9,
    issues: [],
    warnings: [],
    ...overrides,
  };
}

describe("convertDeliveryChecklist", () => {
  it("marks dry-run handoff as ready to write but not ready to preview or bundle", () => {
    const items = convertDeliveryChecklist(response(), input());

    expect(items.map((item) => [item.id, item.status])).toEqual([
      ["hdf5", "done"],
      ["gates", "done"],
      ["ascii", "ready"],
      ["preview", "pending"],
      ["bundle", "pending"],
      ["donjon", "pending"],
    ]);
    expect(items.find((item) => item.id === "ascii")?.action).toBe("convert");
  });

  it("marks a converted artifact as previewable and bundleable", () => {
    const items = convertDeliveryChecklist(
      response({
        dry_run: false,
        converted: true,
        output_exists: true,
        output_size: 1024,
      }),
      input({ sph_calculations: 2 }),
    );

    expect(items.map((item) => [item.id, item.status])).toEqual([
      ["hdf5", "done"],
      ["gates", "done"],
      ["ascii", "done"],
      ["preview", "ready"],
      ["bundle", "ready"],
      ["donjon", "ready"],
    ]);
    expect(items.find((item) => item.id === "preview")?.href).toBe(
      "#ascii-output-preview",
    );
    expect(items.find((item) => item.id === "bundle")?.href).toContain(
      "mcompo=%2Fruns%2Fcase%2Fout.mcompo.txt",
    );
    // The model ends at the product's destination: the DONJON guide.
    expect(items.find((item) => item.id === "donjon")?.href).toContain(
      "/donjon?ascii=",
    );
  });

  it("blocks downstream delivery when preflight fails", () => {
    const items = convertDeliveryChecklist(
      response({ ok: false, preflight_ok: false }),
      input({ ok: false, issues: ["missing total"] }),
    );

    expect(items.map((item) => [item.id, item.status])).toEqual([
      ["hdf5", "blocked"],
      ["gates", "blocked"],
      ["ascii", "blocked"],
      ["preview", "blocked"],
      ["bundle", "blocked"],
      ["donjon", "blocked"],
    ]);
  });

  it("surfaces skipped gates when conversion runs without preflight", () => {
    const items = convertDeliveryChecklist(
      response({ preflight: null }),
      null,
    );

    expect(items.find((item) => item.id === "hdf5")?.status).toBe("ready");
    expect(items.find((item) => item.id === "gates")?.status).toBe("skipped");
  });
});
