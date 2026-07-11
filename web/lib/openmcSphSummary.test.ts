import { describe, expect, it } from "vitest";
import bundledFixture from "../../src/openmc2donjon/web/fixtures/openmc_sph_physics_summary.json";
import type { OpenmcSphPhysicsSummary } from "./api";
import {
  formatScatterTreatment,
  formatPhysicsNumber,
  openmcSphConvertHref,
  productionEvidenceRows,
  reactionRatePreservationRows,
  sphUpdatePolicyRows,
  summaryStatus,
  topSphDeviationRows,
} from "./openmcSphSummary";

const SUMMARY: OpenmcSphPhysicsSummary = {
  schema: "openmc2donjon.openmc-ce-mg-sph-physics-summary.v1",
  route: "OpenMC CE reference + OpenMC MG same geometry -> OpenMC-side SPH",
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
  it("marks summaries with HDF5 SPH and ASCII NSPH as pass", () => {
    expect(summaryStatus(SUMMARY)).toMatchObject({
      tone: "pass",
      label: "handoff carries NSPH",
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
