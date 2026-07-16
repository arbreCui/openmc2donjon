import { describe, expect, it } from "vitest";
import type { OpenmcProvenance } from "./api";
import {
  openmcProvenanceView,
  provenanceArtifact,
  shortDigest,
} from "./openmcProvenance";

function fixture(
  overrides: Partial<OpenmcProvenance> = {},
): OpenmcProvenance {
  return {
    schema: "openmc2donjon.openmc-provenance.v1",
    status: "complete",
    issues: [],
    missing: [],
    digest_sha256: "a".repeat(64),
    integrity: { ok: true, issues: [] },
    capabilities: {
      reference_bound: true,
      export_replayable: true,
      transport_reproducible: true,
    },
    fingerprints: {
      model_sha256: "b".repeat(64),
      transport_sha256: "c".repeat(64),
    },
    producer: {
      name: "openmc2donjon",
      version: "0.1.4",
      python_version: "3.12",
      platform: "test",
    },
    openmc: {
      version: "0.15.2",
      git_sha1: null,
      statepoint_format_version: "18.1",
    },
    statepoint: {
      filetype: "statepoint",
      is_openmc_statepoint: true,
      date_and_time: null,
    },
    source_mode: "recipe-statepoint",
    statepoint_loaded: true,
    evidence: {
      simulation_sources: {},
      openmc_version_sources: {},
    },
    input_closure: {
      attested_complete: true,
      method: "recipe-provenance-files",
    },
    handoff: {
      algorithm: "openmc2donjon-hdf5-payload-sha256-v1",
      payload_sha256: "f".repeat(64),
    },
    artifacts: [
      {
        role: "recipe",
        path: "/case/export_recipe.py",
        required: true,
        present: true,
        size_bytes: 100,
        sha256: "d".repeat(64),
      },
    ],
    simulation: {
      run_mode: "eigenvalue",
      particles: 1000,
      batches: 100,
      inactive: 20,
      generations_per_batch: 1,
      seed: 1,
      stride: null,
      threads: null,
      mpi_ranks: null,
    },
    temperature: null,
    nuclear_data: {
      cross_sections: null,
      cross_sections_source: null,
      selection: "used-materials",
      library_count: 2,
      total_size_bytes: 1000,
      libraries_manifest_sha256: "e".repeat(64),
      libraries: [],
    },
    user_metadata: {},
    ...overrides,
  };
}

describe("OpenMC provenance presentation", () => {
  it("distinguishes full transport replay from a frozen downstream reference", () => {
    expect(openmcProvenanceView(fixture()).label).toBe("COMPLETE");

    const referenceOnly = fixture({
      status: "incomplete",
      missing: ["nuclear_data.libraries_manifest_sha256"],
      capabilities: {
        reference_bound: true,
        export_replayable: true,
        transport_reproducible: false,
      },
    });
    const view = openmcProvenanceView(referenceOnly);
    expect(view.label).toBe("REFERENCE BOUND");
    expect(view.tone).toBe("warn");
    expect(view.summary).toContain("Native DRAGON SPH");
  });

  it("fails closed when embedded integrity is invalid", () => {
    const view = openmcProvenanceView(
      fixture({ integrity: { ok: false, issues: ["digest mismatch"] } }),
    );
    expect(view.label).toBe("UNBOUND");
    expect(view.tone).toBe("fail");
    expect(view.referenceBound).toBe(false);
    expect(view.exportReplayable).toBe(false);
    expect(view.transportReproducible).toBe(false);
  });

  it("treats a capability claim without read-back integrity as unverified", () => {
    const view = openmcProvenanceView(fixture({ integrity: undefined }));
    expect(view.label).toBe("UNBOUND");
    expect(view.referenceBound).toBe(false);
    expect(view.transportReproducible).toBe(false);
  });

  it("finds source artifacts without inventing absent values", () => {
    const provenance = fixture();
    expect(provenanceArtifact(provenance, "recipe")?.path).toBe(
      "/case/export_recipe.py",
    );
    expect(provenanceArtifact(provenance, "settings")).toBeNull();
    expect(shortDigest(null)).toBe("not recorded");
    expect(shortDigest("1234567890abcdef")).toBe("1234567890ab");
  });
});
