import { describe, expect, it } from "vitest";
import bundledSphFixture from "../../src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json";
import type {
  ConvertPreflightInput,
  ConvertResponse,
  ExecutionJob,
  OpenmcSphPhysicsSummary,
  WriterComparisonResponse,
} from "./api";
import {
  converterEvidenceLadder,
  donjonEvidenceLadder,
  evidenceStatusLabel,
  openmcSphEvidenceLadder,
  writerComparisonEvidenceLadder,
} from "./evidenceLadder";

describe("evidence ladder", () => {
  it("keeps a successful ASCII conversion separate from physics acceptance", () => {
    const stages = converterEvidenceLadder(
      convertResponse({
        dry_run: false,
        converted: true,
        output_exists: true,
        output_sha256: "abc",
      }),
      convertInput(),
    );

    expect(status(stages, "handoff-contract")).toBe("passed");
    expect(status(stages, "writer-validation")).toBe("passed");
    expect(status(stages, "donjon-ingest")).toBe("not-evaluated");
    expect(status(stages, "physics-equivalence")).toBe("not-evaluated");
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");
  });

  it("does not treat a PyGan write as a semantic comparison pass", () => {
    const stages = converterEvidenceLadder(
      convertResponse({
        dry_run: false,
        converted: true,
        output_exists: true,
        output_sha256: "abc",
        writer_backend: "pygan",
      }),
      convertInput(),
    );

    expect(status(stages, "writer-validation")).toBe("evidence-present");
    expect(summary(stages, "writer-validation")).toContain("separate required evidence");
  });

  it("marks SPH provenance as evidence without inventing equivalence acceptance", () => {
    const stages = converterEvidenceLadder(
      convertResponse({ physical_sph_required: true }),
      convertInput({ sph_applied: true, sph_kind: "openmc-ce-mg-rate" }),
    );

    expect(status(stages, "physics-equivalence")).toBe("evidence-present");
    expect(summary(stages, "physics-equivalence")).toContain("does not establish");
  });

  it("limits a live PyGan comparison pass to the writer layer", () => {
    const stages = writerComparisonEvidenceLadder(writerResponse());
    expect(status(stages, "writer-validation")).toBe("passed");
    expect(status(stages, "physics-equivalence")).toBe("not-evaluated");
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");
  });

  it("limits a completed DONJON ingest smoke to the ingest layer", () => {
    const stages = donjonEvidenceLadder(
      "Ingest smoke",
      executionJob({ status: "completed" }),
    );
    expect(status(stages, "donjon-ingest")).toBe("passed");
    expect(status(stages, "physics-equivalence")).toBe("not-evaluated");
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");
    expect(summary(stages, "reactor-validation")).toContain("ingest-only");
  });

  it("does not turn an isolated k-effective into reactor acceptance", () => {
    const stages = donjonEvidenceLadder(
      "Generic solve diagnostic",
      executionJob({ status: "completed", k_effective: 1.0082 }),
    );
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");
    expect(summary(stages, "reactor-validation")).toContain("no declared reference");
  });

  it("treats a recorded SPH fixture as evidence, never a physics pass", () => {
    const sphSummary = {
      ...(bundledSphFixture as unknown as OpenmcSphPhysicsSummary),
      evidence_audit: {
        origin: "mock_fixture",
        summary_path: null,
        summary_file_present: false,
        referenced_handoff_artifacts: [],
        all_referenced_handoff_artifacts_present: null,
        physics_acceptance: "not_evaluated",
        reactor_acceptance: "not_evaluated",
      },
    } satisfies OpenmcSphPhysicsSummary;
    const stages = openmcSphEvidenceLadder(sphSummary);

    expect(status(stages, "handoff-contract")).toBe("evidence-present");
    expect(status(stages, "donjon-ingest")).toBe("evidence-present");
    expect(status(stages, "physics-equivalence")).toBe("evidence-present");
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");
  });

  it("passes only the live SPH handoff and DONJON consume layers", () => {
    const sphSummary = {
      ...(bundledSphFixture as unknown as OpenmcSphPhysicsSummary),
      evidence_audit: {
        origin: "live_file",
        summary_path: "/tmp/physics_summary.json",
        summary_file_present: true,
        referenced_handoff_artifacts: [],
        all_referenced_handoff_artifacts_present: true,
        physics_acceptance: "not_evaluated",
        reactor_acceptance: "not_evaluated",
      },
    } satisfies OpenmcSphPhysicsSummary;
    const stages = openmcSphEvidenceLadder(sphSummary);

    expect(status(stages, "handoff-contract")).toBe("passed");
    expect(status(stages, "donjon-ingest")).toBe("passed");
    expect(status(stages, "physics-equivalence")).toBe("evidence-present");
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");
  });

  it("accepts native DRAGON SPH physics without claiming full-core acceptance", () => {
    const sphSummary: OpenmcSphPhysicsSummary = {
      ...(bundledSphFixture as unknown as OpenmcSphPhysicsSummary),
      schema: "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1",
      native_sph: {
        solver: "DRAGON SPH: with TRIVAT SPN",
        iterations: 70,
        epsilon: 1.0e-6,
        final_rms_factor_update: 9.45e-7,
        converged: true,
        one_speed_convergence_provable: true,
        final_flux_solve_converged: true,
        flux_nonconvergence_count: 0,
        factors_unmodified: true,
        negative_factor_correction_count: 0,
        oscillation_stop_count: 0,
        normal_end: true,
      },
      acceptance_checks: {
        donjon_normal_end: true,
        native_sph_converged: true,
        native_sph_factors_unmodified: true,
        native_sph_not_stopped_by_oscillation: true,
        one_speed_convergence_provable: true,
        final_flux_solve_converged: true,
        energy_coverage_passed: true,
        leakage_balance_available_when_required: true,
        reference_physical_balance_within_openmc_uncertainty: true,
        reference_rate_balance_within_openmc_uncertainty: true,
        donjon_keff_within_openmc_uncertainty: true,
        empirical_eigenvalue_multiplier_used: false,
        adf_used: false,
      },
      evidence_audit: {
        origin: "live_file",
        summary_path: "/tmp/physics_summary.json",
        summary_file_present: true,
        referenced_handoff_artifacts: [],
        all_referenced_handoff_artifacts_present: true,
        all_referenced_handoff_artifacts_hash_verified: true,
        evidence_integrity: {
          verified: true,
          issues: [],
          handoff_sha256_manifest_complete: true,
          all_handoff_sha256_match: true,
          converter_receipt: { valid: true, issues: [] },
          openmc_provenance: { valid: true, issues: [] },
          forbidden_corrections: {
            status: "verified_absent",
            adf: { used: false, evidence_status: "verified_absent", issues: [] },
            empirical_eigenvalue_multiplier: {
              used: false,
              evidence_status: "verified_absent",
              issues: [],
            },
          },
        },
        physics_acceptance: "passed",
        reactor_acceptance: "not_evaluated",
      },
    };
    const stages = openmcSphEvidenceLadder(sphSummary);

    expect(status(stages, "handoff-contract")).toBe("passed");
    expect(status(stages, "donjon-ingest")).toBe("passed");
    expect(status(stages, "physics-equivalence")).toBe("passed");
    expect(status(stages, "reactor-validation")).toBe("not-evaluated");

    sphSummary.native_sph!.one_speed_convergence_provable = false;
    expect(
      status(openmcSphEvidenceLadder(sphSummary), "donjon-ingest"),
    ).toBe("failed");
    sphSummary.native_sph!.one_speed_convergence_provable = true;
    sphSummary.acceptance_checks!.one_speed_convergence_provable = false;
    expect(
      status(openmcSphEvidenceLadder(sphSummary), "donjon-ingest"),
    ).toBe("failed");
  });

  it("shows no PASS stage when an old audit PASS lacks strict raw evidence", () => {
    const sphSummary: OpenmcSphPhysicsSummary = {
      ...(bundledSphFixture as unknown as OpenmcSphPhysicsSummary),
      schema: "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1",
      native_sph: {
        solver: "DRAGON SPH with SNT SN",
        iterations: 70,
        epsilon: 1.0e-6,
        final_rms_factor_update: 9.45e-7,
        converged: true,
        // Deliberately absent in an old summary despite its stored audit PASS.
        final_flux_solve_converged: true,
        flux_nonconvergence_count: 0,
        factors_unmodified: true,
        negative_factor_correction_count: 0,
        oscillation_stop_count: 0,
        normal_end: true,
      },
      acceptance_checks: {
        donjon_normal_end: true,
        native_sph_converged: true,
        native_sph_factors_unmodified: true,
        native_sph_not_stopped_by_oscillation: true,
        one_speed_convergence_provable: true,
        final_flux_solve_converged: true,
        energy_coverage_passed: true,
        leakage_balance_available_when_required: true,
        reference_physical_balance_within_openmc_uncertainty: true,
        reference_rate_balance_within_openmc_uncertainty: true,
        donjon_keff_within_openmc_uncertainty: true,
        empirical_eigenvalue_multiplier_used: false,
        adf_used: false,
      },
      evidence_audit: {
        origin: "live_file",
        summary_path: "/tmp/old-physics-summary.json",
        summary_file_present: true,
        referenced_handoff_artifacts: [],
        all_referenced_handoff_artifacts_present: true,
        physics_acceptance: "passed",
        reactor_acceptance: "not_evaluated",
      },
    };

    const stages = openmcSphEvidenceLadder(sphSummary);
    expect(stages.some((item) => item.status === "passed")).toBe(false);
    expect(status(stages, "handoff-contract")).toBe("evidence-present");
    expect(status(stages, "donjon-ingest")).toBe("failed");
    expect(status(stages, "physics-equivalence")).toBe("failed");
    expect(summary(stages, "physics-equivalence")).toContain(
      "stored audit says passed",
    );
  });

  it("uses an explicit not-evaluated badge", () => {
    expect(evidenceStatusLabel("not-evaluated")).toBe("NOT EVALUATED");
  });
});

function status(
  stages: ReturnType<typeof converterEvidenceLadder>,
  id: string,
) {
  return stages.find((item) => item.id === id)?.status;
}

function summary(
  stages: ReturnType<typeof converterEvidenceLadder>,
  id: string,
) {
  return stages.find((item) => item.id === id)?.summary ?? "";
}

function convertResponse(overrides: Partial<ConvertResponse> = {}): ConvertResponse {
  return {
    schema: "openmc2donjon.convert.v1",
    ok: true,
    dry_run: true,
    converted: false,
    format: "multicompo",
    writer_backend: "ascii",
    input_path: "/tmp/input.h5",
    output_path: "/tmp/output.mcompo.txt",
    summary_path: null,
    summary_written: false,
    output_exists: false,
    output_size: null,
    preflight_ok: true,
    preflight: {
      schema: "openmc2donjon.convert.preflight.v1",
      decision: "mgxs_input_contract_passed",
      output_issue: null,
      inputs: [convertInput()],
    },
    cli_command: ["openmc2donjon"],
    cli_command_text: "openmc2donjon",
    ...overrides,
  };
}

function convertInput(
  overrides: Partial<ConvertPreflightInput> = {},
): ConvertPreflightInput {
  return {
    path: "/tmp/input.h5",
    ok: true,
    energy_groups: 2,
    legendre_order: 0,
    issues: [],
    warnings: [],
    ...overrides,
  };
}

function writerResponse(
  overrides: Partial<WriterComparisonResponse> = {},
): WriterComparisonResponse {
  return {
    schema: "openmc2donjon.writer-comparison.v1",
    web_schema: "openmc2donjon.web.writer-comparison.v1",
    mock_mode: false,
    input_h5: "/tmp/input.h5",
    format: "multicompo",
    ok: true,
    rtol: 1e-6,
    atol: 1e-8,
    compared_payloads: 39,
    compared_real_payloads: 18,
    max_abs_diff: 4e-7,
    max_rel_diff: 4e-8,
    issue_count: 0,
    issues: [],
    cli_command: ["openmc2donjon", "compare-writers"],
    cli_command_text: "openmc2donjon compare-writers",
    summary_json: null,
    keep_dir: null,
    ...overrides,
  };
}

function executionJob(overrides: Partial<ExecutionJob> = {}): ExecutionJob {
  return {
    schema: "openmc2donjon.execution-job.v1",
    job_id: "job-1",
    run_id: "job-1",
    operation: "donjon",
    status: "running",
    created_at: 0,
    started_at: 0,
    finished_at: null,
    message: "running",
    result_path: null,
    deck_path: null,
    k_effective: null,
    return_code: null,
    log_tail: "",
    working_directory: null,
    archive_root: null,
    run_directory: null,
    request_path: null,
    status_path: null,
    artifacts_path: null,
    log_path: null,
    staged_manifest_path: null,
    runtime_output_directory: null,
    ...overrides,
  };
}
