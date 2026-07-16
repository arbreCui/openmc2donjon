import { describe, expect, it } from "vitest";
import bundledFixture from "../../src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json";
import type { OpenmcSphPhysicsSummary } from "./api";
import {
  evidenceAuditPresentation,
  forbiddenCorrectionAbsenceState,
  verifiedForbiddenCorrectionAbsenceState,
  formatScatterTreatment,
  formatPhysicsNumber,
  nativeDragonSphAcceptancePassed,
  nativeSphValidatorHref,
  openmcSphConvertHref,
  productionEvidenceRows,
  reactionRatePreservationRows,
  sphUpdatePolicyRows,
  summaryStatus,
  topSphDeviationRows,
} from "./openmcSphSummary";

const SUMMARY: OpenmcSphPhysicsSummary = {
  schema: "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
  route:
    "Fine OpenMC CE full core + assembly-scale homogenized OpenMC MG full core -> OpenMC-side SPH",
  handoff_dir: "/mock",
  mixture_count: 2,
  energy_groups: 33,
  legendre_order: 3,
  handoff_scatter: {
    format: "legendre",
    legendre_order: 3,
  },
  mg_macro_scatter: {
    scatter_format: "histogram",
    histogram_bins: 16,
    legendre_order: null,
  },
  mixture_names: ["A", "B"],
  decisions: {
    openmc_sph: "openmc2donjon_openmc_sph_sidecar_passed",
    sph_augment: "openmc2donjon_sph_augment_passed",
  },
  normalization: {
    method: "power",
    factor: 1.0,
    formula: "sph = mg / ce",
  },
  sph_target: "flux",
  zero_flux_policy: "reject",
  identity_bin_count: 0,
  flux_floor_rel: null,
  floored_bin_count: 0,
  freeze_groups: null,
  frozen_group_bin_count: 0,
  flux_uncertainty: {
    ce_max_relative_std_dev: 0.01,
    mg_max_relative_std_dev: 0.02,
    ce_dataset: "openmc_volume_flux",
    mg_dataset: "openmc_mg_flux",
  },
  quality: {
    decision: "openmc_ce_mg_sph_production_quality",
    structural_passed: true,
    production_ready: true,
    demonstration_quality: true,
    max_flux_relative_std_dev: 0.02,
    production_flux_relative_std_dev_threshold: 0.05,
    demonstration_flux_relative_std_dev_threshold: 0.3,
    notes: ["ok"],
  },
  sph: {
    kind: "openmc-ce-mg",
    real: true,
    applied_to_xs: false,
    minimum: 0.8,
    maximum: 1.2,
    mean: 1.0,
    max_abs_delta_from_unity: 0.2,
    clipped_count: 0,
  },
  reaction_rate_preservation: {
    reference: "CE-tallied MGXS * CE volume flux",
    current_solve: {
      max_relative_residual: 0.24,
      mean_relative_residual: 0.03,
      valid_bins: 165,
    },
    after_sph_update_frozen_flux: {
      max_relative_residual: 5.0e-12,
      mean_relative_residual: 1.5e-12,
      valid_bins: 165,
    },
  },
  handoff: {
    augmented_hdf5_has_sph: true,
    ascii_nsp_block_count: 2,
    accepted_sph_consumption_format: "macrolib",
    macrolib_ascii_nsp_block_count: 33,
    ascii_path: "/mock/out.macrolib.txt",
    macrolib_ascii_path: "/mock/out.macrolib.txt",
    augmented_hdf5_path: "/mock/mgxs_with_sph.h5",
  },
  donjon_consumption: {
    status: "passed",
    mode: "DSPH/MAC PN+SN consume smoke",
    script: "examples/openmc_ce_mg_33g_sph_minicase/run_donjon_consume_smoke.sh",
    result_path: "/mock/donjon.result",
    expected_mix3_g1: 1.05946788,
    target_mix: 2,
    expected_g1: 1.05946788,
    pn_var_value: 1.05946791,
    sn_var_value: 1.05946791,
    pn_ntot0_ratio: 1.05946786,
    sn_ntot0_ratio: 0.999999982,
  },
  donjon_solve_diagnostic: {
    status: "recorded",
    decision: "donjon_solve_diagnostic_recorded",
    script: "examples/openmc_ce_mg_33g_sph_minicase/run_donjon_solve_diagnostic.sh",
    geometry: "3-region reflective CAR2D slab",
    note: "diagnostic only",
    modes: {
      diffusion: {
        k_effective: 0.8899511,
        vs_openmc_ce: {
          flux_shape_mean_relative_residual: 0.0755294,
          flux_shape_max_relative_residual: 0.761238,
        },
      },
      spn3: {
        k_effective: 0.9084644,
        vs_openmc_ce: {
          flux_shape_mean_relative_residual: 0.0515226,
          flux_shape_max_relative_residual: 0.767714,
        },
      },
    },
  },
  per_mixture: [
    {
      mixture: "A",
      ce_flux_min: 1,
      ce_flux_max: 2,
      mg_flux_min: 1,
      mg_flux_max: 2,
      normalized_mg_over_ce_min: 0.9,
      normalized_mg_over_ce_max: 1.1,
      sph_min: 0.9,
      sph_max: 1.1,
      sph_mean: 1,
      max_abs_sph_minus_1: 0.1,
    },
    {
      mixture: "B",
      ce_flux_min: 1,
      ce_flux_max: 2,
      mg_flux_min: 1,
      mg_flux_max: 2,
      normalized_mg_over_ce_min: 0.7,
      normalized_mg_over_ce_max: 1.3,
      sph_min: 0.7,
      sph_max: 1.3,
      sph_mean: 1,
      max_abs_sph_minus_1: 0.3,
    },
  ],
};

describe("openmcSphSummary", () => {
  it("recognizes a live native DRAGON SPH physics pass", () => {
    const native = nativeSummary();
    expect(nativeDragonSphAcceptancePassed(native)).toBe(true);
    expect(summaryStatus(native)).toMatchObject({
      tone: "pass",
      label: "native SPH physics pass",
    });
    expect(openmcSphConvertHref(native)).toBeNull();
    const validator = new URL(nativeSphValidatorHref(native)!, "http://localhost");
    expect(validator.pathname).toBe("/builder");
    expect(validator.searchParams.get("command")).toBe("validate-native-sph");
    expect(validator.searchParams.get("reference_h5")).toBe(
      "/mock/mgxs_with_sph.h5",
    );
    expect(validator.searchParams.get("result_listing")).toBe(
      "/tmp/donjon.result",
    );
    expect(validator.searchParams.get("execution_deck")).toBe(
      "/tmp/native_sph.x2m",
    );
    expect(validator.searchParams.get("converter_receipt")).toBe(
      "/tmp/converter_receipt.json",
    );
    expect(productionEvidenceRows(native)[3]).toMatchObject({
      label: "DONJON vs OpenMC",
      value: "-71.6 pcm",
    });
  });

  it("does not accept a normal end when the final transport solve failed", () => {
    const native = nativeSummary();
    native.native_sph!.final_flux_solve_converged = false;
    expect(summaryStatus(native)).toMatchObject({
      tone: "warn",
      label: "native SPH review required",
    });
  });

  it("requires both one-speed convergence proof records", () => {
    const missingValidatorProof = nativeSummary();
    delete missingValidatorProof.acceptance_checks!
      .one_speed_convergence_provable;
    expect(summaryStatus(missingValidatorProof).tone).toBe("warn");

    const missingSolverProof = nativeSummary();
    delete missingSolverProof.native_sph!.one_speed_convergence_provable;
    expect(summaryStatus(missingSolverProof).tone).toBe("warn");

    const contradictedSolverProof = nativeSummary();
    contradictedSolverProof.native_sph!.one_speed_convergence_provable = false;
    expect(summaryStatus(contradictedSolverProof).tone).toBe("warn");
  });

  it("blocks an old audit PASS when strict raw solver evidence is missing", () => {
    const oldSummary = nativeSummary();
    delete oldSummary.native_sph!.one_speed_convergence_provable;

    expect(oldSummary.evidence_audit?.physics_acceptance).toBe("passed");
    expect(nativeDragonSphAcceptancePassed(oldSummary)).toBe(false);
    expect(summaryStatus(oldSummary)).toMatchObject({
      tone: "warn",
      label: "native SPH review required",
    });
    expect(evidenceAuditPresentation(oldSummary)).toEqual({
      label: "physics acceptance blocked",
      detail:
        "The stored audit says passed, but the current strict contract is missing or contradicts a required acceptance check or raw solver record. Revalidate this summary before use.",
      passed: false,
    });
  });

  it("requires audit, validator checks, and raw records to agree", () => {
    const contradictedCheck = nativeSummary();
    contradictedCheck.acceptance_checks!.final_flux_solve_converged = false;
    expect(nativeDragonSphAcceptancePassed(contradictedCheck)).toBe(false);

    const contradictedRawRecord = nativeSummary();
    contradictedRawRecord.native_sph!.flux_nonconvergence_count = 1;
    expect(nativeDragonSphAcceptancePassed(contradictedRawRecord)).toBe(false);

    const missingArtifactAudit = nativeSummary();
    missingArtifactAudit.evidence_audit!.all_referenced_handoff_artifacts_present =
      false;
    expect(nativeDragonSphAcceptancePassed(missingArtifactAudit)).toBe(false);

    const invalidIntegrity = nativeSummary();
    invalidIntegrity.evidence_audit!.evidence_integrity!.verified = false;
    invalidIntegrity.evidence_audit!.evidence_integrity!.issues = [
      "execution deck SHA-256 mismatch",
    ];
    expect(nativeDragonSphAcceptancePassed(invalidIntegrity)).toBe(false);
    expect(summaryStatus(invalidIntegrity)).toMatchObject({
      label: "native evidence integrity blocked",
      tone: "warn",
    });
  });

  it("treats unknown forbidden-correction evidence as blocked, never PASS", () => {
    expect(forbiddenCorrectionAbsenceState(false)).toBe("pass");
    expect(forbiddenCorrectionAbsenceState(true)).toBe("fail");
    expect(forbiddenCorrectionAbsenceState(null)).toBe("unknown");
    expect(forbiddenCorrectionAbsenceState(undefined)).toBe("unknown");
    expect(
      verifiedForbiddenCorrectionAbsenceState(false, "verified_absent"),
    ).toBe("pass");
    expect(verifiedForbiddenCorrectionAbsenceState(false, "not_provable")).toBe(
      "unknown",
    );
    expect(verifiedForbiddenCorrectionAbsenceState(false, undefined)).toBe(
      "unknown",
    );
    expect(verifiedForbiddenCorrectionAbsenceState(false, "observed")).toBe(
      "fail",
    );
    expect(verifiedForbiddenCorrectionAbsenceState(true, "verified_absent")).toBe(
      "fail",
    );

    const unknown = nativeSummary();
    unknown.acceptance_checks!.adf_used = null;
    expect(nativeDragonSphAcceptancePassed(unknown)).toBe(false);

    unknown.evidence_audit!.evidence_integrity!.forbidden_corrections = {
      status: "not_provable",
      issues: ["execution deck missing"],
    };
    expect(sphUpdatePolicyRows(unknown)).toContainEqual(
      expect.objectContaining({
        label: "Forbidden numerical fallback",
        value: "not established",
      }),
    );

    const verified = nativeSummary();
    expect(sphUpdatePolicyRows(verified)).toContainEqual(
      expect.objectContaining({
        label: "Forbidden numerical fallback",
        value: "verified absent",
      }),
    );
  });

  it("keeps an OpenMC-side NSPH handoff distinct from physics acceptance", () => {
    expect(summaryStatus(SUMMARY)).toMatchObject({
      tone: "warn",
      label: "SPH handoff present — validation required",
    });
  });

  it("warns when SPH is present but only demonstration-quality", () => {
    expect(
      summaryStatus({
        ...SUMMARY,
        quality: {
          ...SUMMARY.quality!,
          decision: "openmc_ce_mg_sph_demonstration_quality",
          production_ready: false,
          max_flux_relative_std_dev: 0.2,
        },
      }),
    ).toMatchObject({
      tone: "warn",
      label: "demo-quality NSPH",
    });
  });

  it("warns when SPH is present but flux statistics need review", () => {
    expect(
      summaryStatus({
        ...SUMMARY,
        quality: {
          ...SUMMARY.quality!,
          decision: "openmc_ce_mg_sph_statistical_review_required",
          production_ready: false,
          demonstration_quality: false,
          max_flux_relative_std_dev: 0.6,
        },
      }),
    ).toMatchObject({
      tone: "warn",
      label: "statistics need review",
    });
  });

  it("sorts mixtures by largest SPH deviation", () => {
    expect(topSphDeviationRows(SUMMARY).map((row) => row.mixture)).toEqual([
      "B",
      "A",
    ]);
  });

  it("formats compact physics numbers", () => {
    expect(formatPhysicsNumber(0)).toBe("0");
    expect(formatPhysicsNumber(0.000000123)).toBe("1.230e-7");
    expect(formatPhysicsNumber(1.2300)).toBe("1.23");
  });

  it("describes the Pn handoff and Hn MG macro treatments separately", () => {
    expect(formatScatterTreatment(SUMMARY)).toBe("P3 handoff · H16 MG macro");
  });

  it("populates SPH update policy rows for the fixture-shaped summary", () => {
    const rows = sphUpdatePolicyRows(SUMMARY);

    expect(rows.map((row) => row.id)).toEqual(["target", "zero-flux"]);
    expect(rows[0]).toMatchObject({ label: "SPH target", value: "flux" });
    expect(rows[0].detail).toContain("Flux-matching");
    expect(rows[1]).toMatchObject({
      label: "Zero-flux policy",
      value: "reject",
    });
    expect(rows[1].detail).toContain("fail the update");
  });

  it("renders the SPH update policy block from the bundled mock fixture", () => {
    const rows = sphUpdatePolicyRows(bundledFixture as OpenmcSphPhysicsSummary);

    expect(rows.map((row) => row.id)).toEqual(["target", "zero-flux"]);
    expect(rows[0]).toMatchObject({ label: "SPH target", value: "flux" });
    expect(rows[1]).toMatchObject({
      label: "Zero-flux policy",
      value: "reject",
    });
    expect(rows[1].detail).toContain("fail the update");
  });

  it("omits SPH update policy rows for summaries without the new fields", () => {
    expect(
      sphUpdatePolicyRows({
        ...SUMMARY,
        sph_target: undefined,
        zero_flux_policy: undefined,
        identity_bin_count: undefined,
        flux_floor_rel: undefined,
        floored_bin_count: undefined,
        freeze_groups: undefined,
        frozen_group_bin_count: undefined,
      }),
    ).toEqual([]);
  });

  it("surfaces the rate-preserving SPH update policy fields when present", () => {
    const rows = sphUpdatePolicyRows({
      ...SUMMARY,
      sph_target: "rate",
      zero_flux_policy: "identity",
      identity_bin_count: 4,
      flux_floor_rel: 1.0e-3,
      floored_bin_count: 6,
      freeze_groups: [1, 31],
      frozen_group_bin_count: 10,
    });

    expect(rows.map((row) => row.id)).toEqual([
      "target",
      "zero-flux",
      "flux-floor",
      "freeze-groups",
    ]);
    expect(rows[0]).toMatchObject({ label: "SPH target", value: "rate" });
    expect(rows[0].detail).toContain("Rate-preserving");
    expect(rows[1]).toMatchObject({
      label: "Zero-flux policy",
      value: "identity",
    });
    expect(rows[1].detail).toContain("4 bin(s)");
    expect(rows[2]).toMatchObject({ label: "Flux floor", value: "0.001" });
    expect(rows[2].detail).toContain("6 bin(s)");
    expect(rows[3]).toMatchObject({
      label: "Frozen groups",
      value: "1, 31",
    });
    expect(rows[3].detail).toContain("10 bin(s)");
  });

  it("keeps flux-target reject policies readable in the update policy rows", () => {
    const rows = sphUpdatePolicyRows({
      ...SUMMARY,
      sph_target: "flux",
      zero_flux_policy: "reject",
      identity_bin_count: 0,
    });

    expect(rows.map((row) => row.id)).toEqual(["target", "zero-flux"]);
    expect(rows[0].detail).toContain("Flux-matching");
    expect(rows[1].detail).toContain("fail the update");
  });

  it("extracts current and frozen-flux reaction-rate preservation diagnostics", () => {
    const rows = reactionRatePreservationRows(SUMMARY);

    expect(rows.map((row) => row.id)).toEqual(["current", "frozen"]);
    expect(rows[0]).toMatchObject({
      label: "Current OpenMC MG solve",
      maxResidual: 0.24,
      validBins: 165,
    });
    expect(rows[1].maxResidual).toBe(5.0e-12);
  });

  it("builds production evidence rows from the physics summary", () => {
    const rows = productionEvidenceRows(SUMMARY);

    expect(rows.map((row) => row.id)).toEqual([
      "flux",
      "sph",
      "rates",
      "handoff",
      "donjon",
      "donjon-solve",
    ]);
    expect(rows[0]).toMatchObject({
      label: "OpenMC flux uncertainty",
      value: "0.01 / 0.02",
    });
    expect(rows[2]).toMatchObject({
      label: "Reaction-rate preservation",
      value: "5.000e-12",
    });
    expect(rows[3].detail).toContain("MACROLIB GROUP/*/NSPH");
    expect(rows[4]).toMatchObject({
      label: "DONJON consume smoke",
      value: "passed",
    });
    expect(rows[4].detail).toContain("target mix 2 group 1 NSPH 1.059");
    expect(rows[4].detail).toContain("PN NTOT0 ratio 1.059");
    expect(rows[5]).toMatchObject({
      label: "DONJON solve diagnostic",
      value: "SPN3 k=0.9085",
    });
    expect(rows[5].detail).toContain("CE flux-shape residual mean 0.05152");
  });

  it("builds a converter deep link for the SPH-augmented handoff", () => {
    const href = openmcSphConvertHref(SUMMARY);

    expect(href).not.toBeNull();
    const url = new URL(href!, "http://localhost:3000");
    expect(url.pathname).toBe("/convert");
    expect(url.searchParams.get("intent")).toBe("openmc-sph");
    expect(url.searchParams.get("input")).toBe("/mock/mgxs_with_sph.h5");
    expect(url.searchParams.get("output")).toBe("/mock/out.macrolib.txt");
    expect(url.searchParams.get("format")).toBe("macrolib");
    expect(url.searchParams.get("writer_backend")).toBe("ascii");
    expect(url.searchParams.get("check")).toBe("1");
    expect(url.searchParams.get("production")).toBe("1");
    // Terminology: the augmented file is "SPH-augmented", never "corrected".
    expect(url.searchParams.get("comment")).toBe(
      "OpenMC-side SPH-augmented handoff",
    );
  });

  it("does not build a converter deep link without augmented handoff paths", () => {
    expect(
      openmcSphConvertHref({
        ...SUMMARY,
        handoff: {
          ...SUMMARY.handoff,
          augmented_hdf5_path: null,
        },
      }),
    ).toBeNull();
    expect(
      openmcSphConvertHref({
        ...SUMMARY,
        handoff: {
          ...SUMMARY.handoff,
          ascii_path: null,
          macrolib_ascii_path: null,
        },
      }),
    ).toBeNull();
  });
});

function nativeSummary(): OpenmcSphPhysicsSummary {
  return {
    ...SUMMARY,
    schema: "openmc2donjon.openmc-dragon-native-sph-physics-summary.v1",
    requested_path: "/tmp/physics_summary.json",
    route: "OpenMC CE fine -> Converter -> DRAGON native SPH -> DONJON SPN",
    handoff: {
      ...SUMMARY.handoff,
      augmented_hdf5_has_sph: false,
      reference_macrolib_path: "/tmp/reference.macrolib.txt",
      verification_macrolib_path: "/tmp/verify.macrolib.txt",
      result_listing_path: "/tmp/donjon.result",
      execution_deck_path: "/tmp/native_sph.x2m",
      energy_coverage_path: "/tmp/energy_coverage.json",
      converter_receipt_path: "/tmp/converter_receipt.json",
    },
    native_sph: {
      solver: "DRAGON SPH: with TRIVAT SPN",
      iterations: 70,
      epsilon: 1.0e-6,
      final_max_factor_update: 5.7e-6,
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
    eigenvalue_validation: {
      openmc_keff: 1.112311,
      openmc_keff_std_dev: 0.000589,
      reference_physical_balance_kind: "finite-domain-keff",
      reference_physical_balance_keff: 1.112276,
      reference_physical_balance_delta_pcm: -3.5,
      reference_physical_balance_z: -0.059,
      reference_collision_balance_kinf: 1.18,
      reference_finite_balance_available: true,
      reference_finite_balance_keff: 1.112276,
      reference_leakage: 0.04,
      reference_rate_balance_keff: 1.112276,
      reference_rate_balance_delta_pcm: -3.5,
      reference_rate_balance_z: -0.059,
      donjon_keff: 1.111595,
      donjon_delta_pcm: -71.5819,
      donjon_z: -1.216,
      max_abs_z: 2.0,
    },
    component_balance: {
      reference_net_loss: 0.99976,
      donjon_net_loss: 1.00037,
      net_loss_relative_residual: 0.000612,
      flux_rms_relative_residual: 0.00656,
      flux_max_relative_residual: 0.0235,
      power_normalization_factor: 1.11195,
      per_component: [],
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
    geometry: {
      kind: "hexagonal",
      boundary_conditions: "radial vacuum; axial reflective",
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
          execution_deck_path: "/tmp/native_sph.x2m",
          deck_reproduced_in_result_listing: true,
          adf: { used: false, evidence_status: "verified_absent", issues: [] },
          empirical_eigenvalue_multiplier: {
            used: false,
            evidence_status: "verified_absent",
            issues: [],
          },
          issues: [],
        },
      },
      physics_acceptance: "passed",
      reactor_acceptance: "not_evaluated",
    },
    quality: {
      ...SUMMARY.quality!,
      decision: "native_sph_physics_passed",
      production_ready: true,
    },
  };
}
