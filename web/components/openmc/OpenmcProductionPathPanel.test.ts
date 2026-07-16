import { describe, expect, it } from "vitest";
import type { OpenmcExportExecutionResponse } from "../../lib/api";
import { openmcExportProvenanceVerified } from "../../lib/openmcExportGate";

function response(
  overrides: {
    mockMode?: boolean;
    integrity?: boolean;
    referenceBound?: boolean;
    transportReproducible?: boolean;
    status?: "complete" | "incomplete" | "legacy";
  } = {},
): OpenmcExportExecutionResponse {
  return {
    ok: true,
    mock_mode: overrides.mockMode ?? false,
    openmc_provenance: {
      status: overrides.status ?? "complete",
      integrity: { ok: overrides.integrity ?? true, issues: [] },
      capabilities: {
        reference_bound: overrides.referenceBound ?? true,
        export_replayable: true,
        transport_reproducible: overrides.transportReproducible ?? true,
      },
    },
  } as unknown as OpenmcExportExecutionResponse;
}

describe("OpenMC written-artifact gate", () => {
  it("never accepts a mock plan/export as written evidence", () => {
    expect(openmcExportProvenanceVerified(response({ mockMode: true }), true)).toBe(false);
  });

  it("fails closed on integrity or missing reference binding", () => {
    expect(openmcExportProvenanceVerified(response({ integrity: false }), false)).toBe(false);
    expect(openmcExportProvenanceVerified(response({ referenceBound: false }), false)).toBe(false);
  });

  it("requires complete transport-reproducible provenance in production", () => {
    expect(
      openmcExportProvenanceVerified(
        response({ status: "incomplete", transportReproducible: false }),
        true,
      ),
    ).toBe(false);
    expect(openmcExportProvenanceVerified(response(), true)).toBe(true);
  });

  it("allows a reference-bound, integrity-checked engineering export", () => {
    expect(
      openmcExportProvenanceVerified(
        response({ status: "incomplete", transportReproducible: false }),
        false,
      ),
    ).toBe(true);
  });
});
